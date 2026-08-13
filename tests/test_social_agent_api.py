from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "social-agent-public-workflows"
    / "scripts"
    / "social_agent_api.py"
)
SPEC = importlib.util.spec_from_file_location("social_agent_api", SCRIPT_PATH)
assert SPEC and SPEC.loader
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)

TEST_KEY = "sai_testkey1." + "x" * 43
ASSET_ID = "11111111-1111-4111-8111-111111111111"
CUSTOM_ENV = api.CUSTOM_ORIGIN_ENV


def local_environment(base_url: str) -> dict[str, str]:
    return {
        "SOCIAL_AGENT_API_KEY": TEST_KEY,
        "SOCIAL_AGENT_API_BASE_URL": base_url,
        CUSTOM_ENV: "1",
    }


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    response_status = 200
    response_body: dict[str, object] = {"ok": True}
    response_raw_body: bytes | None = None
    response_content_type = "application/json"

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b""
        body = json.loads(raw_body) if raw_body else None
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "accept": self.headers.get("Accept"),
                "user_agent": self.headers.get("User-Agent"),
                "body": body,
            }
        )
        encoded = self.__class__.response_raw_body
        if encoded is None:
            encoded = json.dumps(self.__class__.response_body).encode("utf-8")
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", self.__class__.response_content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            pass

    do_GET = _handle
    do_POST = _handle

    def log_message(self, format: str, *args: object) -> None:
        return None


class LocalServer:
    def __enter__(self) -> str:
        RecordingHandler.requests = []
        RecordingHandler.response_status = 200
        RecordingHandler.response_body = {"ok": True}
        RecordingHandler.response_raw_body = None
        RecordingHandler.response_content_type = "application/json"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class SocialAgentAPITests(unittest.TestCase):
    def test_default_api_base_url_uses_current_production_hostname(self) -> None:
        self.assertEqual(api.DEFAULT_API_BASE_URL, "https://social-agent-api.voicevine.ai")

    def test_job_allowlist_matches_hosted_api_contract(self) -> None:
        self.assertEqual(
            set(api.JOB_TYPES),
            {
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
                "regenerate_asset",
                "connect_destination",
                "schedule_posts",
                "check_status",
            },
        )

    def test_capabilities_uses_workspace_bearer_credential(self) -> None:
        with (
            LocalServer() as base_url,
            patch.dict(os.environ, local_environment(base_url), clear=True),
            patch.object(api._skill_updater, "maybe_update_and_reexec") as update_check,
        ):
            result = api.request_json("GET", "/v1/capabilities")

        update_check.assert_called_once_with(reason="before_api")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(RecordingHandler.requests), 1)
        request = RecordingHandler.requests[0]
        self.assertEqual(request["method"], "GET")
        self.assertEqual(request["path"], "/v1/capabilities")
        self.assertEqual(request["authorization"], f"Bearer {TEST_KEY}")
        self.assertEqual(request["user_agent"], "social-agent-public-workflows/0.6.19")
        self.assertIsNone(request["body"])

    def test_create_job_cli_sends_versioned_job_packet(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = api.main(
                    [
                        "create-job",
                        "--job-type",
                        "get_next_question",
                        "--idempotency-key",
                        "question-demo-001",
                        "--project-reference-id",
                        "demo-project",
                        "--inputs-json",
                        "{}",
                    ]
                )

        self.assertEqual(exit_code, 0)
        request = RecordingHandler.requests[0]
        self.assertEqual(request["path"], "/v1/jobs")
        self.assertEqual(
            request["body"],
            {
                "api_version": "2026-07-01",
                "job_type": "get_next_question",
                "idempotency_key": "question-demo-001",
                "project_reference_id": "demo-project",
                "inputs": {},
            },
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True})

    def test_asset_preview_link_mints_capability_with_workspace_bearer_credential(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            RecordingHandler.response_body = {
                "preview_url": "https://social-agent-api.voicevine.ai/v1/asset-previews/cap_example",
                "expires_at": "2026-08-02T00:10:00+00:00",
            }
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = api.main(["asset-preview-link", "--asset-id", ASSET_ID])

        self.assertEqual(exit_code, 0)
        self.assertEqual(RecordingHandler.requests[0]["method"], "POST")
        self.assertEqual(
            RecordingHandler.requests[0]["path"],
            f"/v1/assets/{ASSET_ID}/preview-capabilities",
        )
        self.assertEqual(RecordingHandler.requests[0]["authorization"], f"Bearer {TEST_KEY}")
        self.assertEqual(json.loads(stdout.getvalue())["preview_url"], RecordingHandler.response_body["preview_url"])

    def test_upload_visual_sends_validated_private_image(self) -> None:
        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            return len(data).to_bytes(4, "big") + chunk_type + data + zlib.crc32(chunk_type + data).to_bytes(4, "big")

        image = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00")
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
            + chunk(b"IEND", b"")
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.png"
            source.write_bytes(image)
            with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
                result = api.upload_project_image(
                    "demo project",
                    source,
                    exact_post_media=False,
                    role="product",
                    display_name="Demo",
                    timeout=30,
                )

        self.assertEqual(result, {"ok": True})
        request = RecordingHandler.requests[0]
        self.assertEqual(request["path"], "/v1/projects/demo%20project/visual-assets")
        body = request["body"]
        self.assertIsInstance(body, dict)
        assert isinstance(body, dict)
        self.assertEqual(body["role"], "product")
        self.assertEqual(body["display_name"], "Demo")
        self.assertEqual(base64.b64decode(body["data_base64"]), image)

    def test_upload_rejects_invalid_or_symbolic_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bad.png"
            source.write_bytes(b"not-an-image")
            with self.assertRaisesRegex(api.SocialAgentAPIError, "valid PNG"):
                api._read_upload_image(source)
            link = Path(directory) / "link.png"
            link.symlink_to(source)
            with self.assertRaisesRegex(api.SocialAgentAPIError, "regular file"):
                api._read_upload_image(link)

    def test_asset_preview_fetches_private_image_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.png"
            def chunk(chunk_type: bytes, data: bytes) -> bytes:
                return len(data).to_bytes(4, "big") + chunk_type + data + zlib.crc32(chunk_type + data).to_bytes(4, "big")

            image = (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00")
                + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
                + chunk(b"IEND", b"")
            )
            with LocalServer() as base_url:
                RecordingHandler.response_raw_body = image
                RecordingHandler.response_content_type = "image/png"
                with patch.dict(os.environ, local_environment(base_url), clear=True):
                    result = api.fetch_asset_preview(ASSET_ID, output)
            self.assertEqual(output.read_bytes(), image)
            self.assertEqual(result["mime_type"], "image/png")
            self.assertEqual(result["byte_size"], len(image))
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        request = RecordingHandler.requests[0]
        self.assertEqual(request["path"], f"/v1/assets/{ASSET_ID}/preview")
        self.assertEqual(request["authorization"], f"Bearer {TEST_KEY}")
        self.assertEqual(request["accept"], "image/jpeg, image/png, image/webp")

    def test_asset_preview_rejects_non_image_and_backend_detail(self) -> None:
        with tempfile.TemporaryDirectory() as directory, LocalServer() as base_url:
            output = Path(directory) / "review.png"
            RecordingHandler.response_status = 503
            RecordingHandler.response_body = {"error": {"message": "bucket private-path provider-secret"}}
            with patch.dict(os.environ, local_environment(base_url), clear=True):
                with self.assertRaisesRegex(api.SocialAgentAPIError, "Image preview is unavailable") as caught:
                    api.fetch_asset_preview(ASSET_ID, output)
        self.assertFalse(output.exists())
        self.assertNotIn("bucket", str(caught.exception))
        self.assertNotIn("provider", str(caught.exception))

    def test_asset_preview_rejects_mismatched_image_payload_and_invalid_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory, LocalServer() as base_url:
            output = Path(directory) / "review.png"
            RecordingHandler.response_raw_body = b"not-an-image"
            RecordingHandler.response_content_type = "image/png"
            with patch.dict(os.environ, local_environment(base_url), clear=True):
                with self.assertRaisesRegex(api.SocialAgentAPIError, "invalid image preview"):
                    api.fetch_asset_preview(ASSET_ID, output)
            self.assertFalse(output.exists())
            with self.assertRaisesRegex(api.SocialAgentAPIError, "Asset ID must be a UUID"):
                api.fetch_asset_preview("not-an-asset", output)

    def test_custom_origin_requires_explicit_development_override(self) -> None:
        with patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": "https://staging.example.com"},
            clear=True,
        ):
            with self.assertRaisesRegex(api.SocialAgentAPIError, CUSTOM_ENV):
                api.request_json("GET", "/v1/capabilities")

    def test_private_signin_token_is_refused_for_custom_origin(self) -> None:
        environment = {
            "SOCIAL_AGENT_API_BASE_URL": "https://staging.example.com",
            CUSTOM_ENV: "1",
        }
        with patch.dict(os.environ, environment, clear=True), patch.object(
            api, "_load_signin_access_token", return_value="oauth-private-token"
        ) as load_signin:
            with self.assertRaisesRegex(api.SocialAgentAPIError, "only be used with the production"):
                api.request_json("GET", "/v1/capabilities")
            with self.assertRaisesRegex(api.SocialAgentAPIError, "only be used with the production"):
                api.fetch_asset_preview(ASSET_ID, Path("/tmp/unreachable-preview.png"))
        load_signin.assert_not_called()

    def test_public_http_api_url_is_rejected_even_with_override(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SOCIAL_AGENT_API_KEY": TEST_KEY,
                "SOCIAL_AGENT_API_BASE_URL": "http://api.example.com",
                CUSTOM_ENV: "1",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(api.SocialAgentAPIError, api.DEFAULT_API_BASE_URL):
                api.request_json("GET", "/v1/capabilities")

    def test_base_url_rejects_userinfo_path_query_and_fragment(self) -> None:
        invalid_urls = (
            "https://user:password@social-agent-api.voicevine.ai",
            "https://social-agent-api.voicevine.ai/v1",
            "https://social-agent-api.voicevine.ai?next=evil",
            "https://social-agent-api.voicevine.ai#fragment",
        )
        for invalid_url in invalid_urls:
            with self.subTest(invalid_url=invalid_url), patch.dict(
                os.environ,
                {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": invalid_url},
                clear=True,
            ):
                with self.assertRaises(api.SocialAgentAPIError):
                    api.request_json("GET", "/v1/capabilities")

    def test_cross_origin_redirect_is_rejected_without_forwarding_authorization(self) -> None:
        received_authorization: list[str | None] = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                received_authorization.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return None

        class RedirectHandler(BaseHTTPRequestHandler):
            target_url = ""

            def do_GET(self) -> None:
                self.send_response(302)
                self.send_header("Location", self.__class__.target_url)
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return None

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        RedirectHandler.target_url = f"http://127.0.0.1:{target.server_port}/capture"
        threads = [
            threading.Thread(target=target.serve_forever, daemon=True),
            threading.Thread(target=redirect.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            base_url = f"http://127.0.0.1:{redirect.server_port}"
            with patch.dict(os.environ, local_environment(base_url), clear=True):
                with self.assertRaisesRegex(api.SocialAgentAPIError, "HTTP 302"):
                    api.request_json("GET", "/v1/capabilities")
        finally:
            redirect.shutdown()
            target.shutdown()
            redirect.server_close()
            target.server_close()
            for thread in threads:
                thread.join(timeout=2)

        self.assertEqual(received_authorization, [])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "requires POSIX no-follow support")
    def test_credential_file_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "credential.target"
            link = Path(directory) / "credential.link"
            target.write_text(TEST_KEY, encoding="utf-8")
            target.chmod(0o600)
            link.symlink_to(target)
            with patch.dict(os.environ, {"SOCIAL_AGENT_API_KEY_FILE": str(link)}, clear=True):
                with self.assertRaisesRegex(api.SocialAgentAPIError, "Cannot open"):
                    api.load_api_key()

    def test_credential_file_must_be_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "social-agent.key"
            path.write_text(TEST_KEY, encoding="utf-8")
            path.chmod(0o644)
            with patch.dict(os.environ, {"SOCIAL_AGENT_API_KEY_FILE": str(path)}, clear=True):
                with self.assertRaisesRegex(api.SocialAgentAPIError, "0600"):
                    api.load_api_key()

            path.chmod(0o600)
            with patch.dict(os.environ, {"SOCIAL_AGENT_API_KEY_FILE": str(path)}, clear=True):
                self.assertEqual(api.load_api_key(), TEST_KEY)

    def test_http_error_does_not_reproduce_backend_body(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            RecordingHandler.response_status = 400
            RecordingHandler.response_body = {
                "error": {"code": "INVALID_REQUEST", "message": f"private backend detail {TEST_KEY}"}
            }
            with self.assertRaises(api.SocialAgentAPIError) as caught:
                api.request_json("GET", "/v1/capabilities")

        message = str(caught.exception)
        self.assertEqual(message, "Social Agent API returned HTTP 400 (INVALID_REQUEST)")
        self.assertNotIn(TEST_KEY, message)
        self.assertNotIn("private backend detail", message)

    def test_contract_violation_surfaces_safe_message_and_field_errors(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            RecordingHandler.response_status = 422
            RecordingHandler.response_body = {
                "error": {
                    "code": "JOB_INPUT_CONTRACT_VIOLATION",
                    "message": (
                        "inputs did not match the published contract for approve_or_reject. "
                        "Read GET /v1/job-contracts/approve_or_reject for the exact fields."
                    ),
                    "details": {
                        "job_type": "approve_or_reject",
                        "contract_url": "/v1/job-contracts/approve_or_reject",
                        "errors": [
                            {"field": "action", "code": "unexpected_field", "ignored": TEST_KEY},
                            {"field": TEST_KEY, "code": "unexpected_field"},
                            {"field": "subject_id", "code": "required"},
                            {
                                "field": "decision",
                                "code": "not_an_allowed_value",
                                "allowed": ["approved", "rejected", "revision_requested"],
                            },
                        ],
                    },
                    "private": TEST_KEY,
                }
            }
            with self.assertRaises(api.SocialAgentAPIError) as caught:
                api.request_json("POST", "/v1/jobs", body={})

        self.assertEqual(caught.exception.server_code, "JOB_INPUT_CONTRACT_VIOLATION")
        self.assertEqual(
            caught.exception.field_errors,
            [
                {"field": "action", "code": "unexpected_field"},
                {"field": "[REDACTED]", "code": "unexpected_field"},
                {"field": "subject_id", "code": "required"},
                {
                    "field": "decision",
                    "code": "not_an_allowed_value",
                    "allowed": ["approved", "rejected", "revision_requested"],
                },
            ],
        )
        message = str(caught.exception)
        self.assertIn("Read GET /v1/job-contracts/approve_or_reject", message)
        self.assertIn('"field":"action"', message)
        self.assertIn('"code":"required"', message)
        self.assertNotIn(TEST_KEY, message)
        self.assertNotIn("ignored", message)
        self.assertNotIn("private", message)

    def test_create_job_fetches_and_prints_contract_after_contract_violation(self) -> None:
        violation = api.SocialAgentAPIError(
            "Social Agent API returned HTTP 422 (JOB_INPUT_CONTRACT_VIOLATION)",
            server_code="JOB_INPUT_CONTRACT_VIOLATION",
            field_errors=[{"field": "action", "code": "unexpected_field"}],
        )
        contract = {
            "job_type": "approve_or_reject",
            "fields": {
                "subject_id": {"type": "uuid", "required": True},
                "decision": {
                    "type": "enum",
                    "required": True,
                    "values": ["approved", "rejected", "revision_requested"],
                },
            },
        }
        with patch.object(api, "request_json", side_effect=[violation, contract]) as request_json:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = api.main(
                    [
                        "create-job",
                        "--job-type",
                        "approve_or_reject",
                        "--idempotency-key",
                        "approval-001",
                        "--inputs-json",
                        '{"action":"approve"}',
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(request_json.call_count, 2)
        self.assertEqual(request_json.call_args_list[1].args, ("GET", "/v1/job-contracts/approve_or_reject"))
        printed = json.loads(stderr.getvalue())
        self.assertFalse(printed["ok"])
        self.assertEqual(printed["job_contract"], contract)

    def test_success_response_redacts_credentials_and_sensitive_fields(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            RecordingHandler.response_body = {
                "status": "ok",
                "echo": TEST_KEY,
                "api_token": "other-sensitive-value",
                "oauth_code": "must-not-be-printed",
                "authorization_code": "must-not-be-printed",
                "callback_url": "https://client.example/callback?code=must-not-be-printed",
                "redirect_url": "https://client.example/callback?code=must-not-be-printed",
                "nested": {"Authorization": "Bearer hidden", "safe_id": "job_123"},
                TEST_KEY: "credential was used as a key",
            }
            result = api.request_json("GET", "/v1/capabilities")

        self.assertEqual(
            result,
            {
                "status": "ok",
                "echo": "[REDACTED]",
                "api_token": "[REDACTED]",
                "oauth_code": "[REDACTED]",
                "authorization_code": "[REDACTED]",
                "callback_url": "[REDACTED]",
                "redirect_url": "[REDACTED]",
                "nested": {"Authorization": "[REDACTED]", "safe_id": "job_123"},
                "[REDACTED]": "credential was used as a key",
            },
        )

    def test_response_size_is_limited(self) -> None:
        with LocalServer() as base_url, patch.dict(os.environ, local_environment(base_url), clear=True):
            RecordingHandler.response_raw_body = b"x" * (api.MAX_RESPONSE_BYTES + 1)
            with self.assertRaisesRegex(api.SocialAgentAPIError, "safe size limit"):
                api.request_json("GET", "/v1/capabilities")

    def test_timeout_is_bounded(self) -> None:
        with patch.dict(os.environ, {"SOCIAL_AGENT_API_KEY": TEST_KEY}, clear=True):
            for invalid_timeout in (api.MAX_TIMEOUT_SECONDS + 1, float("nan"), float("inf"), float("-inf")):
                with self.subTest(invalid_timeout=invalid_timeout):
                    with self.assertRaisesRegex(api.SocialAgentAPIError, "no more than"):
                        api.request_json("GET", "/v1/capabilities", timeout=invalid_timeout)


if __name__ == "__main__":
    unittest.main()
