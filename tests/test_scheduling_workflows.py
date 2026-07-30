from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "social-agent-public-workflows" / "scripts"
MODULE_PATH = SCRIPTS / "scheduling_workflows.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

SPEC = importlib.util.spec_from_file_location("scheduling_workflows_tested", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scheduling = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduling)

VERSION_ID = "11111111-1111-4111-8111-111111111111"
DESTINATION_ID = "22222222-2222-4222-8222-222222222222"
CONTENT_HASH = "a" * 64


def _response(
    planned_publish_at: str = "2026-08-01T13:00:00+00:00",
) -> dict[str, object]:
    return {
        "job": {
            "job_type": "schedule_posts",
            "stage": "scheduling_intents_recorded",
            "result_json": {
                "publication_state": "intent_recorded",
                "request_binding": {
                    "api_version": scheduling.api.API_VERSION,
                    "project_reference_id": "project-one",
                    "idempotency_key": "schedule-one-001",
                    "content_version_id": VERSION_ID,
                    "content_hash": CONTENT_HASH,
                    "destination_id": DESTINATION_ID,
                    "planned_publish_at": planned_publish_at,
                },
                "publications": [
                    {
                        "id": "publication-1",
                        "content_version_id": VERSION_ID,
                        "content_hash": CONTENT_HASH,
                        "destination_id": DESTINATION_ID,
                        "planned_publish_at": planned_publish_at,
                        "state": "pending",
                        "external_schedule_ref": None,
                    }
                ],
            },
        }
    }


class SchedulingWorkflowTests(unittest.TestCase):
    def test_schedule_one_requires_explicit_confirmation_without_request(self) -> None:
        with patch.object(scheduling.api, "request_json") as request:
            with self.assertRaisesRegex(
                scheduling.api.SocialAgentAPIError, "Explicit user confirmation"
            ):
                scheduling._schedule_one(
                    project_reference_id="project-one",
                    content_version_id=VERSION_ID,
                    content_hash=CONTENT_HASH,
                    destination_id=DESTINATION_ID,
                    publish_at="2026-08-01T09:00:00-04:00",
                    idempotency_key="schedule-one-001",
                    user_confirmed=False,
                    timeout=30,
                    now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                )
        request.assert_not_called()

    def test_schedule_one_sends_exact_binding_and_reports_intent_only(self) -> None:
        with patch.object(
            scheduling.api, "request_json", return_value=_response()
        ) as request:
            result = scheduling._schedule_one(
                project_reference_id="project-one",
                content_version_id=VERSION_ID,
                content_hash=CONTENT_HASH,
                destination_id=DESTINATION_ID,
                publish_at="2026-08-01T09:00:00-04:00",
                idempotency_key="schedule-one-001",
                user_confirmed=True,
                timeout=30,
                now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
            )

        request.assert_called_once_with(
            "POST",
            "/v1/jobs",
            body={
                "api_version": scheduling.api.API_VERSION,
                "project_reference_id": "project-one",
                "job_type": "schedule_posts",
                "idempotency_key": "schedule-one-001",
                "inputs": {
                    "confirmed": True,
                    "destination_id": DESTINATION_ID,
                    "posts": [
                        {
                            "content_version_id": VERSION_ID,
                            "content_hash": CONTENT_HASH,
                            "planned_publish_at": "2026-08-01T09:00:00-04:00",
                        }
                    ],
                },
            },
            timeout=30,
        )
        self.assertEqual(result["status"], "intent_recorded")
        self.assertFalse(result["externally_scheduled"])
        self.assertFalse(result["published"])
        self.assertNotIn("postiz", str(result).lower())

    def test_schedule_one_rejects_naive_time_and_mismatched_response(self) -> None:
        with patch.object(scheduling.api, "request_json") as request:
            with self.assertRaisesRegex(
                scheduling.api.SocialAgentAPIError, "timezone offset"
            ):
                scheduling._schedule_one(
                    project_reference_id="project-one",
                    content_version_id=VERSION_ID,
                    content_hash=CONTENT_HASH,
                    destination_id=DESTINATION_ID,
                    publish_at="2026-08-01T09:00:00",
                    idempotency_key="schedule-one-001",
                    user_confirmed=True,
                    timeout=30,
                    now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                )
        request.assert_not_called()

        hash_mismatch = _response()
        hash_publication = hash_mismatch["job"]["result_json"]["publications"][0]  # type: ignore[index]
        hash_publication["content_hash"] = "b" * 64  # type: ignore[index]
        with patch.object(
            scheduling.api, "request_json", return_value=hash_mismatch
        ):
            with self.assertRaisesRegex(
                scheduling.api.SocialAgentAPIError, "mismatched publication"
            ):
                scheduling._schedule_one(
                    project_reference_id="project-one",
                    content_version_id=VERSION_ID,
                    content_hash=CONTENT_HASH,
                    destination_id=DESTINATION_ID,
                    publish_at="2026-08-01T09:00:00-04:00",
                    idempotency_key="schedule-one-001",
                    user_confirmed=True,
                    timeout=30,
                    now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                )

        binding_mismatch = _response()
        binding = binding_mismatch["job"]["result_json"]["request_binding"]  # type: ignore[index]
        binding["destination_id"] = "33333333-3333-4333-8333-333333333333"  # type: ignore[index]
        with patch.object(
            scheduling.api, "request_json", return_value=binding_mismatch
        ):
            with self.assertRaisesRegex(
                scheduling.api.SocialAgentAPIError, "mismatched scheduling request"
            ):
                scheduling._schedule_one(
                    project_reference_id="project-one",
                    content_version_id=VERSION_ID,
                    content_hash=CONTENT_HASH,
                    destination_id=DESTINATION_ID,
                    publish_at="2026-08-01T09:00:00-04:00",
                    idempotency_key="schedule-one-001",
                    user_confirmed=True,
                    timeout=30,
                    now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                )

        mismatched = _response()
        publication = mismatched["job"]["result_json"]["publications"][0]  # type: ignore[index]
        publication["destination_id"] = "33333333-3333-4333-8333-333333333333"  # type: ignore[index]
        with patch.object(scheduling.api, "request_json", return_value=mismatched):
            with self.assertRaisesRegex(
                scheduling.api.SocialAgentAPIError, "mismatched publication"
            ):
                scheduling._schedule_one(
                    project_reference_id="project-one",
                    content_version_id=VERSION_ID,
                    content_hash=CONTENT_HASH,
                    destination_id=DESTINATION_ID,
                    publish_at="2026-08-01T09:00:00-04:00",
                    idempotency_key="schedule-one-001",
                    user_confirmed=True,
                    timeout=30,
                    now=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
                )

    def test_cli_failure_and_success_flush_json(self) -> None:
        stderr = io.StringIO()
        with redirect_stderr(stderr), patch.object(
            scheduling.api, "request_json"
        ) as request:
            exit_code = scheduling.main(
                [
                    "schedule-one",
                    "--project-reference-id",
                    "project-one",
                    "--content-version-id",
                    VERSION_ID,
                    "--content-hash",
                    CONTENT_HASH,
                    "--destination-id",
                    DESTINATION_ID,
                    "--publish-at",
                    "2099-08-01T09:00:00-04:00",
                    "--idempotency-key",
                    "schedule-one-001",
                ]
            )
        self.assertEqual(exit_code, 1)
        self.assertIn("Explicit user confirmation", stderr.getvalue())
        request.assert_not_called()

        stdout = io.StringIO()
        with redirect_stdout(stdout), patch.object(
            scheduling.api,
            "request_json",
            return_value=_response("2099-08-01T13:00:00+00:00"),
        ):
            exit_code = scheduling.main(
                [
                    "schedule-one",
                    "--project-reference-id",
                    "project-one",
                    "--content-version-id",
                    VERSION_ID,
                    "--content-hash",
                    CONTENT_HASH,
                    "--destination-id",
                    DESTINATION_ID,
                    "--publish-at",
                    "2099-08-01T09:00:00-04:00",
                    "--idempotency-key",
                    "schedule-one-001",
                    "--confirm-user-schedule",
                ]
            )
        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "intent_recorded"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
