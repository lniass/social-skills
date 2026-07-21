#!/usr/bin/env python3
"""Dependency-light client for the hosted Social Agent API.

This helper intentionally exposes only workspace-credential routes. Operator
bootstrap and administrative credentials do not belong in the public skill.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

API_VERSION = "2026-07-01"
DEFAULT_API_BASE_URL = "https://social-agent-api.voicevine.ai"
DEFAULT_TIMEOUT_SECONDS = 30.0
CREDENTIAL_PATTERN = re.compile(r"sai_[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,256}")
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
JOB_TYPES = (
    "setup_project",
    "update_project_context",
    "get_next_question",
    "answer_question",
    "get_next_update_question",
    "answer_update_question",
    "configure_recurrence",
    "get_recurrence",
    "create_posts",
    "create_assets",
    "approve_or_reject",
    "connect_destination",
    "schedule_posts",
    "check_status",
)


class SocialAgentAPIError(RuntimeError):
    """Safe, credential-redacted API failure."""


def _redact(value: str, credential: str | None = None) -> str:
    if credential:
        value = value.replace(credential, "[REDACTED]")
    return CREDENTIAL_PATTERN.sub("[REDACTED]", value)


def _validate_api_base_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme == "https" and parsed.netloc:
        return value
    if parsed.scheme == "http" and parsed.hostname in LOCAL_HOSTS and parsed.netloc:
        return value
    raise SocialAgentAPIError("SOCIAL_AGENT_API_BASE_URL must use HTTPS, except for localhost development")


def _read_credential_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    try:
        file_stat = path.stat()
    except OSError as exc:
        raise SocialAgentAPIError(f"Cannot read SOCIAL_AGENT_API_KEY_FILE: {_redact(str(exc))}") from exc
    if not stat.S_ISREG(file_stat.st_mode):
        raise SocialAgentAPIError("SOCIAL_AGENT_API_KEY_FILE must point to a regular file")
    if file_stat.st_mode & 0o077:
        raise SocialAgentAPIError("SOCIAL_AGENT_API_KEY_FILE permissions must be 0600 or stricter")
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SocialAgentAPIError(f"Cannot read SOCIAL_AGENT_API_KEY_FILE: {_redact(str(exc))}") from exc


def load_api_key() -> str:
    credential = os.environ.get("SOCIAL_AGENT_API_KEY", "").strip()
    if not credential:
        credential_file = os.environ.get("SOCIAL_AGENT_API_KEY_FILE", "").strip()
        if credential_file:
            credential = _read_credential_file(credential_file)
    if not credential:
        raise SocialAgentAPIError(
            "Set SOCIAL_AGENT_API_KEY or SOCIAL_AGENT_API_KEY_FILE to a workspace-scoped Social Agent credential"
        )
    if CREDENTIAL_PATTERN.fullmatch(credential) is None:
        raise SocialAgentAPIError("The configured Social Agent credential has an invalid format")
    return credential


def request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    credential = load_api_key()
    base_url = _validate_api_base_url(os.environ.get("SOCIAL_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL))
    url = f"{base_url}/{path.lstrip('/')}"
    encoded_body = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {credential}",
        "User-Agent": "social-agent-public-workflows/0.1.0",
    }
    if encoded_body is not None:
        headers["Content-Type"] = "application/json"

    request = Request(url, data=encoded_body, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        safe_body = _redact(response_body, credential)
        raise SocialAgentAPIError(f"Social Agent API returned HTTP {exc.code}: {safe_body}") from exc
    except URLError as exc:
        reason = _redact(str(exc.reason), credential)
        raise SocialAgentAPIError(f"Could not reach the Social Agent API: {reason}") from exc

    try:
        parsed = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise SocialAgentAPIError("Social Agent API returned an invalid JSON response") from exc
    if not isinstance(parsed, dict):
        raise SocialAgentAPIError("Social Agent API returned an unexpected JSON response")
    return parsed


def _json_object(raw_value: str) -> dict[str, Any]:
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Call the hosted Social Agent API with a workspace credential")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="request timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("capabilities", help="read workspace capabilities")
    subparsers.add_parser("projects", help="list projects visible to the credential")

    create_job = subparsers.add_parser("create-job", help="submit a deterministic job packet")
    create_job.add_argument("--job-type", choices=JOB_TYPES, required=True)
    create_job.add_argument("--idempotency-key", required=True)
    create_job.add_argument("--project-reference-id")
    create_job.add_argument("--inputs-json", type=_json_object, default={})

    job_status = subparsers.add_parser("job-status", help="read one job by its server ID")
    job_status.add_argument("job_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            result = request_json("GET", "/v1/capabilities", timeout=args.timeout)
        elif args.command == "projects":
            result = request_json("GET", "/v1/projects", timeout=args.timeout)
        elif args.command == "create-job":
            payload: dict[str, Any] = {
                "api_version": API_VERSION,
                "job_type": args.job_type,
                "idempotency_key": args.idempotency_key,
                "inputs": args.inputs_json,
            }
            if args.project_reference_id:
                payload["project_reference_id"] = args.project_reference_id
            result = request_json("POST", "/v1/jobs", body=payload, timeout=args.timeout)
        elif args.command == "job-status":
            result = request_json("GET", f"/v1/jobs/{quote(args.job_id, safe='')}", timeout=args.timeout)
        else:  # pragma: no cover - argparse enforces commands
            raise SocialAgentAPIError("Unsupported command")
    except SocialAgentAPIError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
