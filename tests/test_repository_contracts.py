from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills" / "social-agent-public-workflows" / "SKILL.md"
HELPER_PATH = ROOT / "skills" / "social-agent-public-workflows" / "scripts" / "social_agent_api.py"


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


if __name__ == "__main__":
    unittest.main()
