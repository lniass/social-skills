#!/usr/bin/env python3
"""Sign a returning user back into their existing Social Agent project.

Guest onboarding is one-time: it clears its own private state on success. An
agent that later loses that state has no credential and no route back to a
project that already exists -- and re-running onboarding makes things worse,
because each new questionnaire invalidates the verification link the user was
sent. Observed with a real user whose workspace, project, cadence, publisher
credential, and drafted posts were all healthy and entirely unreachable.

This helper is that route back. It performs OAuth authorization-code with PKCE
against the authorization server the API itself names, then keeps the refresh
token in private local state so the browser step happens once per install
rather than once per session.

Two rules shape every design decision here:

* **Tokens never enter the conversation.** Not printed, not returned, not put in
  an argument. `token` deliberately has no output mode that emits one; other
  helpers read the private state file instead.
* **Registration is not authentication.** A stored `client_id` proves nothing.
  The affected user had exactly that and no token, which is why their agent
  correctly reported it could not sign in.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SKILL_VERSION = "0.4.0"
DEFAULT_API_BASE_URL = "https://social-agent-api.voicevine.ai"
CUSTOM_ORIGIN_ENV = "SOCIAL_AGENT_ALLOW_CUSTOM_API_BASE_URL"
STATE_FILE_ENV = "SOCIAL_AGENT_SIGNIN_STATE_FILE"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RESPONSE_BYTES = 262_144
MAX_STATE_BYTES = 16_384
TRUE_VALUES = {"1", "true", "yes"}

#: Refresh this far before actual expiry. A token that expires mid-request is
#: indistinguishable from a revoked one at the call site, and retrying a
#: mutating call to find out is exactly what must not happen.
REFRESH_SKEW_SECONDS = 120

#: The browser lands on the API itself, which parks the authorization code for
#: the waiting agent to collect. An earlier version redirected to a loopback
#: address nothing could listen on, so the person had to copy a long URL back
#: into chat -- which is where the attempt died on a phone, and which broke the
#: rule the rest of this product follows: show a link, then poll privately.
#:
#: Only the code crosses that server, never a token. PKCE makes a code useless
#: without the verifier, and the verifier never leaves this machine.
CALLBACK_PATH = "/v1/signin/callback"

#: How long to keep waiting for the person to finish in their browser.
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 900

CLIENT_NAME = "Social Agent public workflows"


class SignInError(Exception):
    """Safe, user-presentable failure. Never carries a token or a raw body."""


# --------------------------------------------------------------------------
# Private state
# --------------------------------------------------------------------------


def _state_path() -> Path:
    configured = os.environ.get(STATE_FILE_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
    else:
        state_home = os.environ.get("XDG_STATE_HOME", "").strip()
        root = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
        path = root / "social-agent" / "signin.json"
    if not path.is_absolute():
        raise SignInError(f"{STATE_FILE_ENV} must be an absolute path")
    return path


def _validate_private_descriptor(descriptor: int) -> None:
    file_stat = os.fstat(descriptor)
    if not stat.S_ISREG(file_stat.st_mode):
        raise SignInError("Sign-in state must be a regular file")
    if os.name == "posix" and file_stat.st_mode & 0o077:
        raise SignInError("Sign-in state permissions must be 0600 or stricter")
    if hasattr(os, "geteuid") and file_stat.st_uid != os.geteuid():
        raise SignInError("Sign-in state must be owned by the current user")


def _load_state() -> dict[str, Any]:
    path = _state_path()
    flags = os.O_RDONLY
    for name in ("O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, name, 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return {}
    try:
        _validate_private_descriptor(descriptor)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            raw = handle.read(MAX_STATE_BYTES + 1)
    except OSError as exc:
        raise SignInError("Could not read the sign-in state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > MAX_STATE_BYTES:
        raise SignInError("Sign-in state is invalid")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SignInError("Sign-in state is invalid") from exc
    if not isinstance(parsed, dict):
        raise SignInError("Sign-in state is invalid")
    return parsed


def _save_state(state: dict[str, Any]) -> None:
    """Write 0600, atomically, never following a symlink.

    Created with O_EXCL at a temporary name and renamed, so a pre-existing
    symlink cannot redirect the write and a crash cannot leave a half-written
    file holding a partial refresh token.
    """
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(state, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(payload) > MAX_STATE_BYTES:
        raise SignInError("Sign-in state is too large to store")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    for name in ("O_CLOEXEC", "O_NOFOLLOW"):
        flags |= getattr(os, name, 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise SignInError("Could not store the sign-in state") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists():
            temporary.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so a token request cannot cross an origin boundary."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D102
        return None


def _api_base_url() -> str:
    configured = os.environ.get("SOCIAL_AGENT_API_BASE_URL", "").strip()
    if not configured:
        return DEFAULT_API_BASE_URL
    if os.environ.get(CUSTOM_ORIGIN_ENV, "").strip().lower() not in TRUE_VALUES:
        raise SignInError("A custom API base URL is not permitted in this runtime")
    return configured.rstrip("/")


def _https_only(url: str, *, what: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise SignInError(f"{what} must be an https URL")
    return url


def _get_json(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": f"social-agent-public-workflows/{SKILL_VERSION}",
        },
        method="GET",
    )
    return _send(request, timeout=timeout)


def _post_form(
    url: str, form: dict[str, str], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    request = Request(
        url,
        data=urlencode(form).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"social-agent-public-workflows/{SKILL_VERSION}",
        },
        method="POST",
    )
    return _send(request, timeout=timeout)


def _post_json(
    url: str, body: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT_SECONDS
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": f"social-agent-public-workflows/{SKILL_VERSION}",
        },
        method="POST",
    )
    return _send(request, timeout=timeout)


def _send(request: Request, *, timeout: float) -> dict[str, Any]:
    opener = build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # Deliberately drops the body. An OAuth error body can echo the code or
        # the redirect, and nothing here needs it to explain the failure.
        raise SignInError(f"Sign-in request failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise SignInError("Could not reach the sign-in service") from exc
    if len(payload) > MAX_RESPONSE_BYTES:
        raise SignInError("Sign-in response exceeded the safe size limit")
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignInError("Sign-in response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise SignInError("Sign-in response was not valid JSON")
    return parsed


# --------------------------------------------------------------------------
# Discovery and registration
# --------------------------------------------------------------------------


def _discover() -> dict[str, Any]:
    """Ask the API which authorization server protects it, then ask that server.

    Discovery starts at the resource rather than at a hardcoded issuer so a
    returning agent needs to know only the API it already talks to.
    """
    resource = _get_json(
        _https_only(
            f"{_api_base_url()}/.well-known/oauth-protected-resource",
            what="API base URL",
        )
    )
    servers = resource.get("authorization_servers")
    if not isinstance(servers, list) or not servers:
        raise SignInError("This deployment does not advertise an authorization server")
    issuer = _https_only(str(servers[0]).rstrip("/"), what="Authorization server")
    metadata = _get_json(f"{issuer}/.well-known/oauth-authorization-server")
    for required in ("authorization_endpoint", "token_endpoint"):
        value = metadata.get(required)
        if not isinstance(value, str) or not value:
            raise SignInError(f"Authorization server metadata is missing {required}")
        _https_only(value, what=required)
    return {
        "issuer": issuer,
        "authorization_endpoint": metadata["authorization_endpoint"],
        "token_endpoint": metadata["token_endpoint"],
        "registration_endpoint": metadata.get("registration_endpoint"),
    }


def _client_id(state: dict[str, Any], metadata: dict[str, Any], redirect_uri: str) -> str:
    existing = state.get("client_id")
    if isinstance(existing, str) and existing:
        return existing
    endpoint = metadata.get("registration_endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise SignInError("This authorization server does not support client registration")
    registered = _post_json(
        _https_only(endpoint, what="Registration endpoint"),
        {
            "client_name": CLIENT_NAME,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "application_type": "native",
        },
    )
    client_id = registered.get("client_id")
    if not isinstance(client_id, str) or not client_id:
        raise SignInError("Client registration did not return a client id")
    state["client_id"] = client_id
    state["redirect_uri"] = redirect_uri
    _save_state(state)
    return client_id


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode("ascii").rstrip("=")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


def command_start(args: argparse.Namespace) -> dict[str, Any]:
    """Begin sign-in and return the URL the user should open."""
    state = _load_state()
    metadata = _discover()
    redirect_uri = args.redirect_uri or f"{_api_base_url()}{CALLBACK_PATH}"
    # A client registered against a different redirect cannot be reused: the
    # authorization server matches the redirect exactly, so a stale
    # registration would fail at the least helpful moment.
    if state.get("redirect_uri") != redirect_uri:
        state.pop("client_id", None)
    client_id = _client_id(state, metadata, redirect_uri)
    handoff = _post_json(f"{_api_base_url()}/v1/signin/sessions", {})
    session_ref = str(handoff.get("session_ref") or "")
    poll_token = str(handoff.get("poll_token") or "")
    if not session_ref or not poll_token:
        raise SignInError("The sign-in service did not start a session")
    verifier, challenge = _pkce_pair()
    # The session reference doubles as the OAuth state: the callback needs it to
    # find the session, and it is unguessable, so it serves both purposes.
    csrf = session_ref
    # The verifier never leaves this machine and the state value is compared on
    # return, so an authorization response captured from somewhere else cannot
    # be redeemed here.
    state["pending"] = {
        "code_verifier": verifier,
        "state": csrf,
        "poll_token": poll_token,
        "redirect_uri": redirect_uri,
        "token_endpoint": metadata["token_endpoint"],
        "created_at": int(time.time()),
    }
    _save_state(state)
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": csrf,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "openid profile email",
        }
    )
    endpoint = urlsplit(metadata["authorization_endpoint"])
    return {
        "status": "awaiting_user",
        # Built with urlunsplit rather than concatenation so an endpoint that
        # already carries a query is extended instead of corrupted.
        "authorization_url": urlunsplit(
            (endpoint.scheme, endpoint.netloc, endpoint.path, query, "")
        ),
        "next_action": (
            "Present this to the user as a tappable markdown hyperlink, not as "
            "bare text and not inside backticks -- a raw URL is not tappable in "
            "most chat clients, and on a phone the user would have to select a "
            "long string by hand. Then run `signin wait`, which completes on its "
            "own once they finish in the browser. Never ask the user to copy "
            "anything back."
        ),
    }


def command_wait(args: argparse.Namespace) -> dict[str, Any]:
    """Wait for the person to finish in their browser, then complete sign-in.

    Polls a server that holds only the authorization code. The token exchange
    happens here, with the verifier that never left this machine -- so nothing
    in the middle of this flow ever holds anything that could be used as the
    user's account.
    """
    state = _load_state()
    pending = state.get("pending")
    if not isinstance(pending, dict):
        raise SignInError("No sign-in is in progress; run `signin start` first")

    session_ref = str(pending.get("state", ""))
    poll_token = str(pending.get("poll_token", ""))
    if not session_ref or not poll_token:
        raise SignInError("This sign-in cannot be resumed; run `signin start` again")

    # `or` would be wrong here: a deliberate 0 is falsy, and turning "check
    # once and return" into a fifteen-minute wait is the kind of surprise that
    # only shows up as a hang.
    requested = getattr(args, "timeout_seconds", None)
    deadline = time.time() + float(
        POLL_TIMEOUT_SECONDS if requested is None else max(0.0, float(requested))
    )
    claim_url = f"{_api_base_url()}/v1/signin/sessions/{session_ref}/claim"
    while True:
        result = _post_json(claim_url, {"poll_token": poll_token})
        status = str(result.get("status") or "")
        if status == "ready":
            code = str(result.get("authorization_code") or "")
            if not code:
                raise SignInError("The sign-in service returned no authorization code")
            return _exchange(state, pending, code)
        if status == "failed":
            state.pop("pending", None)
            _save_state(state)
            raise SignInError(
                f"Sign-in was not completed ({result.get('error_code') or 'unknown'})"
            )
        if status == "expired":
            state.pop("pending", None)
            _save_state(state)
            raise SignInError("This sign-in expired before it was completed")
        if time.time() >= deadline:
            # The pending request is preserved: the person may still be
            # mid-browser, and discarding it would waste a completed sign-in.
            raise SignInError("Still waiting for sign-in to be completed")
        time.sleep(POLL_INTERVAL_SECONDS)


def _exchange(
    state: dict[str, Any], pending: dict[str, Any], code: str
) -> dict[str, Any]:
    tokens = _post_form(
        # Re-validated on the way out, not trusted because it was validated on
        # the way in. This is the one field that decides where a code and,
        # subsequently, a refresh token are sent.
        _https_only(str(pending["token_endpoint"]), what="Token endpoint"),
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": str(pending["redirect_uri"]),
            "client_id": str(state.get("client_id", "")),
            "code_verifier": str(pending["code_verifier"]),
        },
    )
    _store_tokens(state, tokens)
    state.pop("pending", None)
    _save_state(state)
    return {
        "status": "signed_in",
        "expires_in_seconds": int(tokens.get("expires_in") or 0),
        "next_action": (
            "Signed in. The user's existing project is reachable now; list "
            "their prepared posts and schedule rather than starting a new "
            "questionnaire."
        ),
    }


def _store_tokens(state: dict[str, Any], tokens: dict[str, Any]) -> None:
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise SignInError("The authorization server did not return an access token")
    state["access_token"] = access
    expires_in = tokens.get("expires_in")
    state["access_expires_at"] = int(time.time()) + (
        int(expires_in) if isinstance(expires_in, (int, float)) else 3600
    )
    refresh = tokens.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        # Rotation-safe: a refresh response that omits the token means keep the
        # old one, and dropping it here would silently force a browser sign-in
        # on the next call.
        state["refresh_token"] = refresh


def load_access_token() -> str:
    """Return a usable access token, refreshing silently when needed.

    Importable by the other helpers so a token is read from private state
    rather than passed around. Raises rather than returning an expired token:
    a caller that retries a mutating request to discover expiry is exactly the
    behaviour this avoids.
    """
    state = _load_state()
    token = state.get("access_token")
    expires_at = state.get("access_expires_at")
    if (
        isinstance(token, str)
        and token
        and isinstance(expires_at, int)
        and expires_at - REFRESH_SKEW_SECONDS > int(time.time())
    ):
        return token
    refresh = state.get("refresh_token")
    if not isinstance(refresh, str) or not refresh:
        raise SignInError("Not signed in; run `signin start`")
    metadata = _discover()
    tokens = _post_form(
        _https_only(metadata["token_endpoint"], what="Token endpoint"),
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": str(state.get("client_id", "")),
        },
    )
    _store_tokens(state, tokens)
    _save_state(state)
    return str(state["access_token"])


def command_status(_: argparse.Namespace) -> dict[str, Any]:
    """Report whether sign-in is usable, without revealing anything about it."""
    state = _load_state()
    has_refresh = isinstance(state.get("refresh_token"), str) and bool(state["refresh_token"])
    expires_at = state.get("access_expires_at")
    access_valid = (
        isinstance(expires_at, int)
        and expires_at - REFRESH_SKEW_SECONDS > int(time.time())
        and isinstance(state.get("access_token"), str)
    )
    return {
        "registered": isinstance(state.get("client_id"), str) and bool(state["client_id"]),
        # Registration alone is not sign-in. Reported separately because
        # conflating them is what made a registered-but-tokenless install look
        # authenticated.
        "signed_in": has_refresh or access_valid,
        "access_token_valid": access_valid,
        "sign_in_in_progress": isinstance(state.get("pending"), dict),
    }


def command_refresh(_: argparse.Namespace) -> dict[str, Any]:
    load_access_token()
    return {"status": "refreshed"}


def command_forget(_: argparse.Namespace) -> dict[str, Any]:
    """Discard tokens. Keeps the client registration, which is not a secret."""
    state = _load_state()
    for key in ("access_token", "access_expires_at", "refresh_token", "pending"):
        state.pop(key, None)
    _save_state(state)
    return {"status": "forgotten"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sign a returning user into their existing Social Agent project"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Begin sign-in and return the URL to open")
    start.add_argument("--redirect-uri", default=None)
    start.set_defaults(handler=command_start)

    wait = subparsers.add_parser("wait", help="Wait for the user to finish signing in")
    wait.add_argument("--timeout-seconds", type=int, default=POLL_TIMEOUT_SECONDS)
    wait.set_defaults(handler=command_wait)

    for name, handler, help_text in (
        ("status", command_status, "Report whether sign-in is usable"),
        ("refresh", command_refresh, "Refresh the access token now"),
        ("forget", command_forget, "Discard stored tokens"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = args.handler(args)
    except SignInError as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
