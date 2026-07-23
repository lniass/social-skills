from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "social-agent-public-workflows" / "SKILL.md"
HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "social_agent_api.py"
MCP_SETUP_PATH = ROOT / "docs" / "mcp-client-setup.md"


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contains_complete_mit_license(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)

    def test_skill_contains_no_local_questionnaire_copy(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        forbidden = (
            "Fallback/dev question sequence",
            "API has no questionnaire endpoint yet",
            "locally defined questionnaire",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, skill)
        self.assertNotIn("?", skill)
        self.assertIn("Every onboarding and update question must come from", skill)
        self.assertIn("Do not ask locally defined fallback questions", skill)

    def test_example_is_api_driven_without_question_copy(self) -> None:
        example_text = (ROOT / "examples" / "onboarding-session.json").read_text(encoding="utf-8")
        example = json.loads(example_text)
        self.assertNotIn("pre_project_questions", example)
        self.assertNotIn("ask_user", example_text)
        self.assertEqual(example["get_next_question_request"]["job_type"], "get_next_question")
        self.assertEqual(example["answer_question_request_shape"]["job_type"], "answer_question")

    def test_install_documentation_preserves_helper(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = SKILL_PATH.read_text(encoding="utf-8")
        raw_install = "hermes skills install https://raw.githubusercontent.com"
        self.assertNotIn(raw_install, readme)
        self.assertNotIn(raw_install, skill)
        self.assertIn("cp -R social-skills/skills/social-agent-public-workflows/.", readme)
        self.assertIn("cp -R social-skills/skills/social-agent-public-workflows/.", skill)
        self.assertTrue(HELPER_PATH.is_file())

    def test_public_skill_is_mcp_first_with_client_managed_oauth(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Use the Social Agent MCP first", skill)
        self.assertIn("The MCP client, not the conversation, performs OAuth", skill)
        self.assertIn("OAuth happens in the MCP client outside chat", skill)
        self.assertIn("https://social-agent-api.voicevine.ai/mcp", skill)
        self.assertIn("Controlled-pilot helper fallback", skill)
        self.assertIn("It is not a public OAuth fallback", skill)

    def test_cross_runtime_commands_and_config_paths_are_documented(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        setup = MCP_SETUP_PATH.read_text(encoding="utf-8")
        required = (
            "claude mcp add --transport http --scope user social-agent",
            "~/.claude.json",
            "codex mcp add social-agent --url",
            "codex mcp login social-agent",
            "~/.codex/config.toml",
            '\"type\": \"remote\"',
            "opencode mcp auth social-agent",
            "~/.config/opencode/opencode.json",
            "hermes mcp add social-agent --url",
            "hermes mcp test social-agent",
            "~/.hermes/config.yaml",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, skill)
                self.assertIn(value, setup)

    def test_auth_states_resume_and_reauth_are_explicit(self) -> None:
        combined = "\n".join(
            (
                SKILL_PATH.read_text(encoding="utf-8"),
                MCP_SETUP_PATH.read_text(encoding="utf-8"),
            )
        )
        for value in (
            "Unauthenticated",
            "Expired, revoked, or wrong account",
            "After authentication",
            "re-authentication",
            "Read capabilities and current hosted",
            "Do not replay a mutating tool call",
        ):
            with self.subTest(value=value):
                self.assertIn(value, combined)

    def test_public_docs_never_request_or_embed_auth_material(self) -> None:
        combined = "\n".join(
            (
                SKILL_PATH.read_text(encoding="utf-8"),
                MCP_SETUP_PATH.read_text(encoding="utf-8"),
                (ROOT / "README.md").read_text(encoding="utf-8"),
            )
        )
        forbidden = (
            "Bearer eyJ",
            "sai_testkey",
            'clientSecret\": \"actual',
            "authorization_code=",
            "access_token=",
            "refresh_token=",
            "paste the OAuth code",
            "paste your token",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, combined)
        self.assertIn("Never print, repeat, summarize, log, or persist those values", combined)
        self.assertIn("Never expose credentials or OAuth codes", combined)

    def test_public_surface_rejects_supabase_admin_and_arbitrary_tools(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Never connect to or expose the Supabase developer MCP", skill)
        self.assertIn("Do not use arbitrary HTTP, shell, database, bootstrap, operator, or admin tools", skill)
        self.assertIn("The fixed job allowlist is", skill)
        helper_source = HELPER_PATH.read_text(encoding="utf-8")
        for job_type in (
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
        ):
            with self.subTest(job_type=job_type):
                self.assertIn(job_type, skill)
                self.assertIn(f'\"{job_type}\"', helper_source)


if __name__ == "__main__":
    unittest.main()
