from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
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


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    response_status = 200
    response_body: dict[str, object] = {"ok": True}

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b""
        body = json.loads(raw_body) if raw_body else None
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": body,
            }
        )
        encoded = json.dumps(self.__class__.response_body).encode("utf-8")
        self.send_response(self.__class__.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    do_GET = _handle
    do_POST = _handle

    def log_message(self, format: str, *args: object) -> None:
        return None


class LocalServer:
    def __enter__(self) -> str:
        RecordingHandler.requests = []
        RecordingHandler.response_status = 200
        RecordingHandler.response_body = {"ok": True}
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

    def test_capabilities_uses_workspace_bearer_credential(self) -> None:
        with LocalServer() as base_url, patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": base_url},
            clear=True,
        ):
            result = api.request_json("GET", "/v1/capabilities")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            RecordingHandler.requests,
            [
                {
                    "method": "GET",
                    "path": "/v1/capabilities",
                    "authorization": f"Bearer {TEST_KEY}",
                    "body": None,
                }
            ],
        )

    def test_create_job_cli_sends_versioned_job_packet(self) -> None:
        with LocalServer() as base_url, patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": base_url},
            clear=True,
        ):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = api.main(
                    [
                        "create-job",
                        "--job-type",
                        "setup_project",
                        "--idempotency-key",
                        "setup-demo-001",
                        "--project-reference-id",
                        "demo-project",
                        "--inputs-json",
                        '{"display_name":"Demo"}',
                    ]
                )

        self.assertEqual(exit_code, 0)
        request = RecordingHandler.requests[0]
        self.assertEqual(request["path"], "/v1/jobs")
        self.assertEqual(
            request["body"],
            {
                "api_version": "2026-07-01",
                "job_type": "setup_project",
                "idempotency_key": "setup-demo-001",
                "project_reference_id": "demo-project",
                "inputs": {"display_name": "Demo"},
            },
        )
        self.assertEqual(json.loads(stdout.getvalue()), {"ok": True})

    def test_public_http_api_url_is_rejected(self) -> None:
        with patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": "http://api.example.com"},
            clear=True,
        ):
            with self.assertRaisesRegex(api.SocialAgentAPIError, "must use HTTPS"):
                api.request_json("GET", "/v1/capabilities")

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

    def test_http_error_redacts_credentials(self) -> None:
        with LocalServer() as base_url, patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_KEY": TEST_KEY, "SOCIAL_AGENT_API_BASE_URL": base_url},
            clear=True,
        ):
            RecordingHandler.response_status = 400
            RecordingHandler.response_body = {"error": f"do not leak {TEST_KEY}"}
            with self.assertRaises(api.SocialAgentAPIError) as caught:
                api.request_json("GET", "/v1/capabilities")

        message = str(caught.exception)
        self.assertNotIn(TEST_KEY, message)
        self.assertIn("[REDACTED]", message)


if __name__ == "__main__":
    unittest.main()
