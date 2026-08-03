#!/usr/bin/env python3
"""Dependency-light client for the hosted Social Agent API.

This helper intentionally exposes only workspace-credential routes. Operator
bootstrap and administrative credential issuance do not belong in this public
skill.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import stat
import sys
import tempfile
import zlib
from collections.abc import Sequence
from pathlib import Path
from typing import IO, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import UUID

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import skill_updater as _skill_updater  # noqa: E402

API_VERSION = "2026-07-01"
SKILL_VERSION = "0.6.9"
DEFAULT_API_BASE_URL = "https://social-agent-api.voicevine.ai"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_BYTES = 1_048_576
MAX_ASSET_PREVIEW_BYTES = 25 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 25 * 1024 * 1024
IMAGE_MEDIA_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
CUSTOM_ORIGIN_ENV = "SOCIAL_AGENT_ALLOW_CUSTOM_API_BASE_URL"
TRUE_VALUES = {"1", "true", "yes"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
CREDENTIAL_PATTERN = re.compile(r"sai_[A-Za-z0-9_-]{8,64}\.[A-Za-z0-9_-]{43,256}")
SAFE_ERROR_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
SAFE_FIELD_ERROR_CODE_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
MAX_SAFE_ERROR_MESSAGE_LENGTH = 2_000
MAX_SAFE_FIELD_NAME_LENGTH = 67
MAX_SAFE_FIELD_ERRORS = 100
MAX_SAFE_EXPECTED_VALUES = 20
MAX_SAFE_EXPECTED_VALUE_LENGTH = 128
SENSITIVE_FIELD_PARTS = (
    "authorization",
    "password",
    "secret",
    "token",
    "credential",
    "cookie",
    "api_key",
    "access_key",
    "private_key",
    "signed_url",
    "activation_url",
    "connect_url",
    "oauth_url",
    "oauth_code",
    "authorization_code",
    "callback_url",
    "redirect_url",
)
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
    "list_posts",
    "approve_or_reject",
    "connect_destination",
    "schedule_posts",
    "check_status",
)


class SocialAgentAPIError(RuntimeError):
    """Safe, credential-redacted API failure."""

    def __init__(
        self,
        message: str,
        *,
        server_code: str | None = None,
        field_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.server_code = server_code
        self.field_errors = field_errors or []


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so Authorization never crosses an origin boundary."""

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


def _redact(value: str, credential: str | None = None) -> str:
    if credential:
        value = value.replace(credential, "[REDACTED]")
    return CREDENTIAL_PATTERN.sub("[REDACTED]", value)


def _is_sensitive_field(key: object) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
    return any(part in normalized for part in SENSITIVE_FIELD_PARTS)


def _redact_json(value: Any, credential: str) -> Any:
    if isinstance(value, dict):
        redacted: dict[object, Any] = {}
        for key, item in value.items():
            safe_key: object = _redact(key, credential) if isinstance(key, str) else key
            safe_value = "[REDACTED]" if _is_sensitive_field(key) else _redact_json(item, credential)
            if safe_key in redacted:
                safe_key = "[REDACTED_DUPLICATE_KEY]"
            redacted[safe_key] = safe_value
        return redacted
    if isinstance(value, list):
        return [_redact_json(item, credential) for item in value]
    if isinstance(value, str):
        return _redact(value, credential)
    return value


def _custom_origin_allowed() -> bool:
    return os.environ.get(CUSTOM_ORIGIN_ENV, "").strip().lower() in TRUE_VALUES


def _validate_api_base_url(raw_url: str) -> str:
    value = raw_url.strip().rstrip("/")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise SocialAgentAPIError("SOCIAL_AGENT_API_BASE_URL contains an invalid port") from exc

    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise SocialAgentAPIError("SOCIAL_AGENT_API_BASE_URL must be an origin without user information")
    if parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise SocialAgentAPIError("SOCIAL_AGENT_API_BASE_URL must not contain a path, query, or fragment")

    production = urlsplit(DEFAULT_API_BASE_URL)
    is_production = (
        parsed.scheme == "https"
        and parsed.hostname.lower() == production.hostname
        and port in (None, 443)
    )
    if is_production:
        return DEFAULT_API_BASE_URL

    is_loopback_http = parsed.scheme == "http" and parsed.hostname.lower() in LOCAL_HOSTS and parsed.netloc
    is_custom_https = parsed.scheme == "https" and parsed.netloc
    if _custom_origin_allowed() and (is_loopback_http or is_custom_https):
        return value

    raise SocialAgentAPIError(
        f"SOCIAL_AGENT_API_BASE_URL must use {DEFAULT_API_BASE_URL}; "
        f"set {CUSTOM_ORIGIN_ENV}=1 only for controlled development"
    )


def _read_credential_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SocialAgentAPIError(f"Cannot open SOCIAL_AGENT_API_KEY_FILE: {_redact(str(exc))}") from exc

    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise SocialAgentAPIError("SOCIAL_AGENT_API_KEY_FILE must point to a regular file")
        if os.name == "posix" and file_stat.st_mode & 0o077:
            raise SocialAgentAPIError("SOCIAL_AGENT_API_KEY_FILE permissions must be 0600 or stricter")
        if hasattr(os, "geteuid") and file_stat.st_uid != os.geteuid():
            raise SocialAgentAPIError("SOCIAL_AGENT_API_KEY_FILE must be owned by the current user")
        with os.fdopen(descriptor, "r", encoding="utf-8") as credential_file:
            descriptor = -1
            return credential_file.read(4097).strip()
    except OSError as exc:
        raise SocialAgentAPIError(f"Cannot read SOCIAL_AGENT_API_KEY_FILE: {_redact(str(exc))}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _load_signin_access_token() -> str:
    try:
        from signin import SignInError, load_access_token
    except ImportError:  # pragma: no cover - helper always ships alongside
        raise SocialAgentAPIError(
            "Set SOCIAL_AGENT_API_KEY or SOCIAL_AGENT_API_KEY_FILE to a workspace-scoped Social Agent credential"
        ) from None
    try:
        return load_access_token()
    except SignInError as exc:
        raise SocialAgentAPIError(str(exc)) from exc


def load_api_key(*, allow_signin: bool = True) -> str:
    credential = os.environ.get("SOCIAL_AGENT_API_KEY", "").strip()
    if not credential:
        credential_file = os.environ.get("SOCIAL_AGENT_API_KEY_FILE", "").strip()
        if credential_file:
            credential = _read_credential_file(credential_file)
    if credential:
        if CREDENTIAL_PATTERN.fullmatch(credential) is None:
            raise SocialAgentAPIError("The configured Social Agent credential has an invalid format")
        return credential
    if not allow_signin:
        raise SocialAgentAPIError(
            "Private sign-in credentials may only be used with the production Social Agent API"
        )
    # No provisioned credential. Fall back to a signed-in user's OAuth token,
    # read from private state rather than passed in, so a token never has to
    # travel through an argument, an environment dump, or the conversation.
    return _load_signin_access_token()


def _read_limited(response: Any) -> bytes:
    payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SocialAgentAPIError("Social Agent API response exceeded the safe size limit")
    return payload


def _safe_printable_string(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    if not all(character.isprintable() for character in value):
        return None
    return value


def _safe_expected_value(value: object) -> object | None:
    if isinstance(value, str):
        return _safe_printable_string(value, maximum=MAX_SAFE_EXPECTED_VALUE_LENGTH)
    if value is None or isinstance(value, bool | int):
        return value
    return None


def _safe_contract_field_errors(error: dict[str, Any]) -> list[dict[str, Any]]:
    details = error.get("details")
    if not isinstance(details, dict):
        return []
    raw_errors = details.get("errors")
    if not isinstance(raw_errors, list) or len(raw_errors) > MAX_SAFE_FIELD_ERRORS:
        return []

    safe_errors: list[dict[str, Any]] = []
    for raw_error in raw_errors:
        if not isinstance(raw_error, dict):
            continue
        field = _safe_printable_string(raw_error.get("field"), maximum=MAX_SAFE_FIELD_NAME_LENGTH)
        code = raw_error.get("code")
        if field is None or not isinstance(code, str) or SAFE_FIELD_ERROR_CODE_PATTERN.fullmatch(code) is None:
            continue
        safe_error: dict[str, Any] = {"field": field, "code": code}
        for key in ("expected", "allowed"):
            raw_expected = raw_error.get(key)
            if not isinstance(raw_expected, list) or len(raw_expected) > MAX_SAFE_EXPECTED_VALUES:
                continue
            expected = [_safe_expected_value(item) for item in raw_expected]
            if all(item is not None for item in expected):
                safe_error[key] = expected
        safe_errors.append(safe_error)
    return safe_errors


def _safe_server_error(payload: bytes) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None, []
    if not isinstance(parsed, dict):
        return None, None, []
    error = parsed.get("error")
    if not isinstance(error, dict):
        return None, None, []
    code = error.get("code")
    if not isinstance(code, str) or SAFE_ERROR_CODE_PATTERN.fullmatch(code) is None:
        return None, None, []
    if code != "JOB_INPUT_CONTRACT_VIOLATION":
        return code, None, []
    message = _safe_printable_string(error.get("message"), maximum=MAX_SAFE_ERROR_MESSAGE_LENGTH)
    return code, message, _safe_contract_field_errors(error)


def _request_timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0 or value > MAX_TIMEOUT_SECONDS:
        raise SocialAgentAPIError(f"Timeout must be greater than 0 and no more than {MAX_TIMEOUT_SECONDS:g} seconds")
    return value


def request_json(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    base_url = _validate_api_base_url(os.environ.get("SOCIAL_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL))
    credential = load_api_key(allow_signin=base_url == DEFAULT_API_BASE_URL)
    url = f"{base_url}/{path.lstrip('/')}"
    encoded_body = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {credential}",
        "User-Agent": f"social-agent-public-workflows/{SKILL_VERSION}",
    }
    if encoded_body is not None:
        headers["Content-Type"] = "application/json"

    request = Request(url, data=encoded_body, headers=headers, method=method.upper())
    opener = build_opener(_NoRedirectHandler())
    _skill_updater.maybe_update_and_reexec(reason="before_api")
    try:
        with opener.open(request, timeout=_request_timeout(timeout)) as response:
            response_payload = _read_limited(response)
    except HTTPError as exc:
        _skill_updater.maybe_check_after_api_failure(exc)
        response_payload = _read_limited(exc)
        server_code, server_message, field_errors = _safe_server_error(response_payload)
        redacted_field_errors = _redact_json(field_errors, credential)
        if not isinstance(redacted_field_errors, list):  # pragma: no cover - list in, list out
            redacted_field_errors = []
        suffix = f" ({server_code})" if server_code else ""
        message = f"Social Agent API returned HTTP {exc.code}{suffix}"
        if server_message:
            message = f"{message}: {_redact(server_message, credential)}"
        if redacted_field_errors:
            encoded_errors = json.dumps(
                redacted_field_errors, ensure_ascii=False, separators=(",", ":")
            )
            message = f"{message} Field errors: {encoded_errors}"
        raise SocialAgentAPIError(
            message,
            server_code=server_code,
            field_errors=redacted_field_errors,
        ) from exc
    except URLError as exc:
        _skill_updater.maybe_check_after_api_failure(exc)
        reason = _redact(str(exc.reason), credential)
        raise SocialAgentAPIError(f"Could not reach the Social Agent API: {reason}") from exc

    try:
        parsed = json.loads(response_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SocialAgentAPIError("Social Agent API returned an invalid JSON response") from exc
    if not isinstance(parsed, dict):
        raise SocialAgentAPIError("Social Agent API returned an unexpected JSON response")
    return _redact_json(parsed, credential)


def _validated_asset_id(asset_id: str) -> str:
    try:
        return str(UUID(asset_id))
    except ValueError as exc:
        raise SocialAgentAPIError("Asset ID must be a UUID") from exc


def _read_preview_bytes(response: Any) -> bytes:
    payload = response.read(MAX_ASSET_PREVIEW_BYTES + 1)
    if len(payload) > MAX_ASSET_PREVIEW_BYTES:
        raise SocialAgentAPIError("Image preview exceeded the safe size limit")
    return payload


def _validate_png(payload: bytes) -> bool:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset = 8
    saw_ihdr = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            return False
        size = int.from_bytes(payload[offset:offset + 4], "big")
        chunk_type = payload[offset + 4:offset + 8]
        chunk_end = offset + 12 + size
        if chunk_end > len(payload):
            return False
        chunk = payload[offset + 8:offset + 8 + size]
        expected_crc = int.from_bytes(payload[offset + 8 + size:chunk_end], "big")
        if zlib.crc32(chunk_type + chunk) & 0xFFFFFFFF != expected_crc:
            return False
        if not saw_ihdr:
            if chunk_type != b"IHDR" or size != 13:
                return False
            saw_ihdr = True
        if chunk_type == b"IEND":
            return saw_ihdr and size == 0 and chunk_end == len(payload)
        offset = chunk_end
    return False


def _validate_jpeg(payload: bytes) -> bool:
    if len(payload) < 4 or not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        return False
    offset = 2
    saw_frame = False
    while offset < len(payload) - 1:
        if payload[offset] != 0xFF:
            return False
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            return False
        marker = payload[offset]
        offset += 1
        if marker == 0xD9:
            return offset == len(payload)
        if marker == 0xDA:
            return saw_frame
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if offset + 2 > len(payload):
            return False
        size = int.from_bytes(payload[offset:offset + 2], "big")
        if size < 2 or offset + size > len(payload):
            return False
        if marker in {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}:
            saw_frame = True
        offset += size
    return False


def _validate_webp(payload: bytes) -> bool:
    if len(payload) < 20 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        return False
    if int.from_bytes(payload[4:8], "little") != len(payload) - 8:
        return False
    offset = 12
    saw_image_chunk = False
    while offset < len(payload):
        if offset + 8 > len(payload):
            return False
        chunk_type = payload[offset:offset + 4]
        size = int.from_bytes(payload[offset + 4:offset + 8], "little")
        chunk_end = offset + 8 + size
        if chunk_end > len(payload):
            return False
        if chunk_type in {b"VP8 ", b"VP8L", b"VP8X"}:
            saw_image_chunk = True
        offset = chunk_end + (size % 2)
    return saw_image_chunk and offset == len(payload)


def _validate_preview_image(media_type: str, payload: bytes) -> None:
    validators = {
        "image/png": _validate_png,
        "image/jpeg": _validate_jpeg,
        "image/webp": _validate_webp,
    }
    if not payload or not validators[media_type](payload):
        raise SocialAgentAPIError("Social Agent API returned an invalid image preview")


def _read_upload_image(path: Path) -> bytes:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise SocialAgentAPIError("Image upload path must be a readable regular file") from exc
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise SocialAgentAPIError("Image upload path must be a readable regular file")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            payload = handle.read(MAX_IMAGE_UPLOAD_BYTES + 1)
    except OSError as exc:
        raise SocialAgentAPIError("Could not read image upload") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(payload) > MAX_IMAGE_UPLOAD_BYTES:
        raise SocialAgentAPIError("Image upload exceeded the safe size limit")
    if not any(validator(payload) for validator in (_validate_png, _validate_jpeg, _validate_webp)):
        raise SocialAgentAPIError("Image upload must be a valid PNG, JPEG, or WebP file")
    return payload


def upload_project_image(
    project_reference_id: str,
    image_path: Path,
    *,
    exact_post_media: bool,
    role: str,
    display_name: str | None,
    timeout: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "data_base64": base64.b64encode(_read_upload_image(image_path)).decode("ascii"),
        "role": role,
    }
    if display_name:
        payload["display_name"] = display_name
    collection = "post-media" if exact_post_media else "visual-assets"
    project = quote(project_reference_id, safe="")
    return request_json("POST", f"/v1/projects/{project}/{collection}", body=payload, timeout=timeout)


def _write_private_preview(output: Path, payload: bytes) -> None:
    parent = output.parent
    if not parent.is_dir():
        raise SocialAgentAPIError("Preview output directory does not exist")
    if output.exists() and output.is_symlink():
        raise SocialAgentAPIError("Preview output must not be a symbolic link")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=parent)
    temporary_path = Path(temporary)
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
        os.replace(temporary_path, output)
        if os.name == "posix":
            output.chmod(0o600)
    except OSError as exc:
        raise SocialAgentAPIError("Could not save image preview") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


def fetch_asset_preview(asset_id: str, output: Path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, object]:
    """Fetch one authorized image rendition to a private local file.

    The endpoint is derived from an opaque asset ID rather than accepted as an
    arbitrary URL, so a bearer credential cannot be redirected to another host.
    """
    normalized_id = _validated_asset_id(asset_id)
    base_url = _validate_api_base_url(os.environ.get("SOCIAL_AGENT_API_BASE_URL", DEFAULT_API_BASE_URL))
    credential = load_api_key(allow_signin=base_url == DEFAULT_API_BASE_URL)
    request = Request(
        f"{base_url}/v1/assets/{normalized_id}/preview",
        headers={
            "Accept": ", ".join(sorted(IMAGE_MEDIA_TYPES)),
            "Authorization": f"Bearer {credential}",
            "User-Agent": f"social-agent-public-workflows/{SKILL_VERSION}",
        },
        method="GET",
    )
    try:
        with build_opener(_NoRedirectHandler()).open(request, timeout=_request_timeout(timeout)) as response:
            media_type = response.headers.get_content_type().lower()
            if media_type not in IMAGE_MEDIA_TYPES:
                raise SocialAgentAPIError("Social Agent API returned an unsupported image preview")
            payload = _read_preview_bytes(response)
            _validate_preview_image(media_type, payload)
    except HTTPError as exc:
        try:
            _read_limited(exc)
        except SocialAgentAPIError:
            pass
        raise SocialAgentAPIError("Image preview is unavailable") from exc
    except URLError as exc:
        raise SocialAgentAPIError(f"Could not reach the Social Agent API: {_redact(str(exc.reason), credential)}") from exc
    _write_private_preview(output, payload)
    return {"asset_id": normalized_id, "mime_type": media_type, "byte_size": len(payload)}


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
    job_contracts = subparsers.add_parser(
        "job-contracts",
        help="read what a job type's inputs must contain, before sending one",
    )
    job_contracts.add_argument(
        "--job-type",
        choices=JOB_TYPES,
        help="one job type; omit for every published contract",
    )
    subparsers.add_parser("projects", help="list projects visible to the credential")

    create_job = subparsers.add_parser("create-job", help="submit a deterministic job packet")
    create_job.add_argument("--job-type", choices=JOB_TYPES, required=True)
    create_job.add_argument("--idempotency-key", required=True)
    create_job.add_argument(
        "--project-reference-id",
        help="project slug from the projects list, not its id",
    )
    create_job.add_argument("--inputs-json", type=_json_object, default={})

    job_status = subparsers.add_parser("job-status", help="read one job by its server ID")
    job_status.add_argument("job_id")
    asset_preview = subparsers.add_parser("asset-preview", help="retrieve one authorized rendered image to a private local file")
    asset_preview.add_argument("--asset-id", required=True)
    asset_preview.add_argument("--output", type=Path, required=True)
    asset_preview_link = subparsers.add_parser(
        "asset-preview-link",
        help="mint one short-lived rendered image capability for native attachment delivery",
    )
    asset_preview_link.add_argument("--asset-id", required=True)
    for command, help_text in (
        ("upload-visual", "upload one private reusable project image"),
        ("upload-post-media", "upload one exact image for a future post"),
    ):
        upload = subparsers.add_parser(command, help=help_text)
        upload.add_argument("--project-reference-id", required=True)
        upload.add_argument("--image", type=Path, required=True)
        upload.add_argument(
            "--role",
            choices=("logo", "template", "palette", "product", "product_screenshot", "style_example", "scene", "texture"),
            default="style_example",
        )
        upload.add_argument("--display-name")
    visual_assets = subparsers.add_parser("visual-assets", help="list reusable project images")
    visual_assets.add_argument("--project-reference-id", required=True)
    visual_lifecycle = subparsers.add_parser("visual-lifecycle", help="activate or archive a reviewed reusable image")
    visual_lifecycle.add_argument("--project-reference-id", required=True)
    visual_lifecycle.add_argument("--asset-id", required=True)
    visual_lifecycle.add_argument("--action", choices=("activate", "archive"), required=True)
    visual_lifecycle.add_argument("--asset-kind", choices=("reference", "background"))
    post_media = subparsers.add_parser("post-media", help="list exact future-post images")
    post_media.add_argument("--project-reference-id", required=True)
    post_media_action = subparsers.add_parser("post-media-action", help="attach or archive exact future-post media")
    post_media_action.add_argument("--project-reference-id", required=True)
    post_media_action.add_argument("--asset-id", required=True)
    post_media_action.add_argument("--action", choices=("attach", "archive"), required=True)
    post_media_action.add_argument("--content-version-id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "capabilities":
            result = request_json("GET", "/v1/capabilities", timeout=args.timeout)
        elif args.command == "job-contracts":
            path = "/v1/job-contracts"
            if args.job_type:
                path = f"{path}/{quote(args.job_type, safe='')}"
            result = request_json("GET", path, timeout=args.timeout)
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
        elif args.command == "asset-preview":
            result = fetch_asset_preview(args.asset_id, args.output, timeout=args.timeout)
        elif args.command == "asset-preview-link":
            asset_id = _validated_asset_id(args.asset_id)
            result = request_json(
                "POST", f"/v1/assets/{quote(asset_id, safe='')}/preview-capabilities", timeout=args.timeout
            )
        elif args.command in {"upload-visual", "upload-post-media"}:
            result = upload_project_image(
                args.project_reference_id,
                args.image,
                exact_post_media=args.command == "upload-post-media",
                role=args.role,
                display_name=args.display_name,
                timeout=args.timeout,
            )
        elif args.command in {"visual-assets", "post-media"}:
            project = quote(args.project_reference_id, safe="")
            result = request_json("GET", f"/v1/projects/{project}/{args.command}", timeout=args.timeout)
        elif args.command == "visual-lifecycle":
            project = quote(args.project_reference_id, safe="")
            asset_id = _validated_asset_id(args.asset_id)
            body = {"action": args.action}
            if args.asset_kind:
                body["asset_kind"] = args.asset_kind
            result = request_json(
                "POST",
                f"/v1/projects/{project}/visual-assets/{asset_id}/lifecycle",
                body=body,
                timeout=args.timeout,
            )
        elif args.command == "post-media-action":
            project = quote(args.project_reference_id, safe="")
            asset_id = _validated_asset_id(args.asset_id)
            if args.action == "attach" and not args.content_version_id:
                raise SocialAgentAPIError("Attaching post media requires a content version ID")
            body = {"content_version_id": args.content_version_id} if args.action == "attach" else None
            result = request_json(
                "POST",
                f"/v1/projects/{project}/post-media/{asset_id}/{args.action}",
                body=body,
                timeout=args.timeout,
            )
        else:  # pragma: no cover
            raise SocialAgentAPIError("Unsupported command")
    except SocialAgentAPIError as exc:
        failure: dict[str, Any] = {"ok": False, "error": str(exc)}
        if args.command == "create-job" and exc.server_code == "JOB_INPUT_CONTRACT_VIOLATION":
            contract_path = f"/v1/job-contracts/{quote(args.job_type, safe='')}"
            try:
                failure["job_contract"] = request_json("GET", contract_path, timeout=args.timeout)
            except SocialAgentAPIError as contract_exc:
                failure["job_contract_error"] = str(contract_exc)
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
