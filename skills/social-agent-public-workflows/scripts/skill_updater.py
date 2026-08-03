from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import stat
import sys
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

SKILL_NAME = "social-agent-public-workflows"
OFFICIAL_REPOSITORY = "lniass/social-skills"
OFFICIAL_BRANCH = "main"
OFFICIAL_VERSION_URL = (
    "https://raw.githubusercontent.com/"
    f"{OFFICIAL_REPOSITORY}/{OFFICIAL_BRANCH}/skills/{SKILL_NAME}/VERSION"
)
OFFICIAL_ARCHIVE_URL = (
    f"https://github.com/{OFFICIAL_REPOSITORY}/archive/refs/heads/{OFFICIAL_BRANCH}.zip"
)
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
FAILURE_CHECK_INTERVAL_SECONDS = 30 * 60
RECENT_CHECK_GRACE_SECONDS = 5 * 60
NETWORK_TIMEOUT_SECONDS = 10
MAX_VERSION_BYTES = 128
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_FILES = 200
REQUIRED_FILES = (
    "SKILL.md",
    "VERSION",
    "scripts/social_agent_api.py",
    "scripts/skill_updater.py",
)
STATE_ENV = "SOCIAL_AGENT_UPDATE_STATE_DIR"
DISABLE_ENV = "SOCIAL_AGENT_DISABLE_AUTO_UPDATE"
REEXEC_ENV = "SOCIAL_AGENT_UPDATE_REEXEC"
TRUE_VALUES = frozenset({"1", "true", "yes"})
VERSION_PARTS = 3


class SkillUpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateResult:
    status: str
    installed_version: str
    official_version: str | None = None
    checked: bool = False
    updated: bool = False


def _skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_dir() -> Path:
    configured = os.environ.get(STATE_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    cache_home = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(cache_home).expanduser() if cache_home else Path.home() / ".cache"
    return base / SKILL_NAME


def _state_path() -> Path:
    return _state_dir() / "update-state.json"


def _lock_path() -> Path:
    return _state_dir() / "update.lock"


def _disabled() -> bool:
    return os.environ.get(DISABLE_ENV, "").strip().lower() in TRUE_VALUES


def _version_tuple(value: str) -> tuple[int, int, int]:
    value = value.strip()
    parts = value.split(".")
    if len(parts) != VERSION_PARTS or any(not part.isdigit() for part in parts):
        raise SkillUpdateError("Skill version must use three numeric components")
    numbers = tuple(int(part) for part in parts)
    if any(number > 999_999 for number in numbers):
        raise SkillUpdateError("Skill version component is too large")
    return numbers  # type: ignore[return-value]


def _read_local_version(skill_dir: Path | None = None) -> str:
    path = (skill_dir or _skill_dir()) / "VERSION"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SkillUpdateError("Installed skill VERSION file is unavailable") from exc
    _version_tuple(value)
    return value


def _read_state() -> dict[str, Any]:
    path = _state_path()
    try:
        payload = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_state(state: dict[str, Any]) -> None:
    directory = _state_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=directory,
        prefix="update-state-",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(state, handle, sort_keys=True, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, _state_path())


@contextlib.contextmanager
def _update_lock() -> Iterator[None]:
    directory = _state_dir()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    handle = _lock_path().open("a+b")
    lock_module: Any | None = None
    try:
        try:
            import fcntl

            lock_module = fcntl
        except ImportError:
            pass
        if lock_module is not None:
            lock_module.flock(handle.fileno(), lock_module.LOCK_EX)
        yield
    finally:
        if lock_module is not None:
            lock_module.flock(handle.fileno(), lock_module.LOCK_UN)
        handle.close()


def _read_limited(response: Any, maximum: int) -> bytes:
    payload = response.read(maximum + 1)
    if len(payload) > maximum:
        raise SkillUpdateError("Official GitHub update response exceeded the safe size limit")
    return payload


def _fetch_official_version() -> str:
    request = Request(
        OFFICIAL_VERSION_URL,
        headers={"Accept": "text/plain", "User-Agent": f"{SKILL_NAME}-updater"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            payload = _read_limited(response, MAX_VERSION_BYTES)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SkillUpdateError("Could not check the official GitHub skill version") from exc
    try:
        value = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise SkillUpdateError("Official GitHub VERSION file was not UTF-8") from exc
    _version_tuple(value)
    return value


def _download_archive() -> bytes:
    request = Request(
        OFFICIAL_ARCHIVE_URL,
        headers={"Accept": "application/zip", "User-Agent": f"{SKILL_NAME}-updater"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
            return _read_limited(response, MAX_ARCHIVE_BYTES)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SkillUpdateError("Could not download the official GitHub skill archive") from exc


def _archive_member_relative_path(name: str) -> PurePosixPath | None:
    path = PurePosixPath(name)
    parts = path.parts
    marker = ("skills", SKILL_NAME)
    for index in range(len(parts) - 1):
        if tuple(parts[index : index + 2]) == marker:
            relative = PurePosixPath(*parts[index + 2 :])
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                return None
            return relative
    return None


def _stage_archive(archive: bytes, parent: Path, official_version: str) -> Path:
    stage = parent / f".{SKILL_NAME}.update-{uuid4().hex}"
    stage.mkdir(mode=0o700)
    extracted_bytes = 0
    extracted_files = 0
    try:
        archive_path = stage / ".download.zip"
        archive_path.write_bytes(archive)
        with zipfile.ZipFile(archive_path) as bundle:
            for member in bundle.infolist():
                relative = _archive_member_relative_path(member.filename)
                if relative is None or member.is_dir():
                    continue
                unix_mode = member.external_attr >> 16
                if stat.S_IFMT(unix_mode) == stat.S_IFLNK:
                    raise SkillUpdateError("Official GitHub skill archive contains a symbolic link")
                extracted_files += 1
                extracted_bytes += member.file_size
                if extracted_files > MAX_ARCHIVE_FILES or extracted_bytes > MAX_EXTRACTED_BYTES:
                    raise SkillUpdateError("Official GitHub skill archive exceeded extraction limits")
                destination = stage.joinpath(*relative.parts)
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as target:
                    shutil.copyfileobj(source, target)
                os.chmod(destination, 0o700 if destination.suffix == ".py" else 0o600)
        archive_path.unlink(missing_ok=True)
        for required in REQUIRED_FILES:
            if not (stage / required).is_file():
                raise SkillUpdateError("Official GitHub skill archive is incomplete")
        if _read_local_version(stage) != official_version:
            raise SkillUpdateError("Official GitHub version changed while the update was downloading")
        return stage
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _inside_git_checkout(skill_dir: Path) -> bool:
    return any((parent / ".git").exists() for parent in (skill_dir, *skill_dir.parents))


def _install_archive(archive: bytes, official_version: str) -> None:
    skill_dir = _skill_dir()
    if _inside_git_checkout(skill_dir):
        raise SkillUpdateError("A Git checkout must be updated with Git instead of self-replacement")
    parent = skill_dir.parent
    stage = _stage_archive(archive, parent, official_version)
    backup = parent / f".{skill_dir.name}.previous"
    stale_backup = parent / f".{skill_dir.name}.previous-{uuid4().hex}"
    if backup.exists():
        os.replace(backup, stale_backup)
    try:
        os.replace(skill_dir, backup)
        try:
            os.replace(stage, skill_dir)
        except Exception:
            os.replace(backup, skill_dir)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        if stale_backup.exists():
            shutil.rmtree(stale_backup, ignore_errors=True)


def _check_due(state: dict[str, Any], now: float, reason: str, force: bool) -> bool:
    if force:
        return True
    if reason == "api_failure":
        last_success = state.get("last_successful_check_at")
        if isinstance(last_success, (int, float)) and now - float(last_success) < RECENT_CHECK_GRACE_SECONDS:
            return False
        last_failure = state.get("last_failure_check_at")
        return not isinstance(last_failure, (int, float)) or now - float(last_failure) >= FAILURE_CHECK_INTERVAL_SECONDS
    last_success = state.get("last_successful_check_at")
    if isinstance(last_success, (int, float)) and now - float(last_success) < CHECK_INTERVAL_SECONDS:
        return False
    last_attempt = state.get("last_check_attempt_at")
    return not isinstance(last_attempt, (int, float)) or now - float(last_attempt) >= FAILURE_CHECK_INTERVAL_SECONDS


def check_and_update(*, reason: str = "before_api", force: bool = False) -> UpdateResult:
    installed = _read_local_version()
    if _disabled():
        return UpdateResult(status="disabled", installed_version=installed)
    if _inside_git_checkout(_skill_dir()) and not force:
        return UpdateResult(status="development_checkout", installed_version=installed)
    now = time.time()
    with _update_lock():
        state = _read_state()
        if not _check_due(state, now, reason, force):
            official = state.get("official_version")
            return UpdateResult(
                status="fresh",
                installed_version=installed,
                official_version=official if isinstance(official, str) else None,
            )
        state["last_check_attempt_at"] = now
        if reason == "api_failure":
            state["last_failure_check_at"] = now
        _write_state(state)
        try:
            official = _fetch_official_version()
        except SkillUpdateError as exc:
            state["last_failure_check_at"] = now
            state["last_error_at"] = now
            state["last_error"] = str(exc)
            _write_state(state)
            return UpdateResult(status="check_failed", installed_version=installed, checked=True)
        state.update(
            {
                "last_successful_check_at": now,
                "official_version": official,
                "installed_version": installed,
            }
        )
        state.pop("last_error", None)
        state.pop("last_error_at", None)
        if _version_tuple(installed) >= _version_tuple(official):
            _write_state(state)
            return UpdateResult(
                status="current",
                installed_version=installed,
                official_version=official,
                checked=True,
            )
        if _inside_git_checkout(_skill_dir()):
            state["update_available"] = True
            _write_state(state)
            return UpdateResult(
                status="update_available",
                installed_version=installed,
                official_version=official,
                checked=True,
            )
        try:
            archive = _download_archive()
            _install_archive(archive, official)
        except (OSError, SkillUpdateError, zipfile.BadZipFile) as exc:
            state["last_failure_check_at"] = now
            state["last_error_at"] = now
            state["last_error"] = str(exc)
            _write_state(state)
            return UpdateResult(
                status="update_failed",
                installed_version=installed,
                official_version=official,
                checked=True,
            )
        state.update(
            {
                "installed_version": official,
                "updated_at": now,
                "update_available": False,
            }
        )
        _write_state(state)
        return UpdateResult(
            status="updated",
            installed_version=official,
            official_version=official,
            checked=True,
            updated=True,
        )


def _is_api_failure(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (HTTPError, URLError, TimeoutError, ConnectionError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def maybe_update_and_reexec(*, reason: str = "before_api") -> UpdateResult:
    try:
        result = check_and_update(reason=reason)
    except (OSError, SkillUpdateError):
        return UpdateResult(status="check_failed", installed_version="unknown")
    if result.updated and os.environ.get(REEXEC_ENV) != "1":
        os.environ[REEXEC_ENV] = "1"
        os.execv(sys.executable, [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])
    return result


def maybe_check_after_api_failure(error: BaseException) -> UpdateResult | None:
    if not _is_api_failure(error):
        return None
    return maybe_update_and_reexec(reason="api_failure")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check the official GitHub Social Agent skill version")
    parser.add_argument("command", choices=("status", "check"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "status":
        installed = _read_local_version()
        state = _read_state()
        result = UpdateResult(
            status="status",
            installed_version=installed,
            official_version=state.get("official_version") if isinstance(state.get("official_version"), str) else None,
        )
    else:
        result = check_and_update(force=True)
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.status not in {"check_failed", "update_failed"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
