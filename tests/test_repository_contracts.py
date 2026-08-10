from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "social-agent-public-workflows" / "SKILL.md"
AUTH_HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "social_agent_api.py"
GUEST_HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "guest_questionnaire.py"
POST_HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "post_workflows.py"
SCHEDULING_HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "scheduling_workflows.py"
MCP_SETUP_PATH = ROOT / "docs" / "mcp-client-setup.md"


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contains_complete_mit_license(self) -> None:
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)

    def test_installable_skill_contains_no_local_questionnaire_copy(self) -> None:
        installable_files = sorted(
            path
            for path in SKILL_PATH.parent.rglob("*")
            if path.is_file() and path.suffix in {".md", ".py", ".json", ".yaml", ".yml"}
        )
        self.assertTrue(installable_files)
        combined = "\n".join(path.read_text(encoding="utf-8") for path in installable_files)
        forbidden = (
            "Fallback/dev question sequence",
            "API has no questionnaire endpoint yet",
            "locally defined questionnaire",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, combined)
        self.assertIn(
            "Your project is ready. Tell me when you want a Facebook post",
            combined,
        )
        self.assertNotIn("?", combined)
        self.assertIn("Every onboarding and update question must come from", combined)
        self.assertIn("Do not ask locally defined fallback questions", combined)

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
        mirror_install = "rsync -a --delete social-skills/skills/social-agent-public-workflows/"
        self.assertIn(mirror_install, readme)
        self.assertIn(mirror_install, skill)
        self.assertIn("npx -y skills@latest add lniass/social-skills", readme)
        self.assertIn("npx -y skills@latest update social-agent-public-workflows -y", readme)
        self.assertTrue(AUTH_HELPER_PATH.is_file())
        self.assertTrue(GUEST_HELPER_PATH.is_file())

    def test_public_skill_uses_handled_verification_without_mcp_onboarding(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("start with the bundled restricted guest helper", skill)
        self.assertIn("## Verify your Handled account", skill)
        self.assertIn("subscribe if needed", skill)
        self.assertIn("provider-confirmed entitlement", skill)
        self.assertIn("separate explicit approve or deny action", skill)
        self.assertIn("I will detect approval automatically", skill)
        self.assertIn("MCP is not part of current public onboarding", skill)
        self.assertIn("The helper supports `verify` and `poll-verification`", skill)
        self.assertIn("`project_ready` proves trusted claim and configured project creation", skill)
        self.assertIn("Only `caption_ready` proves persisted post-copy generation", skill)
        self.assertIn("create-post --confirm-user-request", skill)
        self.assertIn("poll again automatically", skill)
        self.assertNotIn("Stop unconditionally after questionnaire completion", skill)
        self.assertNotIn("Planned behavior only", skill)
        self.assertNotIn("https://handled.voicevine.ai/pricing", skill)

    def test_skill_version_matches_guest_helper_user_agent(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        helper_source = GUEST_HELPER_PATH.read_text(encoding="utf-8")
        match = re.search(r"^version: ([0-9]+(?:\.[0-9]+)+)$", skill, re.MULTILINE)
        self.assertIsNotNone(match)
        assert match is not None
        version_file = (SKILL_PATH.parent / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(version_file, match.group(1))
        self.assertIn(f'SKILL_VERSION = "{match.group(1)}"', helper_source)

    def test_approval_presentation_requires_visible_copy_assets_and_separate_schedule_consent(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        required = (
            "Present every caption as one separately numbered message before showing a copy gate.",
            "approve caption [number(s)]",
            "edit caption [number(s)]",
            "approve all captions",
            "A bare approval applies only to the last fully displayed caption.",
            "Present every required rendered image as one separately numbered preview before showing an image gate.",
            "approve image(s) [number(s)]",
            "regenerate image(s) [number(s)]",
            "approve all images",
            "A caption decision never approves an image.",
            "Flow: retrieve and display rendered image previews",
            "submit an allowlisted `list_posts` job",
            "MEDIA:/tmp/handled-image-<first-8-chars-of-asset-id>.jpg",
            "Never reuse a fixed or previously-used filename for a different asset ID",
            "an actual visible image attachment",
            "Never say or imply that images cannot be directly displayed",
            "Handled's native image-attachment format",
            "including when the current client has no native image-attachment capability",
            "respond with exactly `The actual preview is unavailable.`",
            "Refresh is retrieval only.",
            "Require a separate explicit scheduling confirmation after copy and image decisions.",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, skill)

    def test_direct_facebook_request_cannot_bypass_guest_questionnaire(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn('"connect my Facebook Page" is onboarding intent', skill)
        self.assertIn("Before the hosted guest questionnaire is complete, never:", skill)
        self.assertIn("Composio, Facebook, Meta, or other provider OAuth connection link", skill)
        self.assertIn("invoke a Composio tool or any non-Social-Agent connector", skill)
        self.assertIn("Run the restricted guest questionnaire helper", skill)
        self.assertIn("only after the check above lands on a genuinely new user", skill)
        self.assertIn("only when the user asks to schedule", skill)
        self.assertIn("Present the server-returned destination link as **Social Connect**, never as Composio", skill)

    def test_returning_identity_lists_projects_before_onboarding(self) -> None:
        # A fresh runtime (e.g. a destroyed-and-recreated Agent37 instance)
        # has no local memory of a prior session even when its credential's
        # workspace already has a project. This is the mandatory check that
        # must run before guest onboarding ever starts, and the exact wording
        # for each of its three outcomes.
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "Check whether this user already has a project before onboarding "
            "anything, at the very start of every fresh session.",
            skill,
        )
        self.assertIn(
            "run `python3 scripts/social_agent_api.py projects` and present "
            "its outcome exactly as described in Presenting connected projects",
            skill,
        )
        self.assertIn("A failed `projects` call is not evidence of a new user", skill)
        self.assertIn("Here is the list of connected social media accounts:", skill)
        self.assertIn("Your workspace is empty.", skill)
        self.assertIn("No workspace found.", skill)
        self.assertIn("Do not start onboarding after this list.", skill)
        self.assertIn(
            "A failed call here (network, timeout, or server error) is never "
            "grounds to conclude no workspace exists",
            skill,
        )

    def test_mcp_commands_are_future_only_and_absent_from_active_skill(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        setup = MCP_SETUP_PATH.read_text(encoding="utf-8")
        required = (
            "claude mcp add --transport http --scope user social-agent",
            "codex mcp add social-agent --url",
            "codex mcp login social-agent",
            "opencode mcp auth social-agent",
            "hermes mcp add social-agent --url",
            "hermes mcp test social-agent",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, setup)
                self.assertNotIn(value, skill)
        self.assertIn("Future optional Social Agent MCP setup", setup)
        self.assertIn("Do not ask a public onboarding user to configure or authenticate MCP", setup)

    def test_handled_verification_states_and_auto_resume_are_explicit(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in (
            SKILL_PATH,
            ROOT / "docs" / "guest-questionnaire-flow.md",
            ROOT / "docs" / "social-agent-public-workflows-plan.md",
        ))
        for value in (
            "Verify your Handled account",
            "provider-confirmed entitlement",
            "explicit approve or deny",
            "polls privately",
            "does not return to chat to say `done`",
            "configured-project proof",
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
        self.assertIn("Do not paste passwords, codes, callback links, or tokens here", combined)
        self.assertIn("guest resume token or verification polling credential", combined)

    def test_public_surface_rejects_supabase_admin_and_arbitrary_tools(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("Never connect to or expose the Supabase developer MCP", skill)
        self.assertIn("Do not use arbitrary HTTP, shell, database, bootstrap, operator, or admin tools", skill)
        self.assertIn("The fixed controlled product job allowlist is", skill)
        helper_source = AUTH_HELPER_PATH.read_text(encoding="utf-8")
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

    def test_guest_helper_boundary_is_documented_without_claim_or_question_copy(self) -> None:
        skill = SKILL_PATH.read_text(encoding="utf-8")
        helper_source = GUEST_HELPER_PATH.read_text(encoding="utf-8")
        post_helper_source = POST_HELPER_PATH.read_text(encoding="utf-8")
        scheduling_helper_source = SCHEDULING_HELPER_PATH.read_text(encoding="utf-8")
        self.assertIn("scripts/guest_questionnaire.py", skill)
        self.assertIn("scripts/post_workflows.py", skill)
        self.assertIn("scripts/scheduling_workflows.py", skill)
        self.assertNotIn('"create-post"', helper_source)
        self.assertIn('"create-post"', post_helper_source)
        self.assertNotIn('"schedule-one"', helper_source)
        self.assertNotIn('"schedule-one"', post_helper_source)
        self.assertIn('"schedule-one"', scheduling_helper_source)
        self.assertIn('"/v1/guest/post-requests"', post_helper_source)
        self.assertIn('"/v1/jobs"', scheduling_helper_source)
        self.assertNotIn("mcp_postiz", scheduling_helper_source.lower())
        self.assertNotIn("integrationscheduleposttool", scheduling_helper_source.lower())
        self.assertIn("mode `0600` or stricter", skill)
        self.assertIn("Try `resume` before `start`", skill)
        self.assertIn("Never paste a guest resume token or verification polling credential into a tool argument", skill)
        self.assertNotIn("claim_guest", helper_source)
        self.assertNotIn('headers["Authorization"]', helper_source)
        self.assertNotIn("What should I build", skill)

    def test_failed_generation_recovery_is_explicit_and_non_destructive(self) -> None:
        documents = (
            SKILL_PATH,
            ROOT / "README.md",
            ROOT / "docs" / "guest-questionnaire-flow.md",
        )
        for path in documents:
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn("retry-post --confirm-user-retry", text)
                self.assertIn("new questionnaire", text)
        skill = SKILL_PATH.read_text(encoding="utf-8")
        helper_source = POST_HELPER_PATH.read_text(encoding="utf-8")
        self.assertIn("preserve the complete guest and verification state", skill)
        self.assertIn('"retry-post"', helper_source)
        self.assertIn('{"retry_failed_generation": True}', helper_source)
        self.assertIn("recovery_contract=True", helper_source)
        self.assertNotIn('"retry_failed_generation": False', helper_source)
        self.assertIn("VERIFICATION_CLEANUP_STATUSES", helper_source)


if __name__ == "__main__":
    unittest.main()
