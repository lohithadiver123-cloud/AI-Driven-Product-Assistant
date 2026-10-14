"""
Async integration tests for Milestone 3 services and data pipelines.
Tests PRD generation, Agile User Story generation, Prioritization auto-seeding & weighted scoring,
and PM Copilot multi-turn chat.
"""

import os
import sys
import unittest
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import prd_service, user_story_service, prioritization_service, copilot_service


# Hyphen characters a language model may emit interchangeably: ASCII hyphen-minus,
# non-breaking hyphen, figure dash, en dash, em dash, small hyphen-minus and fullwidth
# hyphen-minus. A title is the same title whichever one it uses.
_HYPHENS = "\u002d\u2010\u2011\u2012\u2013\u2014\ufe63\uff0d"
_HYPHEN_TABLE = str.maketrans({char: "-" for char in _HYPHENS})


def normalise_hyphens(text: str) -> str:
    """
    Fold the various hyphen codepoints to a plain hyphen.

    Asserting `"Anti-Suspension" in title` made this test flaky: when the model returned
    `Anti\u2011Suspension` (non-breaking hyphen) the string matched no evidence of a real
    defect, but the test failed anyway. Comparing on normalised text still proves the title
    carries the requested subject and is no longer hostage to typography.
    """
    return str(text).translate(_HYPHEN_TABLE)


class Milestone3ServiceIntegration(unittest.TestCase):

    def setUp(self):
        self.workspace_id = "test_workspace_m3"

    def test_prd_service_pipeline(self):
        async def _run():
            # 1. Generate PRD
            prd = await prd_service.generate_prd_with_ai(
                workspace_id=self.workspace_id,
                title="PRD: Anti-Suspension Security Shield",
                custom_prompt="Provide automated identity appeal verification within 5 minutes.",
                target_audience="Creators and Businesses",
                strategic_goals="Reduce account lockouts by 80%",
                tone="comprehensive"
            )
            self.assertIsNotNone(prd)
            self.assertEqual(prd["workspace_id"], self.workspace_id)
            self.assertIn("Anti-Suspension", normalise_hyphens(prd["title"]))
            self.assertGreaterEqual(len(prd["functional_requirements"]), 2)
            self.assertIn("raw_markdown", prd)

            # 2. Get PRD by ID
            fetched = await prd_service.get_prd_by_id(prd["id"])
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["id"], prd["id"])

            # 3. Update PRD
            updated = await prd_service.update_prd(prd["id"], {"status": "in_review"})
            self.assertEqual(updated["status"], "in_review")

            # 4. List PRDs for workspace
            prds = await prd_service.get_prds_for_workspace(self.workspace_id)
            self.assertGreaterEqual(len(prds), 1)

            return prd

        generated_prd = asyncio.run(_run())
        self.assertIsNotNone(generated_prd)

    def test_user_story_service_pipeline(self):
        async def _run():
            # Generate User Stories
            stories = await user_story_service.generate_user_stories_with_ai(
                workspace_id=self.workspace_id,
                custom_prompt="Real-time multi-device session sync",
                count=3,
                persona="Power User"
            )
            self.assertEqual(len(stories), 3)
            for s in stories:
                self.assertEqual(s["workspace_id"], self.workspace_id)
                self.assertIn(s["story_points"], [1, 2, 3, 5, 8, 13])
                self.assertIn(s["status"], ["backlog", "in_progress", "in_review", "done"])
                self.assertGreaterEqual(len(s["acceptance_criteria"]), 1)

            # Update status
            s0 = stories[0]
            updated = await user_story_service.update_story_status(s0["id"], "in_progress")
            self.assertEqual(updated["status"], "in_progress")

            # List stories
            all_s = await user_story_service.get_stories_for_workspace(self.workspace_id)
            self.assertGreaterEqual(len(all_s), 3)

        asyncio.run(_run())

    def test_prioritization_service_pipeline(self):
        async def _run():
            # 1. Custom item creation
            item = await prioritization_service.create_prioritization_item({
                "workspace_id": self.workspace_id,
                "name": "Dark Mode Support",
                "description": "High user demand for OLED dark mode",
                "category": "feature_request",
                "reach": 5000.0,
                "impact": 2.0,
                "confidence": 0.9,
                "effort": 1.5,
                "value": 8.0,
                "moscow": "should_have"
            })
            self.assertIsNotNone(item)
            self.assertEqual(item["value_vs_effort"]["quadrant"], "quick_win")
            self.assertGreater(item["rice"]["score"], 5000.0)

            # 2. Update Weights
            weights = await prioritization_service.save_workspace_weights(self.workspace_id, {
                "customer_demand_weight": 0.40,
                "business_impact_weight": 0.30,
                "feasibility_weight": 0.20,
                "risk_mitigation_weight": 0.10,
            })
            self.assertEqual(weights["customer_demand_weight"], 0.40)

            # 3. List items
            items = await prioritization_service.get_prioritization_items(self.workspace_id)
            self.assertGreaterEqual(len(items), 1)

        asyncio.run(_run())

    def test_copilot_service_pipeline(self):
        async def _run():
            chat_res = await copilot_service.chat_with_pm_copilot(
                workspace_id=self.workspace_id,
                message="What should our primary product focus be for next sprint?",
                session_id="integration_test"
            )
            self.assertIn("reply", chat_res)
            self.assertIn("session_id", chat_res)
            self.assertIsInstance(chat_res["sources_cited"], list)
            self.assertIsInstance(chat_res["suggested_followups"], list)

            # History check
            history = await copilot_service.get_copilot_history(self.workspace_id, "integration_test")
            self.assertGreaterEqual(len(history), 2)  # user + assistant

            # Clear
            cleared = await copilot_service.clear_copilot_history(self.workspace_id, "integration_test")
            self.assertTrue(cleared)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
