#!/usr/bin/env python3
"""Explicit Social Agent post-request workflows.

The current guest bridge consumes the private verification capability saved by
``guest_questionnaire.py``. Future authenticated post, media, and recurrence
operations belong in this workflow layer rather than in onboarding.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import guest_questionnaire as guest  # noqa: E402


def _request_post_creation(
    timeout: float, *, user_confirmed: bool
) -> tuple[dict[str, Any], str | None]:
    """Create one idempotent post job after privately observed project readiness."""
    if not user_confirmed:
        raise guest.GuestQuestionnaireError(
            "Explicit user confirmation is required to create a post"
        )
    with guest._state_lock():
        state = guest._load_state()
        verification = state.get("verification")
        if not isinstance(verification, dict):
            raise guest.GuestQuestionnaireError("No verified project is available")
        if verification.get("status") != "project_ready":
            raise guest.GuestQuestionnaireError(
                "The verified project is not ready for post creation"
            )
        polling_token = verification.get("polling_token")
        if not guest._is_valid_polling_token(polling_token):
            raise guest.GuestQuestionnaireError(
                "Guest questionnaire verification state is invalid"
            )
        assert isinstance(polling_token, str)
        result = guest._validate_verification_status_response(
            guest._request_json(
                "POST",
                "/v1/guest/post-requests",
                verification_token=polling_token,
                body={"api_version": guest.API_VERSION},
                timeout=timeout,
            )
        )
        if result["status"] not in {
            "generating",
            "caption_ready",
            "denied",
            "expired",
            "failed",
        }:
            raise guest.GuestQuestionnaireError(
                "Social Agent API did not accept the post creation request"
            )
    output = guest._safe_output(result, polling_token)
    cleanup_token = (
        polling_token
        if result["status"] in guest.TERMINAL_VERIFICATION_STATUSES
        else None
    )
    return output, cleanup_token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Request Social Agent post creation without exposing private capabilities"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=guest.DEFAULT_TIMEOUT_SECONDS,
        help="request timeout in seconds",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_post = subparsers.add_parser(
        "create-post",
        help="create a post only after the user explicitly requests one",
    )
    create_post.add_argument(
        "--confirm-user-request", action="store_true", required=True
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cleanup_polling_token: str | None = None
    try:
        if args.command == "create-post":
            result, cleanup_polling_token = _request_post_creation(
                args.timeout, user_confirmed=args.confirm_user_request
            )
        else:  # pragma: no cover
            raise guest.GuestQuestionnaireError("Unsupported command")
    except guest.GuestQuestionnaireError as exc:
        print(
            json.dumps(
                {"ok": False, "error": guest._redact_text(str(exc))},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    sys.stdout.flush()
    if cleanup_polling_token is not None:
        try:
            if result.get("status") == "caption_ready":
                guest._forget_state(expected_polling_token=cleanup_polling_token)
            else:
                guest._clear_verification_state(
                    expected_polling_token=cleanup_polling_token
                )
        except guest.GuestQuestionnaireError as exc:
            print(
                json.dumps(
                    {"ok": False, "error": guest._redact_text(str(exc))}
                ),
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
