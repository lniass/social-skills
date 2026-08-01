"""Sign-in helper behaviour.

The valuable assertions here are the refusals. A sign-in helper that leaks a
token, redeems a response meant for a different request, or reports a bare
client registration as authentication would each be worse than not having one.
"""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "social-agent-public-workflows" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import signin  # noqa: E402


class SignInStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.state_file = Path(self._directory.name) / "signin.json"
        patcher = mock.patch.dict(
            os.environ, {signin.STATE_FILE_ENV: str(self.state_file)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_state_is_written_private_to_the_owner(self) -> None:
        signin._save_state({"client_id": "abc"})
        mode = self.state_file.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_a_world_readable_state_file_is_refused(self) -> None:
        # A token sitting in a file other users can read is not usable state,
        # and silently accepting it would hide the exposure.
        signin._save_state({"client_id": "abc"})
        self.state_file.chmod(0o644)
        with self.assertRaises(signin.SignInError):
            signin._load_state()

    def test_missing_state_is_not_an_error(self) -> None:
        # A fresh install has no state; that is the normal first run.
        self.assertEqual(signin._load_state(), {})

    def test_forget_keeps_registration_but_drops_tokens(self) -> None:
        signin._save_state(
            {"client_id": "abc", "refresh_token": "r", "access_token": "a"}
        )
        signin.command_forget(mock.Mock())
        state = signin._load_state()
        self.assertEqual(state.get("client_id"), "abc")
        self.assertNotIn("refresh_token", state)
        self.assertNotIn("access_token", state)


class SignInStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        patcher = mock.patch.dict(
            os.environ,
            {signin.STATE_FILE_ENV: str(Path(self._directory.name) / "signin.json")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_registration_alone_is_not_reported_as_signed_in(self) -> None:
        # This exact conflation is what made a registered-but-tokenless install
        # look authenticated to its own agent.
        signin._save_state({"client_id": "abc"})
        status = signin.command_status(mock.Mock())
        self.assertTrue(status["registered"])
        self.assertFalse(status["signed_in"])

    def test_a_refresh_token_counts_as_signed_in(self) -> None:
        signin._save_state({"client_id": "abc", "refresh_token": "r"})
        self.assertTrue(signin.command_status(mock.Mock())["signed_in"])

    def test_status_reveals_no_token_material(self) -> None:
        signin._save_state(
            {"client_id": "abc", "refresh_token": "secret-r", "access_token": "secret-a"}
        )
        rendered = json.dumps(signin.command_status(mock.Mock()))
        self.assertNotIn("secret-r", rendered)
        self.assertNotIn("secret-a", rendered)


class SignInFinishTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        patcher = mock.patch.dict(
            os.environ,
            {signin.STATE_FILE_ENV: str(Path(self._directory.name) / "signin.json")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        signin._save_state(
            {
                "client_id": "abc",
                "pending": {
                    "code_verifier": "v",
                    "state": "expected-state",
                    "redirect_uri": "http://127.0.0.1:8765/social-agent/callback",
                    "token_endpoint": "https://auth.example/token",
                    "created_at": int(time.time()),
                },
            }
        )

    def test_a_mismatched_state_is_refused_without_calling_the_token_endpoint(
        self,
    ) -> None:
        # Redeeming a response from a different sign-in would bind this install
        # to whatever session produced it.
        with mock.patch.object(signin, "_post_form") as post:
            with self.assertRaises(signin.SignInError):
                signin.command_finish(
                    mock.Mock(
                        redirect_url="http://127.0.0.1:8765/cb?code=c&state=wrong"
                    )
                )
            post.assert_not_called()

    def test_an_authorization_error_is_reported_without_its_description(self) -> None:
        with self.assertRaises(signin.SignInError) as caught:
            signin.command_finish(
                mock.Mock(
                    redirect_url=(
                        "http://127.0.0.1:8765/cb?error=access_denied"
                        "&error_description=user+said+no+to+everything"
                    )
                )
            )
        self.assertIn("access_denied", str(caught.exception))
        self.assertNotIn("said no to everything", str(caught.exception))

    def test_a_successful_exchange_clears_the_pending_request(self) -> None:
        with mock.patch.object(
            signin,
            "_post_form",
            return_value={
                "access_token": "at",
                "refresh_token": "rt",
                "expires_in": 3600,
            },
        ):
            result = signin.command_finish(
                mock.Mock(
                    redirect_url="http://127.0.0.1:8765/cb?code=c&state=expected-state"
                )
            )
        self.assertEqual(result["status"], "signed_in")
        state = signin._load_state()
        self.assertNotIn("pending", state)
        # The one-time request must not be replayable.
        with self.assertRaises(signin.SignInError):
            signin.command_finish(
                mock.Mock(
                    redirect_url="http://127.0.0.1:8765/cb?code=c&state=expected-state"
                )
            )

    def test_the_returned_payload_carries_no_token(self) -> None:
        # Distinctive values, so the assertion cannot pass or fail by matching
        # an ordinary English substring in the next_action text.
        access = "ACCESS-TOKEN-c3f9a1"
        refresh = "REFRESH-TOKEN-7b21de"
        with mock.patch.object(
            signin,
            "_post_form",
            return_value={
                "access_token": access,
                "refresh_token": refresh,
                "expires_in": 60,
            },
        ):
            result = signin.command_finish(
                mock.Mock(
                    redirect_url="http://127.0.0.1:8765/cb?code=c&state=expected-state"
                )
            )
        rendered = json.dumps(result)
        self.assertNotIn(access, rendered)
        self.assertNotIn(refresh, rendered)
        # Stored, though -- the token has to survive somewhere private.
        self.assertEqual(signin._load_state()["access_token"], access)


class RefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        patcher = mock.patch.dict(
            os.environ,
            {signin.STATE_FILE_ENV: str(Path(self._directory.name) / "signin.json")},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_valid_access_token_is_reused_without_a_network_call(self) -> None:
        signin._save_state(
            {
                "client_id": "abc",
                "access_token": "still-good",
                "access_expires_at": int(time.time()) + 3600,
            }
        )
        with mock.patch.object(signin, "_discover") as discover:
            self.assertEqual(signin.load_access_token(), "still-good")
            discover.assert_not_called()

    def test_a_token_inside_the_skew_window_is_refreshed_early(self) -> None:
        # Expiring mid-request is indistinguishable from revoked at the call
        # site, and finding out by retrying a mutating call is the thing to
        # avoid.
        signin._save_state(
            {
                "client_id": "abc",
                "access_token": "about-to-expire",
                "access_expires_at": int(time.time()) + 10,
                "refresh_token": "rt",
            }
        )
        with mock.patch.object(
            signin, "_discover", return_value={"token_endpoint": "https://auth/token"}
        ), mock.patch.object(
            signin, "_post_form", return_value={"access_token": "fresh", "expires_in": 3600}
        ):
            self.assertEqual(signin.load_access_token(), "fresh")

    def test_a_refresh_that_omits_a_new_refresh_token_keeps_the_old_one(self) -> None:
        # Dropping it would silently force a browser sign-in on the next call.
        signin._save_state(
            {
                "client_id": "abc",
                "access_expires_at": 0,
                "refresh_token": "keep-me",
            }
        )
        with mock.patch.object(
            signin, "_discover", return_value={"token_endpoint": "https://auth/token"}
        ), mock.patch.object(
            signin, "_post_form", return_value={"access_token": "fresh", "expires_in": 60}
        ):
            signin.load_access_token()
        self.assertEqual(signin._load_state()["refresh_token"], "keep-me")

    def test_no_refresh_token_asks_for_sign_in_rather_than_guessing(self) -> None:
        signin._save_state({"client_id": "abc"})
        with self.assertRaises(signin.SignInError):
            signin.load_access_token()


if __name__ == "__main__":
    unittest.main()
