#!/usr/bin/env python3
"""Restricted guest-questionnaire and Handled-verification client for Social Agent.

The helper talks only to the fixed Social Agent API origin, stores opaque guest
and polling capabilities in a private local state file, and never prints either
private capability. Only the exact server-returned Handled verification URL is
displayable.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import secrets
import stat
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, IO, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]

try:
    import msvcrt
except ImportError:  # pragma: no cover - POSIX fallback
    msvcrt = None  # type: ignore[assignment]

API_VERSION = "2026-07-01"
SKILL_VERSION = "0.6.3"
DEFAULT_API_BASE_URL = "https://social-agent-api.voicevine.ai"
TRUSTED_HANDLED_ORIGIN = "https://handled.voicevine.ai"
TRUSTED_HANDLED_VERIFICATION_PATH = "/social-agent/verify"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_BYTES = 1_048_576
MAX_REQUEST_BYTES = 65_536
MIN_VERIFICATION_REUSE_SECONDS = 60
CUSTOM_ORIGIN_ENV = "SOCIAL_AGENT_ALLOW_CUSTOM_API_BASE_URL"
STATE_FILE_ENV = "SOCIAL_AGENT_GUEST_STATE_FILE"
TRUE_VALUES = {"1", "true", "yes"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
RESUME_TOKEN_PATTERN = re.compile(r"gq_[A-Za-z0-9_-]+")
POLLING_TOKEN_PATTERN = re.compile(r"gvp_[A-Za-z0-9_-]+")
DISPLAY_TOKEN_PATTERN = re.compile(r"gvd_[A-Za-z0-9_-]+")
CONTENT_HASH_PATTERN = re.compile(r"[a-f0-9]{64}")
CREDENTIAL_PATTERN = re.compile(r"sai_[A-Za-z0-9_.-]+")
CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x1f\x7f]")
SENSITIVE_FIELD_PARTS = (
    "authorization",
    "verification",
    "password",
    "secret",
    "token",
    "credential",
    "cookie",
    "api_key",
    "access_key",
    "private_key",
    "oauth_code",
    "authorization_code",
)


class GuestQuestionnaireError(RuntimeError):
    """Safe guest-flow failure that contains no private capability or backend body."""


class VerificationRateLimited(GuestQuestionnaireError):
    """Safe bounded polling delay returned by the hosted API."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Verification was checked too soon")
        self.retry_after_seconds = retry_after_seconds


def _is_valid_resume_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 35 <= len(value) <= 131
        and RESUME_TOKEN_PATTERN.fullmatch(value) is not None
    )


def _is_valid_polling_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 36 <= len(value) <= 132
        and POLLING_TOKEN_PATTERN.fullmatch(value) is not None
    )


def _is_valid_display_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and 36 <= len(value) <= 132
        and DISPLAY_TOKEN_PATTERN.fullmatch(value) is not None
    )


def _contains_sensitive_answer(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _is_sensitive_field(key) or _contains_sensitive_answer(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_answer(item) for item in value)
    if isinstance(value, str):
        return any(
            pattern.search(value) is not None
            for pattern in (RESUME_TOKEN_PATTERN, POLLING_TOKEN_PATTERN, DISPLAY_TOKEN_PATTERN, CREDENTIAL_PATTERN)
        )
    return False


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        return None


def _custom_origin_allowed() -> bool:
    return os.environ.get(CUSTOM_ORIGIN_ENV, "").strip().lower() in TRUE_VALUES


def _validate_api_base_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise GuestQuestionnaireError("SOCIAL_AGENT_API_BASE_URL contains an invalid port") from exc

    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise GuestQuestionnaireError("SOCIAL_AGENT_API_BASE_URL must be an origin without user information")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise GuestQuestionnaireError("SOCIAL_AGENT_API_BASE_URL must not contain a path, query, or fragment")

    production = urlsplit(DEFAULT_API_BASE_URL)
    is_production = (
        parsed.scheme == "https"
        and parsed.hostname.lower() == production.hostname
        and port in (None, 443)
    )
    if is_production:
        return DEFAULT_API_BASE_URL

    is_loopback_http = parsed.scheme == "http" and parsed.hostname.lower() in LOCAL_HOSTS and bool(parsed.netloc)
    if _custom_origin_allowed() and is_loopback_http:
        return value

    raise GuestQuestionnaireError(
        f"SOCIAL_AGENT_API_BASE_URL must use {DEFAULT_API_BASE_URL}; "
        f"{CUSTOM_ORIGIN_ENV}=1 permits only loopback HTTP for controlled development"
    )


def _state_path() -> Path:
    configured = os.environ.get(STATE_FILE_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
    else:
        state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
        path = root / "social-agent" / "guest-questionnaire.json"
    if not path.is_absolute():
        raise GuestQuestionnaireError(f"{STATE_FILE_ENV} must be an absolute path")
    return path


def _validate_private_descriptor(descriptor: int) -> None:
    file_stat = os.fstat(descriptor)
    if not stat.S_ISREG(file_stat.st_mode):
        raise GuestQuestionnaireError("Guest questionnaire state must be a regular file")
    if os.name == "posix" and file_stat.st_mode & 0o077:
        raise GuestQuestionnaireError("Guest questionnaire state permissions must be 0600 or stricter")
    if hasattr(os, "geteuid") and file_stat.st_uid != os.geteuid():
        raise GuestQuestionnaireError("Guest questionnaire state must be owned by the current user")


def _open_state_for_read(path: Path) -> int:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise GuestQuestionnaireError("No resumable guest questionnaire was found; start a new one") from exc


def _load_state() -> dict[str, Any]:
    path = _state_path()
    descriptor = _open_state_for_read(path)
    try:
        _validate_private_descriptor(descriptor)
        with os.fdopen(descriptor, "r", encoding="utf-8") as state_file:
            descriptor = -1
            raw = state_file.read(8193)
    except OSError as exc:
        raise GuestQuestionnaireError("Could not read the guest questionnaire state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(raw) > 8192:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid") from exc
    if not isinstance(parsed, dict) or set(parsed) - {
        "api_version", "api_base_url", "expires_at", "resume_token", "verification"
    }:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")

    token = parsed.get("resume_token")
    base_url = parsed.get("api_base_url")
    expires_at = parsed.get("expires_at")
    if parsed.get("api_version") != API_VERSION:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")
    if not _is_valid_resume_token(token):
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")
    assert isinstance(token, str)
    if not isinstance(base_url, str) or base_url != _api_base_url():
        raise GuestQuestionnaireError("Guest questionnaire state belongs to a different API origin")
    if not isinstance(expires_at, str) or not expires_at:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")

    state: dict[str, Any] = {
        "resume_token": token,
        "api_base_url": base_url,
        "expires_at": expires_at,
    }
    verification = parsed.get("verification")
    if verification is not None:
        legacy_keys = {"polling_token", "expires_at"}
        reusable_keys = legacy_keys | {
            "verification_url", "request_id", "retry_after_seconds"
        }
        ready_legacy_keys = legacy_keys | {"status"}
        ready_keys = reusable_keys | {"status"}
        if not isinstance(verification, dict):
            raise GuestQuestionnaireError("Guest questionnaire verification state is invalid")
        verification_keys = frozenset(verification)
        if verification_keys not in {
            frozenset(legacy_keys), frozenset(reusable_keys),
            frozenset(ready_legacy_keys), frozenset(ready_keys),
        }:
            raise GuestQuestionnaireError("Guest questionnaire verification state is invalid")
        polling_token = verification.get("polling_token")
        verification_expires_at = verification.get("expires_at")
        if not _is_valid_polling_token(polling_token):
            raise GuestQuestionnaireError("Guest questionnaire verification state is invalid")
        stored_verification: dict[str, Any] = {
            "polling_token": polling_token,
            "expires_at": _validate_timestamp(
                verification_expires_at, "verification expiry"
            ),
        }
        if set(verification) in (reusable_keys, ready_keys):
            stored_verification.update(
                {
                    "verification_url": _validate_verification_url(
                        verification.get("verification_url")
                    ),
                    "request_id": _require_public_identifier(
                        verification.get("request_id"), "request ID", maximum=256
                    ),
                    "retry_after_seconds": _validate_retry_after(
                        verification.get("retry_after_seconds"), required=True
                    ),
                }
            )
        if "status" in verification:
            if verification.get("status") != "project_ready":
                raise GuestQuestionnaireError(
                    "Guest questionnaire verification state is invalid"
                )
            stored_verification["status"] = "project_ready"
        state["verification"] = stored_verification
    return state


def _ensure_private_parent(path: Path) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parent_stat = path.parent.stat(follow_symlinks=False)
    if not stat.S_ISDIR(parent_stat.st_mode):
        raise GuestQuestionnaireError("Guest questionnaire state parent must be a directory")
    if hasattr(os, "geteuid") and parent_stat.st_uid != os.geteuid():
        raise GuestQuestionnaireError("Guest questionnaire state parent must be owned by the current user")
    if os.name == "posix" and parent_stat.st_mode & 0o077:
        raise GuestQuestionnaireError("Guest questionnaire state parent permissions must be 0700 or stricter")


def _fsync_parent(path: Path) -> None:
    if os.name != "posix":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path.parent, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _state_lock() -> Any:
    path = _state_path()
    _ensure_private_parent(path)
    lock_path = path.parent / f".{path.name}.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise GuestQuestionnaireError("Could not lock the private guest questionnaire state") from exc
    locked = False
    try:
        _validate_private_descriptor(descriptor)
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        elif msvcrt is not None:  # pragma: no cover - exercised on Windows
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")
                os.fsync(descriptor)
            deadline = time.monotonic() + MAX_TIMEOUT_SECONDS
            while True:
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(  # type: ignore[attr-defined]
                        descriptor, msvcrt.LK_NBLCK, 1  # type: ignore[attr-defined]
                    )
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise GuestQuestionnaireError(
                            "Timed out locking the private guest questionnaire state"
                        ) from exc
                    time.sleep(0.05)
        else:  # pragma: no cover - unsupported Python platform
            raise GuestQuestionnaireError(
                "This platform does not provide a safe private-state lock"
            )
        locked = True
        yield
    finally:
        if locked:
            if fcntl is not None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            elif msvcrt is not None:  # pragma: no cover - exercised on Windows
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(  # type: ignore[attr-defined]
                    descriptor, msvcrt.LK_UNLCK, 1  # type: ignore[attr-defined]
                )
        os.close(descriptor)


def _state_payload(state: dict[str, Any]) -> bytes:
    return json.dumps(
        {
            "api_version": API_VERSION,
            "api_base_url": state["api_base_url"],
            "expires_at": state["expires_at"],
            "resume_token": state["resume_token"],
            **({"verification": state["verification"]} if "verification" in state else {}),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _save_state(*, token: str, expires_at: str, base_url: str) -> None:
    path = _state_path()
    _ensure_private_parent(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    payload = _state_payload(
        {"api_version": API_VERSION, "api_base_url": base_url, "expires_at": expires_at, "resume_token": token}
    )
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise GuestQuestionnaireError("A guest questionnaire is already saved; resume or forget it first") from exc
    except OSError as exc:
        raise GuestQuestionnaireError("Could not create the private guest questionnaire state") from exc
    try:
        with os.fdopen(descriptor, "wb") as state_file:
            descriptor = -1
            state_file.write(payload)
            state_file.flush()
            os.fsync(state_file.fileno())
        _fsync_parent(path)
    except OSError as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise GuestQuestionnaireError("Could not save the guest questionnaire state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_state(state: dict[str, Any]) -> None:
    path = _state_path()
    _ensure_private_parent(path)
    payload = _state_payload(state)
    if len(payload) > 8192:
        raise GuestQuestionnaireError("Guest questionnaire state is invalid")
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = -1
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as state_file:
            descriptor = -1
            state_file.write(payload)
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary, path)
        _fsync_parent(path)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise GuestQuestionnaireError("Could not update the private guest questionnaire state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _forget_state_unlocked(*, expected_polling_token: str | None = None) -> None:
    path = _state_path()
    try:
        state = _load_state()
    except GuestQuestionnaireError:
        if not path.exists() and not path.is_symlink():
            return
        raise
    if expected_polling_token is not None:
        verification = state.get("verification")
        current = verification.get("polling_token") if isinstance(verification, dict) else None
        if not secrets.compare_digest(str(current), expected_polling_token):
            raise GuestQuestionnaireError("Verification state changed; newer private state was preserved")
    try:
        path.unlink()
        _fsync_parent(path)
    except OSError as exc:
        raise GuestQuestionnaireError("Could not remove the guest questionnaire state") from exc


def _forget_state(*, expected_polling_token: str | None = None) -> None:
    with _state_lock():
        _forget_state_unlocked(expected_polling_token=expected_polling_token)


def _clear_verification_state(*, expected_polling_token: str) -> None:
    with _state_lock():
        state = _load_state()
        verification = state.get("verification")
        current = verification.get("polling_token") if isinstance(verification, dict) else None
        if not secrets.compare_digest(str(current), expected_polling_token):
            raise GuestQuestionnaireError("Verification state changed; newer private state was preserved")
        state.pop("verification", None)
        _replace_state(state)


def _api_base_url() -> str:
    return _validate_api_base_url(os.environ.get("SOCIAL_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL))


def _request_timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > MAX_TIMEOUT_SECONDS:
        raise GuestQuestionnaireError(
            f"Timeout must be greater than 0 and no more than {MAX_TIMEOUT_SECONDS:g} seconds"
        )
    return value


def _read_limited(response: Any) -> bytes:
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise GuestQuestionnaireError("Social Agent API response exceeded the safe size limit")
    return payload


def _redact_text(value: str, token: str | None = None) -> str:
    if token:
        value = value.replace(token, "[REDACTED]")
    value = RESUME_TOKEN_PATTERN.sub("[REDACTED]", value)
    value = POLLING_TOKEN_PATTERN.sub("[REDACTED]", value)
    value = DISPLAY_TOKEN_PATTERN.sub("[REDACTED]", value)
    return CREDENTIAL_PATTERN.sub("[REDACTED]", value)


def _is_sensitive_field(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return any(part in normalized for part in SENSITIVE_FIELD_PARTS)


def _safe_output(value: Any, token: str | None = None) -> Any:
    if isinstance(value, dict):
        output: dict[object, Any] = {}
        for key, item in value.items():
            safe_key: object = _redact_text(key, token) if isinstance(key, str) else key
            safe_item = "[REDACTED]" if _is_sensitive_field(key) else _safe_output(item, token)
            if safe_key in output:
                safe_key = "[REDACTED_DUPLICATE_KEY]"
            output[safe_key] = safe_item
        return output
    if isinstance(value, list):
        return [_safe_output(item, token) for item in value]
    if isinstance(value, str):
        return _redact_text(value, token)
    return value


def _request_json(
    method: str,
    path: str,
    *,
    token: str | None = None,
    verification_token: str | None = None,
    recovery_contract: bool = False,
    body: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if token is not None and verification_token is not None:
        raise GuestQuestionnaireError("Only one private capability may be sent per request")
    base_url = _api_base_url()
    url = f"{base_url}/{path.lstrip('/')}"
    encoded_body = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    if encoded_body is not None and len(encoded_body) > MAX_REQUEST_BYTES:
        raise GuestQuestionnaireError("Guest questionnaire answer exceeded the safe size limit")
    headers = {
        "Accept": "application/json",
        "User-Agent": f"social-agent-public-workflows-guest/{SKILL_VERSION}",
    }
    if token:
        if not _is_valid_resume_token(token):
            raise GuestQuestionnaireError("Guest questionnaire state is invalid")
        headers["X-Guest-Resume-Token"] = token
    if verification_token:
        if not _is_valid_polling_token(verification_token):
            raise GuestQuestionnaireError("Guest questionnaire verification state is invalid")
        headers["X-Guest-Verification-Token"] = verification_token
    if recovery_contract:
        if verification_token is None:
            raise GuestQuestionnaireError(
                "Recovery contract requires a private verification capability"
            )
        headers["X-Guest-Recovery-Contract"] = "1"
    if encoded_body is not None:
        headers["Content-Type"] = "application/json"

    request = Request(url, data=encoded_body, headers=headers, method=method.upper())
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:
            response_payload = _read_limited(response)
    except HTTPError as exc:
        _read_limited(exc)
        if exc.code == 429 and verification_token is not None:
            retry_raw = exc.headers.get("Retry-After", "")
            if retry_raw.isdigit():
                retry_after = int(retry_raw)
                if 1 <= retry_after <= 30:
                    raise VerificationRateLimited(retry_after) from exc
        raise GuestQuestionnaireError(f"Social Agent API returned HTTP {exc.code}") from exc
    except URLError as exc:
        private_token = verification_token or token
        reason = _redact_text(str(exc.reason), private_token)
        raise GuestQuestionnaireError(f"Could not reach the Social Agent API: {reason}") from exc

    try:
        parsed = json.loads(response_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuestQuestionnaireError("Social Agent API returned an invalid JSON response") from exc
    if not isinstance(parsed, dict):
        raise GuestQuestionnaireError("Social Agent API returned an unexpected JSON response")
    return parsed


def _require_nonempty_string(value: object, field: str, *, maximum: int = 4096) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or CONTROL_CHARACTER_PATTERN.search(value)
    ):
        raise GuestQuestionnaireError(f"Social Agent API returned an invalid {field}")
    return value


def _require_public_identifier(value: object, field: str, *, maximum: int = 256) -> str:
    identifier = _require_nonempty_string(value, field, maximum=maximum)
    if any(
        pattern.search(identifier) is not None
        for pattern in (RESUME_TOKEN_PATTERN, POLLING_TOKEN_PATTERN, DISPLAY_TOKEN_PATTERN, CREDENTIAL_PATTERN)
    ):
        raise GuestQuestionnaireError(f"Social Agent API returned an invalid {field}")
    return identifier


def _validate_questionnaire_response(result: dict[str, Any], *, expect_token: bool) -> dict[str, Any]:
    if result.get("api_version") != API_VERSION:
        raise GuestQuestionnaireError("Social Agent API returned an unsupported API version")
    _require_public_identifier(result.get("request_id"), "request ID", maximum=256)
    _require_nonempty_string(result.get("expires_at"), "guest expiry", maximum=128)

    token = result.get("resume_token")
    if expect_token:
        if not _is_valid_resume_token(token):
            raise GuestQuestionnaireError("Social Agent API did not return a valid guest resume token")
    elif token is not None:
        raise GuestQuestionnaireError("Social Agent API unexpectedly returned a new guest resume token")

    questionnaire = result.get("questionnaire")
    if not isinstance(questionnaire, dict):
        raise GuestQuestionnaireError("Social Agent API returned an invalid questionnaire")
    _require_nonempty_string(questionnaire.get("workflow_key"), "workflow key", maximum=120)
    version = questionnaire.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise GuestQuestionnaireError("Social Agent API returned an invalid workflow version")
    _require_nonempty_string(questionnaire.get("session_id"), "questionnaire session", maximum=256)
    status = questionnaire.get("status")
    completed = questionnaire.get("completed")
    if status not in {"in_progress", "completed"} or not isinstance(completed, bool):
        raise GuestQuestionnaireError("Social Agent API returned an invalid questionnaire status")
    if completed != (status == "completed"):
        raise GuestQuestionnaireError("Social Agent API returned inconsistent questionnaire completion state")
    if not isinstance(questionnaire.get("answers"), dict) or not isinstance(
        questionnaire.get("completed_steps"), list
    ):
        raise GuestQuestionnaireError("Social Agent API returned invalid questionnaire progress")

    _require_nonempty_string(questionnaire.get("next_action"), "next action")
    if completed:
        if "question" in questionnaire and questionnaire["question"] is not None:
            raise GuestQuestionnaireError("Social Agent API returned a question for a completed questionnaire")
    else:
        question = questionnaire.get("question")
        if not isinstance(question, dict):
            raise GuestQuestionnaireError("Social Agent API did not return the current questionnaire step")
        _require_nonempty_string(question.get("step_key"), "step key", maximum=120)
        _require_nonempty_string(question.get("question"), "question text")
        options = question.get("options")
        if options is not None and not isinstance(options, list):
            raise GuestQuestionnaireError("Social Agent API returned invalid question options")
    return result


def _validate_timestamp(value: object, field: str, *, must_be_future: bool = False) -> str:
    timestamp = _require_nonempty_string(value, field, maximum=128)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GuestQuestionnaireError(f"Social Agent API returned an invalid {field}") from exc
    if parsed.tzinfo is None:
        raise GuestQuestionnaireError(f"Social Agent API returned an invalid {field}")
    if must_be_future:
        now = datetime.now(timezone.utc)
        normalized = parsed.astimezone(timezone.utc)
        if normalized <= now or normalized > now + timedelta(days=1):
            raise GuestQuestionnaireError(f"Social Agent API returned an invalid {field}")
    return timestamp


def _validate_retry_after(value: object, *, required: bool) -> int | None:
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 30:
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification retry interval")
    return value


def _validate_verification_url(value: object) -> str:
    url = _require_nonempty_string(value, "Handled verification URL", maximum=512)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "handled.voicevine.ai"
        or parsed.hostname != "handled.voicevine.ai"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.path != TRUSTED_HANDLED_VERIFICATION_PATH
        or parsed.query
        or not _is_valid_display_token(parsed.fragment)
    ):
        raise GuestQuestionnaireError("Social Agent API returned an invalid Handled verification URL")
    return url


def _validate_verification_create_response(result: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "api_version", "request_id", "status", "verification_url", "polling_token",
        "expires_at", "retry_after_seconds",
    }
    if set(result) != expected or result.get("api_version") != API_VERSION:
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification response")
    request_id = _require_public_identifier(result.get("request_id"), "request ID", maximum=256)
    if result.get("status") != "pending_login":
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification status")
    verification_url = _validate_verification_url(result.get("verification_url"))
    polling_token = result.get("polling_token")
    if not _is_valid_polling_token(polling_token):
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification polling capability")
    assert isinstance(polling_token, str)
    expires_at = _validate_timestamp(
        result.get("expires_at"), "verification expiry", must_be_future=True
    )
    retry_after = _validate_retry_after(result.get("retry_after_seconds"), required=True)
    return {
        "api_version": API_VERSION,
        "request_id": request_id,
        "status": "pending_login",
        "verification_url": verification_url,
        "polling_token": polling_token,
        "expires_at": expires_at,
        "retry_after_seconds": retry_after,
    }


POLLING_VERIFICATION_STATUSES = {
    "pending_login", "pending_subscription", "pending_entitlement_confirmation",
    "pending_consent", "claiming", "generating",
}
ACTIONABLE_VERIFICATION_STATUSES = {"project_ready"}
TERMINAL_VERIFICATION_STATUSES = {"caption_ready", "denied", "expired", "failed"}
VERIFICATION_CLEANUP_STATUSES = {"caption_ready", "denied", "expired"}
ALLOWED_WORKER_DIAGNOSTICS = {
    "generation_failed",
    "hermes_executable_unavailable",
    "hermes_subprocess_unavailable",
    "provider_authentication_failed",
    "provider_permanent_error",
    "provider_policy_refusal",
}


def _validate_verification_status_response(result: dict[str, Any]) -> dict[str, Any]:
    required = {"api_version", "request_id", "status", "expires_at", "retry_after_seconds"}
    optional = {"caption", "content_hash", "worker_diagnostic"}
    if not required.issubset(result) or set(result) - required - optional or result.get("api_version") != API_VERSION:
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification status response")
    request_id = _require_public_identifier(result.get("request_id"), "request ID", maximum=256)
    status = result.get("status")
    allowed_statuses = (
        POLLING_VERIFICATION_STATUSES
        | ACTIONABLE_VERIFICATION_STATUSES
        | TERMINAL_VERIFICATION_STATUSES
    )
    if not isinstance(status, str) or status not in allowed_statuses:
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification status")
    expires_at = _validate_timestamp(
        result.get("expires_at"),
        "verification expiry",
        must_be_future=status in POLLING_VERIFICATION_STATUSES | ACTIONABLE_VERIFICATION_STATUSES,
    )
    retry_after = _validate_retry_after(
        result.get("retry_after_seconds"), required=status in POLLING_VERIFICATION_STATUSES
    )
    if status in ACTIONABLE_VERIFICATION_STATUSES | TERMINAL_VERIFICATION_STATUSES and retry_after is not None:
        raise GuestQuestionnaireError("Social Agent API returned an invalid verification retry interval")
    caption = result.get("caption")
    content_hash = result.get("content_hash")
    worker_diagnostic = result.get("worker_diagnostic")
    if status == "caption_ready":
        if (
            not isinstance(caption, str)
            or not 1 <= len(caption) <= 10_000
            or any(ord(character) < 32 and character not in "\n\r\t" for character in caption)
            or not isinstance(content_hash, str)
            or CONTENT_HASH_PATTERN.fullmatch(content_hash) is None
            or retry_after is not None
        ):
            raise GuestQuestionnaireError("Social Agent API returned invalid configured caption proof")
    elif caption is not None or content_hash is not None:
        raise GuestQuestionnaireError("Social Agent API returned unexpected configured caption data")
    if status == "failed" and worker_diagnostic is not None:
        worker_diagnostic = _require_public_identifier(
            worker_diagnostic, "worker diagnostic", maximum=64
        )
        if worker_diagnostic not in ALLOWED_WORKER_DIAGNOSTICS:
            raise GuestQuestionnaireError(
                "Social Agent API returned an invalid worker diagnostic"
            )
    elif worker_diagnostic is not None:
        raise GuestQuestionnaireError(
            "Social Agent API returned an unexpected worker diagnostic"
        )
    return {
        "api_version": API_VERSION,
        "request_id": request_id,
        "status": status,
        "expires_at": expires_at,
        "retry_after_seconds": retry_after,
        **({"caption": caption, "content_hash": content_hash} if status == "caption_ready" else {}),
        **(
            {"worker_diagnostic": worker_diagnostic}
            if status == "failed" and worker_diagnostic is not None
            else {}
        ),
    }


def _json_value(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc.msg}") from exc


def _start(timeout: float) -> dict[str, Any]:
    path = _state_path()
    if path.exists() or path.is_symlink():
        raise GuestQuestionnaireError("A guest questionnaire is already saved; resume or forget it first")
    result = _validate_questionnaire_response(
        _request_json("POST", "/v1/guest/questionnaire", timeout=timeout), expect_token=True
    )
    token = result.get("resume_token")
    expires_at = result.get("expires_at")
    if not _is_valid_resume_token(token):
        raise GuestQuestionnaireError("Social Agent API did not return a valid guest resume token")
    assert isinstance(token, str)  # narrowed by _is_valid_resume_token
    if not isinstance(expires_at, str) or not expires_at:
        raise GuestQuestionnaireError("Social Agent API did not return a valid guest expiry")
    _save_state(token=token, expires_at=expires_at, base_url=_api_base_url())
    output = _safe_output(result, token)
    output["resume_saved"] = True
    return output


def _resume(timeout: float) -> dict[str, Any]:
    state = _load_state()
    result = _validate_questionnaire_response(
        _request_json("GET", "/v1/guest/questionnaire", token=state["resume_token"], timeout=timeout),
        expect_token=False,
    )
    return _safe_output(result, state["resume_token"])


def _answer(*, step_key: str, answer: Any, timeout: float) -> dict[str, Any]:
    if not 1 <= len(step_key) <= 120 or CONTROL_CHARACTER_PATTERN.search(step_key):
        raise GuestQuestionnaireError("The server-returned step key is invalid")
    if not isinstance(answer, dict):
        raise GuestQuestionnaireError("Guest questionnaire answers must be JSON objects")
    if _contains_sensitive_answer(answer):
        raise GuestQuestionnaireError("Guest questionnaire answers must not contain credentials or sensitive fields")
    state = _load_state()
    result = _validate_questionnaire_response(
        _request_json(
            "POST",
            "/v1/guest/questionnaire/answer",
            token=state["resume_token"],
            body={"api_version": API_VERSION, "step_key": step_key, "answer": answer},
            timeout=timeout,
        ),
        expect_token=False,
    )
    return _safe_output(result, state["resume_token"])


def _reusable_verification_result(verification: object) -> dict[str, Any] | None:
    if not isinstance(verification, dict) or "verification_url" not in verification:
        return None
    try:
        expires_at = datetime.fromisoformat(
            str(verification["expires_at"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None
    now = datetime.now(timezone.utc)
    if not now + timedelta(seconds=MIN_VERIFICATION_REUSE_SECONDS) < expires_at <= now + timedelta(days=1):
        return None
    if verification.get("status") == "project_ready":
        return {
            "api_version": API_VERSION,
            "request_id": verification["request_id"],
            "status": "project_ready",
            "expires_at": verification["expires_at"],
            "retry_after_seconds": None,
            "verification_saved": True,
        }
    return {
        "api_version": API_VERSION,
        "request_id": verification["request_id"],
        "status": "pending_login",
        "verification_url": verification["verification_url"],
        "expires_at": verification["expires_at"],
        "retry_after_seconds": verification["retry_after_seconds"],
        "verification_saved": True,
    }


def _verify(timeout: float) -> dict[str, Any]:
    with _state_lock():
        state = _load_state()
        reusable = _reusable_verification_result(state.get("verification"))
        if reusable is not None:
            return reusable
        result = _validate_verification_create_response(
            _request_json(
                "POST",
                "/v1/guest/questionnaire/verification",
                token=state["resume_token"],
                timeout=timeout,
            )
        )
        polling_token = result["polling_token"]
        assert isinstance(polling_token, str)
        state["verification"] = {
            "polling_token": polling_token,
            "expires_at": result["expires_at"],
            "verification_url": result["verification_url"],
            "request_id": result["request_id"],
            "retry_after_seconds": result["retry_after_seconds"],
        }
        _replace_state(state)
    return {
        "api_version": result["api_version"],
        "request_id": result["request_id"],
        "status": result["status"],
        "verification_url": result["verification_url"],
        "expires_at": result["expires_at"],
        "retry_after_seconds": result["retry_after_seconds"],
        "verification_saved": True,
    }


def _poll_verification(timeout: float) -> tuple[dict[str, Any], str | None]:
    with _state_lock():
        state = _load_state()
        verification = state.get("verification")
        if not isinstance(verification, dict):
            raise GuestQuestionnaireError("No private verification session was found; create one first")
        polling_token = verification.get("polling_token")
        if not _is_valid_polling_token(polling_token):
            raise GuestQuestionnaireError("Guest questionnaire verification state is invalid")
        assert isinstance(polling_token, str)
        try:
            response = _request_json(
                "GET",
                "/v1/guest/questionnaire/verification/status",
                verification_token=polling_token,
                recovery_contract=True,
                timeout=timeout,
            )
        except VerificationRateLimited as exc:
            return (
                {
                    "api_version": API_VERSION,
                    "status": "rate_limited",
                    "retry_after_seconds": exc.retry_after_seconds,
                },
                None,
            )
        result = _validate_verification_status_response(response)
        if result["status"] == "project_ready":
            verification["status"] = "project_ready"
            state["verification"] = verification
            _replace_state(state)
    output = _safe_output(result, polling_token)
    cleanup_token = polling_token if result["status"] in VERIFICATION_CLEANUP_STATUSES else None
    return output, cleanup_token


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Social Agent guest onboarding and Handled verification without exposing private capabilities"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="request timeout in seconds")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="start a guest questionnaire and save its resume token privately")
    subparsers.add_parser("resume", help="read the current server-owned questionnaire state")
    answer = subparsers.add_parser("answer", help="submit an answer for the current server-returned step")
    answer.add_argument("--step-key", required=True)
    answer.add_argument("--answer-json", type=_json_value, required=True)
    subparsers.add_parser("verify", help="create or safely reuse a Handled verification session")
    subparsers.add_parser("poll-verification", help="read the saved verification session status privately")
    subparsers.add_parser("forget", help="discard all local guest state only when explicitly requested")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cleanup_polling_token: str | None = None
    try:
        if args.command == "start":
            result = _start(args.timeout)
        elif args.command == "resume":
            result = _resume(args.timeout)
        elif args.command == "answer":
            result = _answer(step_key=args.step_key, answer=args.answer_json, timeout=args.timeout)
        elif args.command == "verify":
            result = _verify(args.timeout)
        elif args.command == "poll-verification":
            result, cleanup_polling_token = _poll_verification(args.timeout)
        elif args.command == "forget":
            _forget_state()
            result = {"forgotten": True}
        else:  # pragma: no cover
            raise GuestQuestionnaireError("Unsupported command")
    except GuestQuestionnaireError as exc:
        print(json.dumps({"ok": False, "error": _redact_text(str(exc))}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    sys.stdout.flush()
    if cleanup_polling_token is not None:
        try:
            if result.get("status") == "caption_ready":
                _forget_state(expected_polling_token=cleanup_polling_token)
            else:
                _clear_verification_state(expected_polling_token=cleanup_polling_token)
        except GuestQuestionnaireError as exc:
            print(json.dumps({"ok": False, "error": _redact_text(str(exc))}), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
