#!/usr/bin/env python3
"""Explicit one-time Social Agent scheduling workflow.

This helper records one publication intent through the authenticated hosted API.
It never calls Postiz directly and never reports external scheduling or
publication from local job acceptance.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import social_agent_api as api  # noqa: E402

PROJECT_REFERENCE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{8,160}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _uuid(value: str, *, field: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise api.SocialAgentAPIError(f"{field} must be a UUID") from exc


def _future_time(value: str, *, now: datetime | None = None) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise api.SocialAgentAPIError(
            "--publish-at must be an ISO-8601 datetime with a timezone offset"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise api.SocialAgentAPIError("--publish-at must include a timezone offset")
    current = now or datetime.now(UTC)
    if parsed.astimezone(UTC) <= current.astimezone(UTC):
        raise api.SocialAgentAPIError("--publish-at must be in the future")
    return parsed


def _schedule_one(
    *,
    project_reference_id: str,
    content_version_id: str,
    content_hash: str,
    destination_id: str,
    publish_at: str,
    idempotency_key: str,
    user_confirmed: bool,
    timeout: float,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not user_confirmed:
        raise api.SocialAgentAPIError(
            "Explicit user confirmation is required to schedule a post"
        )
    if PROJECT_REFERENCE_PATTERN.fullmatch(project_reference_id) is None:
        raise api.SocialAgentAPIError("--project-reference-id has an invalid format")
    if SHA256_PATTERN.fullmatch(content_hash) is None:
        raise api.SocialAgentAPIError("--content-hash must be lowercase SHA-256")
    if IDEMPOTENCY_PATTERN.fullmatch(idempotency_key) is None:
        raise api.SocialAgentAPIError("--idempotency-key has an invalid format")

    version_id = _uuid(content_version_id, field="--content-version-id")
    selected_destination_id = _uuid(destination_id, field="--destination-id")
    requested_time = _future_time(publish_at, now=now)
    response = api.request_json(
        "POST",
        "/v1/jobs",
        body={
            "api_version": api.API_VERSION,
            "project_reference_id": project_reference_id,
            "job_type": "schedule_posts",
            "idempotency_key": idempotency_key,
            "inputs": {
                "confirmed": True,
                "destination_id": selected_destination_id,
                "posts": [
                    {
                        "content_version_id": version_id,
                        "content_hash": content_hash,
                        "planned_publish_at": requested_time.isoformat(),
                    }
                ],
            },
        },
        timeout=timeout,
    )
    job = response.get("job")
    if not isinstance(job, dict):
        raise api.SocialAgentAPIError("Social Agent API returned an invalid job response")
    result = job.get("result_json")
    if (
        job.get("job_type") != "schedule_posts"
        or job.get("stage") != "scheduling_intents_recorded"
        or not isinstance(result, dict)
        or result.get("publication_state") != "intent_recorded"
    ):
        raise api.SocialAgentAPIError(
            "Social Agent API did not confirm a one-time publication intent"
        )
    binding = result.get("request_binding")
    binding_time_raw = (
        binding.get("planned_publish_at") if isinstance(binding, dict) else None
    )
    try:
        binding_time = (
            datetime.fromisoformat(binding_time_raw.replace("Z", "+00:00"))
            if isinstance(binding_time_raw, str)
            else None
        )
    except ValueError:
        binding_time = None
    if (
        not isinstance(binding, dict)
        or binding.get("api_version") != api.API_VERSION
        or binding.get("project_reference_id") != project_reference_id
        or binding.get("idempotency_key") != idempotency_key
        or binding.get("content_version_id") != version_id
        or binding.get("content_hash") != content_hash
        or binding.get("destination_id") != selected_destination_id
        or binding_time is None
        or binding_time.tzinfo is None
        or binding_time.astimezone(UTC) != requested_time.astimezone(UTC)
    ):
        raise api.SocialAgentAPIError(
            "Social Agent API returned mismatched scheduling request evidence"
        )
    publications = result.get("publications")
    if not isinstance(publications, list) or len(publications) != 1:
        raise api.SocialAgentAPIError(
            "Social Agent API returned an invalid publication intent"
        )
    publication = publications[0]
    if not isinstance(publication, dict):
        raise api.SocialAgentAPIError(
            "Social Agent API returned an invalid publication intent"
        )
    accepted_time_raw = publication.get("planned_publish_at")
    if not isinstance(accepted_time_raw, str):
        raise api.SocialAgentAPIError(
            "Social Agent API omitted the accepted publication time"
        )
    try:
        accepted_time = datetime.fromisoformat(
            accepted_time_raw.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise api.SocialAgentAPIError(
            "Social Agent API returned an invalid accepted publication time"
        ) from exc
    if (
        publication.get("content_version_id") != version_id
        or publication.get("content_hash") != content_hash
        or publication.get("destination_id") != selected_destination_id
        or accepted_time.tzinfo is None
        or accepted_time.astimezone(UTC) != requested_time.astimezone(UTC)
        or publication.get("state") != "pending"
        or publication.get("external_schedule_ref") is not None
    ):
        raise api.SocialAgentAPIError(
            "Social Agent API returned mismatched publication intent evidence"
        )
    publication_id = publication.get("id")
    if not isinstance(publication_id, str) or not publication_id:
        raise api.SocialAgentAPIError(
            "Social Agent API omitted the publication intent identifier"
        )
    return {
        "status": "intent_recorded",
        "publication_id": publication_id,
        "content_version_id": version_id,
        "destination_id": selected_destination_id,
        "planned_publish_at": publication.get("planned_publish_at"),
        "externally_scheduled": False,
        "published": False,
        "next_action": (
            "Wait for Social Connect submission and reconciliation. "
            "Do not report this post as externally scheduled or published yet."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record one approved post publication intent through the hosted Social Agent API"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    schedule = subparsers.add_parser(
        "schedule-one", help="record one explicitly confirmed publication intent"
    )
    schedule.add_argument(
        "--timeout",
        type=float,
        default=api.DEFAULT_TIMEOUT_SECONDS,
        help="request timeout in seconds",
    )
    schedule.add_argument("--project-reference-id", required=True)
    schedule.add_argument("--content-version-id", required=True)
    schedule.add_argument("--content-hash", required=True)
    schedule.add_argument("--destination-id", required=True)
    schedule.add_argument("--publish-at", required=True)
    schedule.add_argument("--idempotency-key", required=True)
    schedule.add_argument("--confirm-user-schedule", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = _schedule_one(
            project_reference_id=args.project_reference_id,
            content_version_id=args.content_version_id,
            content_hash=args.content_hash,
            destination_id=args.destination_id,
            publish_at=args.publish_at,
            idempotency_key=args.idempotency_key,
            user_confirmed=bool(args.confirm_user_schedule),
            timeout=args.timeout,
        )
        print(json.dumps(result, sort_keys=True), flush=True)
        return 0
    except api.SocialAgentAPIError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
