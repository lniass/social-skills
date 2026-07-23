from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "social-agent-public-workflows"
    / "scripts"
    / "guest_questionnaire.py"
)
SPEC = importlib.util.spec_from_file_location("guest_questionnaire", SCRIPT_PATH)
assert SPEC and SPEC.loader
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)

TEST_TOKEN = "gq_" + "a" * 43


def questionnaire_response(*, token: str | None = None, completed: bool = False) -> dict[str, object]:
    result: dict[str, object] = {
        "api_version": "2026-07-01",
        "request_id": "request-1",
        "expires_at": "2026-07-24T12:00:00+00:00",
        "questionnaire": {
            "workflow_key": "social_agent_public_onboarding",
            "version": 2,
            "session_id": "guest-session-1",
            "status": "completed" if completed else "in_progress",
            "completed": completed,
            "answers": {},
            "completed_steps": [],
            "next_action": "continue",
            "question": None
            if completed
            else {
                "step_key": "server-owned-step",
                "question": "Server-owned question",
                "options": [
                    {"option_id": "one", "label": "Server option one", "recommended": True},
                    {"option_id": "two", "label": "Server option two", "recommended": False},
                ],
            },
        },
    }
    if token is not None:
        result["resume_token"] = token
    return result


class RecordingHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []
    queued_responses: list[tuple[int, Mapping[str, object] | bytes]] = []

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b""
        self.__class__.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "resume_token": self.headers.get("X-Guest-Resume-Token"),
                "user_agent": self.headers.get("User-Agent"),
                "body": json.loads(raw_body) if raw_body else None,
            }
        )
        status, response = self.__class__.queued_responses.pop(0)
        encoded = response if isinstance(response, bytes) else json.dumps(response).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
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
    def __init__(self, *responses: tuple[int, Mapping[str, object] | bytes]) -> None:
        self.queued_responses = list(responses)

    def __enter__(self) -> str:
        RecordingHandler.requests = []
        RecordingHandler.queued_responses = list(self.queued_responses)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def environment(base_url: str, state_file: Path) -> dict[str, str]:
    return {
        "SOCIAL_AGENT_API_BASE_URL": base_url,
        guest.CUSTOM_ORIGIN_ENV: "1",
        guest.STATE_FILE_ENV: str(state_file),
    }


def write_state(path: Path, *, token: str = TEST_TOKEN, base_url: str) -> None:
    path.write_text(
        json.dumps(
            {
                "api_version": guest.API_VERSION,
                "api_base_url": base_url,
                "expires_at": "2026-07-24T12:00:00+00:00",
                "resume_token": token,
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o600)


class GuestQuestionnaireTests(unittest.TestCase):
    def test_default_origin_and_public_commands_are_restricted(self) -> None:
        self.assertEqual(guest.DEFAULT_API_BASE_URL, "https://social-agent-api.voicevine.ai")
        parser = guest.build_parser()
        commands = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
        self.assertEqual(set(commands), {"start", "resume", "answer", "forget"})
        self.assertNotIn("claim", commands)

    def test_start_saves_private_token_without_printing_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer((201, questionnaire_response(token=TEST_TOKEN))) as base_url, patch.dict(
                os.environ, environment(base_url, state_file), clear=True
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    exit_code = guest.main(["start"])

            self.assertEqual(exit_code, 0)
            output = json.loads(stdout.getvalue())
            self.assertEqual(output["resume_token"], "[REDACTED]")
            self.assertTrue(output["resume_saved"])
            self.assertNotIn(TEST_TOKEN, stdout.getvalue())
            self.assertEqual(json.loads(state_file.read_text(encoding="utf-8"))["resume_token"], TEST_TOKEN)
            self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)
            request = RecordingHandler.requests[0]
            self.assertEqual(request["method"], "POST")
            self.assertEqual(request["path"], "/v1/guest/questionnaire")
            self.assertIsNone(request["authorization"])
            self.assertIsNone(request["resume_token"])
            self.assertEqual(request["user_agent"], "social-agent-public-workflows-guest/0.4.0")

    def test_resume_reads_private_state_and_sends_only_guest_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer((200, questionnaire_response())) as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        exit_code = guest.main(["resume"])

            self.assertEqual(exit_code, 0)
            self.assertNotIn(TEST_TOKEN, stdout.getvalue())
            request = RecordingHandler.requests[0]
            self.assertEqual(request["method"], "GET")
            self.assertEqual(request["path"], "/v1/guest/questionnaire")
            self.assertEqual(request["resume_token"], TEST_TOKEN)
            self.assertIsNone(request["authorization"])

    def test_answer_submits_exact_step_and_json_value(self) -> None:
        answer = {"option_id": "one"}
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer((200, questionnaire_response())) as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        exit_code = guest.main(
                            ["answer", "--step-key", "server-owned-step", "--answer-json", json.dumps(answer)]
                        )

            self.assertEqual(exit_code, 0)
            request = RecordingHandler.requests[0]
            self.assertEqual(request["path"], "/v1/guest/questionnaire/answer")
            self.assertEqual(request["resume_token"], TEST_TOKEN)
            self.assertEqual(
                request["body"],
                {"api_version": "2026-07-01", "step_key": "server-owned-step", "answer": answer},
            )

    def test_answer_rejects_sensitive_content_invalid_step_and_oversized_payload(self) -> None:
        sensitive_answers = (
            {"api_token": "not-allowed"},
            {"description": TEST_TOKEN},
            {"nested": [{"password": "not-allowed"}]},
        )
        for answer in sensitive_answers:
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "credentials or sensitive"):
                    guest._answer(step_key="server-step", answer=answer, timeout=30)

        for step_key in ("", "x" * 121, "bad\nstep"):
            with self.subTest(step_key=step_key):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "step key is invalid"):
                    guest._answer(step_key=step_key, answer={"option_id": "one"}, timeout=30)

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(guest.GuestQuestionnaireError, "answer exceeded"):
                guest._request_json(
                    "POST",
                    "/v1/guest/questionnaire/answer",
                    body={"answer": "x" * guest.MAX_REQUEST_BYTES},
                )

    def test_start_refuses_to_overwrite_saved_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer() as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        exit_code = guest.main(["start"])

            self.assertEqual(exit_code, 1)
            self.assertIn("resume or forget", stderr.getvalue())
            self.assertEqual(RecordingHandler.requests, [])
            self.assertEqual(json.loads(state_file.read_text(encoding="utf-8"))["resume_token"], TEST_TOKEN)

    def test_forget_removes_only_valid_state_without_printing_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer() as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        exit_code = guest.main(["forget"])
            self.assertEqual(exit_code, 0)
            self.assertFalse(state_file.exists())
            self.assertNotIn(TEST_TOKEN, stdout.getvalue())

    def test_forget_rejects_unrelated_or_permissive_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            state_file.write_text("unrelated user file", encoding="utf-8")
            state_file.chmod(0o600)
            with patch.dict(os.environ, {guest.STATE_FILE_ENV: str(state_file)}, clear=True):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "state is invalid"):
                    guest._forget_state()
            self.assertEqual(state_file.read_text(encoding="utf-8"), "unrelated user file")

            state_file.write_text("{}", encoding="utf-8")
            state_file.chmod(0o644)
            with patch.dict(os.environ, {guest.STATE_FILE_ENV: str(state_file)}, clear=True):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "0600"):
                    guest._forget_state()
            self.assertTrue(state_file.exists())

    def test_custom_origin_requires_explicit_development_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "SOCIAL_AGENT_API_BASE_URL": "https://staging.example.com",
                guest.STATE_FILE_ENV: str(Path(directory) / "guest.json"),
            },
            clear=True,
        ):
            with self.assertRaisesRegex(guest.GuestQuestionnaireError, guest.CUSTOM_ORIGIN_ENV):
                guest._api_base_url()

    def test_custom_https_origin_is_rejected_even_with_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "SOCIAL_AGENT_API_BASE_URL": "https://staging.example.com",
                guest.CUSTOM_ORIGIN_ENV: "1",
                guest.STATE_FILE_ENV: str(Path(directory) / "guest.json"),
            },
            clear=True,
        ):
            with self.assertRaises(guest.GuestQuestionnaireError):
                guest._api_base_url()

    def test_non_loopback_http_origin_is_rejected_even_with_override(self) -> None:
        with patch.dict(
            os.environ,
            {"SOCIAL_AGENT_API_BASE_URL": "http://example.com", guest.CUSTOM_ORIGIN_ENV: "1"},
            clear=True,
        ):
            with self.assertRaises(guest.GuestQuestionnaireError):
                guest._api_base_url()

    def test_state_path_must_be_absolute(self) -> None:
        with patch.dict(os.environ, {guest.STATE_FILE_ENV: "relative/guest.json"}, clear=True):
            with self.assertRaisesRegex(guest.GuestQuestionnaireError, "absolute"):
                guest._state_path()

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"), "requires POSIX no-follow support")
    def test_resume_rejects_state_file_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.json"
            link = Path(directory) / "link.json"
            target.write_text("{}", encoding="utf-8")
            target.chmod(0o600)
            link.symlink_to(target)
            with patch.dict(os.environ, {guest.STATE_FILE_ENV: str(link)}, clear=True):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "No resumable"):
                    guest._load_state()

    def test_resume_rejects_permissive_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            state_file.write_text("{}", encoding="utf-8")
            state_file.chmod(0o644)
            with patch.dict(os.environ, {guest.STATE_FILE_ENV: str(state_file)}, clear=True):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "0600"):
                    guest._load_state()

    def test_response_contract_rejects_version_shape_and_state_drift(self) -> None:
        valid = questionnaire_response()
        invalid_cases: list[tuple[str, dict[str, object], str]] = []

        wrong_version = json.loads(json.dumps(valid))
        wrong_version["api_version"] = "2099-01-01"
        invalid_cases.append(("api version", wrong_version, "unsupported API version"))

        missing_question = json.loads(json.dumps(valid))
        assert isinstance(missing_question["questionnaire"], dict)
        missing_question["questionnaire"].pop("question")
        invalid_cases.append(("missing question", missing_question, "current questionnaire step"))

        inconsistent = json.loads(json.dumps(valid))
        assert isinstance(inconsistent["questionnaire"], dict)
        inconsistent["questionnaire"]["completed"] = True
        invalid_cases.append(("inconsistent state", inconsistent, "inconsistent questionnaire"))

        bad_options = json.loads(json.dumps(valid))
        assert isinstance(bad_options["questionnaire"], dict)
        assert isinstance(bad_options["questionnaire"]["question"], dict)
        bad_options["questionnaire"]["question"]["options"] = "not-a-list"
        invalid_cases.append(("invalid options", bad_options, "invalid question options"))

        for label, response, message in invalid_cases:
            with self.subTest(label=label):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, message):
                    guest._validate_questionnaire_response(response, expect_token=False)

    def test_answer_requires_a_json_object(self) -> None:
        for answer in ("one", ["one"], None, 1, True):
            with self.subTest(answer=answer):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "JSON objects"):
                    guest._answer(step_key="server-step", answer=answer, timeout=30)

    def test_http_error_does_not_print_backend_body_or_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            response = {"detail": f"private backend detail {TEST_TOKEN}"}
            with LocalServer((400, response)) as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        exit_code = guest.main(["resume"])

            self.assertEqual(exit_code, 1)
            self.assertIn("HTTP 400", stderr.getvalue())
            self.assertNotIn("private backend detail", stderr.getvalue())
            self.assertNotIn(TEST_TOKEN, stderr.getvalue())

    def test_success_response_redacts_resume_tokens_and_sensitive_fields(self) -> None:
        response = questionnaire_response()
        response.update(
            {
                "echo": TEST_TOKEN,
                "api_token": "sensitive",
                TEST_TOKEN: "token used as a key",
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer((200, response)) as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    result = guest._resume(30)

        serialized = json.dumps(result)
        self.assertNotIn(TEST_TOKEN, serialized)
        self.assertEqual(result["api_token"], "[REDACTED]")

    def test_cross_origin_redirect_is_rejected_without_forwarding_guest_token(self) -> None:
        received_tokens: list[str | None] = []

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                received_tokens.append(self.headers.get("X-Guest-Resume-Token"))
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
            with tempfile.TemporaryDirectory() as directory:
                base_url = f"http://127.0.0.1:{redirect.server_port}"
                state_file = Path(directory) / "guest.json"
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    with self.assertRaisesRegex(guest.GuestQuestionnaireError, "HTTP 302"):
                        guest._resume(30)
        finally:
            redirect.shutdown()
            target.shutdown()
            redirect.server_close()
            target.server_close()
            for thread in threads:
                thread.join(timeout=2)

        self.assertEqual(received_tokens, [])

    def test_response_size_and_timeout_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "guest.json"
            with LocalServer((200, b"x" * (guest.MAX_RESPONSE_BYTES + 1))) as base_url:
                write_state(state_file, base_url=base_url)
                with patch.dict(os.environ, environment(base_url, state_file), clear=True):
                    with self.assertRaisesRegex(guest.GuestQuestionnaireError, "safe size limit"):
                        guest._resume(30)

        for timeout in (guest.MAX_TIMEOUT_SECONDS + 1, float("nan"), float("inf"), float("-inf")):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(guest.GuestQuestionnaireError, "no more than"):
                    guest._request_timeout(timeout)


if __name__ == "__main__":
    unittest.main()
