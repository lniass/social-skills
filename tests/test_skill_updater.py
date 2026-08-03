from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock
from urllib.error import URLError

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "social-agent-public-workflows"
    / "scripts"
    / "skill_updater.py"
)
SPEC = importlib.util.spec_from_file_location("skill_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)


class SkillUpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.skill_dir = self.root / updater.SKILL_NAME
        self.skill_dir.mkdir()
        (self.skill_dir / "VERSION").write_text("1.0.0\n", encoding="utf-8")
        self.state_dir = self.root / "state"
        self.environment = mock.patch.dict(
            os.environ,
            {
                updater.STATE_ENV: str(self.state_dir),
                updater.DISABLE_ENV: "0",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.skill_patch = mock.patch.object(updater, "_skill_dir", return_value=self.skill_dir)
        self.skill_patch.start()
        self.addCleanup(self.skill_patch.stop)

    def test_current_version_is_cached_for_six_hours(self) -> None:
        with mock.patch.object(updater, "_fetch_official_version", return_value="1.0.0") as fetch:
            first = updater.check_and_update()
            second = updater.check_and_update()

        self.assertEqual(first.status, "current")
        self.assertTrue(first.checked)
        self.assertEqual(second.status, "fresh")
        self.assertFalse(second.checked)
        fetch.assert_called_once_with()
        state = json.loads((self.state_dir / "update-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["official_version"], "1.0.0")

    def test_newer_version_downloads_and_installs(self) -> None:
        with (
            mock.patch.object(updater, "_fetch_official_version", return_value="1.1.0"),
            mock.patch.object(updater, "_download_archive", return_value=b"archive") as download,
            mock.patch.object(updater, "_install_archive") as install,
        ):
            result = updater.check_and_update()

        self.assertEqual(result.status, "updated")
        self.assertTrue(result.updated)
        download.assert_called_once_with()
        install.assert_called_once_with(b"archive", "1.1.0")

    def test_git_checkout_reports_update_without_replacing_files(self) -> None:
        (self.root / ".git").mkdir()
        with (
            mock.patch.object(updater, "_fetch_official_version", return_value="1.1.0"),
            mock.patch.object(updater, "_download_archive") as download,
        ):
            result = updater.check_and_update(force=True)

        self.assertEqual(result.status, "update_available")
        self.assertFalse(result.updated)
        download.assert_not_called()

    def test_failed_check_is_non_destructive(self) -> None:
        with mock.patch.object(
            updater,
            "_fetch_official_version",
            side_effect=updater.SkillUpdateError("offline"),
        ):
            result = updater.check_and_update()

        self.assertEqual(result.status, "check_failed")
        self.assertEqual((self.skill_dir / "VERSION").read_text(encoding="utf-8"), "1.0.0\n")

        with mock.patch.object(updater, "_fetch_official_version") as fetch:
            throttled = updater.check_and_update()
        self.assertEqual(throttled.status, "fresh")
        fetch.assert_not_called()

    def test_api_failure_check_has_thirty_minute_cooldown(self) -> None:
        old = updater.time.time() - updater.RECENT_CHECK_GRACE_SECONDS - 1
        self.state_dir.mkdir()
        (self.state_dir / "update-state.json").write_text(
            json.dumps(
                {
                    "last_successful_check_at": old,
                    "last_failure_check_at": updater.time.time(),
                    "official_version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(updater, "_fetch_official_version") as fetch:
            result = updater.check_and_update(reason="api_failure")

        self.assertEqual(result.status, "fresh")
        fetch.assert_not_called()

    def test_recent_success_suppresses_immediate_failure_recheck(self) -> None:
        self.state_dir.mkdir()
        (self.state_dir / "update-state.json").write_text(
            json.dumps(
                {
                    "last_successful_check_at": updater.time.time(),
                    "official_version": "1.0.0",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch.object(updater, "_fetch_official_version") as fetch:
            result = updater.check_and_update(reason="api_failure")

        self.assertEqual(result.status, "fresh")
        fetch.assert_not_called()

    def test_api_failure_detection_walks_exception_chain(self) -> None:
        try:
            try:
                raise URLError("offline")
            except URLError as cause:
                raise RuntimeError("safe wrapper") from cause
        except RuntimeError as error:
            self.assertTrue(updater._is_api_failure(error))
        self.assertFalse(updater._is_api_failure(ValueError("local validation")))

    def test_archive_staging_rejects_version_race(self) -> None:
        archive = self._archive(version="1.2.0")
        with self.assertRaisesRegex(updater.SkillUpdateError, "version changed"):
            updater._stage_archive(archive, self.root, "1.1.0")
        self.assertFalse(any(self.root.glob(f".{updater.SKILL_NAME}.update-*")))

    def test_archive_install_replaces_skill_and_keeps_previous_copy(self) -> None:
        (self.skill_dir / "old.txt").write_text("old", encoding="utf-8")
        updater._install_archive(self._archive(version="1.1.0"), "1.1.0")

        self.assertEqual((self.skill_dir / "VERSION").read_text(encoding="utf-8"), "1.1.0\n")
        self.assertFalse((self.skill_dir / "old.txt").exists())
        backup = self.root / f".{updater.SKILL_NAME}.previous"
        self.assertEqual((backup / "old.txt").read_text(encoding="utf-8"), "old")

    def _archive(self, *, version: str) -> bytes:
        prefix = f"social-skills-main/skills/{updater.SKILL_NAME}"
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as bundle:
            files = {
                "SKILL.md": "---\nname: social-agent-public-workflows\n---\n",
                "VERSION": f"{version}\n",
                "scripts/social_agent_api.py": "print('api')\n",
                "scripts/skill_updater.py": "print('updater')\n",
            }
            for relative, content in files.items():
                bundle.writestr(f"{prefix}/{relative}", content)
        return stream.getvalue()


if __name__ == "__main__":
    unittest.main()
