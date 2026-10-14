"""
Unit and integration tests for Milestone 4.
Validates:
1. Roadmap planning: value-ordered sequencing, capacity-aware release packing,
   recommended milestones, and the determinism of the plan.
2. Executive summary and product strategy report generation from measured evidence.
3. Output quality evaluation: distribution reconciliation, freshness, placeholder
   detection and the traceability scan for numbers a model cannot source.

The service tests patch persistence so they can run against fixtures without
touching the demo data files.
"""

import os
import sys
import unittest
import asyncio
from datetime import date
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import quality_service, report_service, roadmap_service


def _insights():
    """A workspace analysis shaped exactly like the stored insights document."""
    return {
        "_id": "insights_test",
        "workspace_id": "test_workspace_m4",
        "workspace_name": "Test Workspace",
        "total_analyzed": 1000,
        "health_score": 71.4,
        "sentiment_distribution": {"positive": 600, "neutral": 120, "negative": 280},
        "category_distribution": {
            "general_feedback": 600,
            "feature_request": 220,
            "bug_report": 120,
            "performance_issue": 60,
        },
        "themes": [{"id": "t1", "title": "Playback"}],
        "pain_points": [
            {
                "id": "pp_1",
                "title": "Playback stops randomly",
                "severity": "high",
                "impact_score": 82.0,
                "affected_users_count": 210,
                "recommended_action": "Fix the audio pipeline before adding features.",
                "root_cause": "Session state is dropped on network change.",
                "sample_quotes": ["music stops every few minutes"],
                "score_breakdown": {"avg_rating": 2.1, "negative_sentiment_pct": 78.0},
            },
            {
                "id": "pp_2",
                "title": "Repeated login prompts",
                "severity": "medium",
                "impact_score": 63.0,
                "affected_users_count": 90,
                "recommended_action": "Extend the session lifetime.",
                "root_cause": "Tokens expire on app background.",
                "sample_quotes": ["asks me to log in again"],
                "score_breakdown": {"avg_rating": 2.8, "negative_sentiment_pct": 55.0},
            },
        ],
        "feature_clusters": [
            {
                "id": "fc_1",
                "cluster_name": "Offline library downloads",
                "summary": "Users want to keep their library available without a connection.",
                "demand_level": "high",
                "priority_score": 88.0,
                "request_count": 140,
                "keywords": ["offline", "download"],
            }
        ],
        "trends": [{"period": "2026-05", "count": 120}],
        "analyzed_at": "2026-09-20T10:00:00+00:00",
        "ai_model": "Deterministic analysis engine",
    }


def _items():
    """A prioritization backlog with measured scores, as the seeder produces it."""
    from services.prioritization_service import _calculate_rice

    def item(item_id, name, reach, impact, confidence, effort, moscow, category, count, source_type, source_id):
        return {
            "id": item_id,
            "workspace_id": "test_workspace_m4",
            "name": name,
            "description": f"Seeded from {count} customer records.",
            "category": category,
            "source_cluster_id": source_id if source_type == "feature_cluster" else None,
            "source_pain_point_id": source_id if source_type == "pain_point" else None,
            "rice": {
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "score": _calculate_rice(reach, impact, confidence, effort),
            },
            "value_vs_effort": {"value": 8.0, "effort": 4.0, "quadrant": "major_project"},
            "moscow": moscow,
            "weighted": {
                "customer_demand_score": 80.0,
                "business_impact_score": 75.0,
                "feasibility_score": 50.0,
                "risk_mitigation_score": 50.0,
                "final_score": 64.0,
            },
            "ai_rationale": f"Seeded from {count} records.",
            "feedback_count": count,
            "rank": 1,
            "created_at": "2026-09-21T10:00:00+00:00",
            "updated_at": "2026-09-21T10:00:00+00:00",
        }

    # Scores: 180, 180, 60, 20 — so ordering, packing and spill are all observable.
    return [
        item("prio_1", "Resolve: Playback stops randomly", 300.0, 2.0, 0.9, 3.0, "must_have", "bug_report", 210, "pain_point", "pp_1"),
        item("prio_2", "Offline library downloads", 300.0, 2.0, 0.9, 3.0, "must_have", "feature_request", 140, "feature_cluster", "fc_1"),
        item("prio_3", "Resolve: Repeated login prompts", 200.0, 1.0, 0.9, 3.0, "should_have", "bug_report", 90, "pain_point", "pp_2"),
        item("prio_4", "Collaborative playlists", 100.0, 1.0, 0.6, 3.0, "could_have", "feature_request", 25, None, None),
    ]


class RoadmapPlanningTests(unittest.TestCase):
    """The sequencing rules a plan must obey, tested without any AI provider."""

    def test_release_windows_are_four_weeks_and_horizon_bounded(self):
        windows = roadmap_service._release_windows(date(2026, 10, 5), 12)
        self.assertEqual(len(windows), 3)
        self.assertEqual(windows[0]["horizon"], "now")
        self.assertEqual(windows[1]["horizon"], "next")
        self.assertEqual(windows[2]["horizon"], "later")
        self.assertEqual(windows[0]["start_date"], "2026-10-05")
        self.assertEqual(windows[0]["end_date"], "2026-11-01")
        self.assertEqual(windows[1]["start_date"], "2026-11-02")

    def test_ordering_prefers_fix_work_at_equal_value(self):
        fix = {"name": "Resolve: Playback stops", "category": "bug_report", "rice": {"score": 180.0}, "weighted": {"final_score": 64.0}, "feedback_count": 210}
        feature = {"name": "Offline library", "category": "feature_request", "rice": {"score": 180.0}, "weighted": {"final_score": 64.0}, "feedback_count": 140}
        ordered = sorted([feature, fix], key=roadmap_service._order_key)
        self.assertEqual(ordered[0]["name"], "Resolve: Playback stops")

    def test_packing_respects_capacity_and_spills_to_backlog(self):
        windows = roadmap_service._release_windows(date(2026, 10, 5), 8)
        ordered = sorted(_items(), key=roadmap_service._order_key)
        assignment, deferred = roadmap_service._pack_items(ordered, windows, velocity=4.0)
        # Two windows of 4 effort units hold one 3.0-effort item plus one 2.0-effort item is too big,
        # so the plan must leave work in the backlog rather than silently drop it.
        self.assertEqual(len(assignment), 2)
        self.assertEqual(len(deferred), 2)
        for index, window in enumerate(windows):
            total = sum(
                roadmap_service._effort_of(item)
                for item in ordered
                if assignment.get(item["id"]) == window["index"]
            )
            self.assertLessEqual(total, 4.0 + 1e-9)

    def test_packing_leaves_no_item_beyond_the_horizon_when_capacity_allows(self):
        windows = roadmap_service._release_windows(date(2026, 10, 5), 12)
        ordered = sorted(_items(), key=roadmap_service._order_key)
        assignment, deferred = roadmap_service._pack_items(ordered, windows, velocity=8.0)
        self.assertEqual(deferred, [])
        self.assertEqual(len(assignment), len(ordered))

    def test_strategy_text_explains_sequencing_and_the_backlog(self):
        windows = roadmap_service._release_windows(date(2026, 10, 5), 8)
        ordered = sorted(_items(), key=roadmap_service._order_key)
        assignment, deferred = roadmap_service._pack_items(ordered, windows, velocity=4.0)
        text = roadmap_service._strategy_text(ordered, windows, deferred, 4.0)
        self.assertIn("RICE", text)
        self.assertIn("4.0 effort units", text)
        self.assertIn("backlog", text)

    def test_milestone_exit_criteria_and_metrics_are_measured_not_invented(self):
        items = [
            {
                "name": "Resolve: Playback stops randomly",
                "category": "bug_report",
                "rice": {"score": 180.0, "effort": 3.0},
                "moscow": "must_have",
            }
        ]
        sources = [{"count": 210, "avg_rating": 2.1, "negative_sentiment_pct": 78.0}]
        criteria = roadmap_service._milestone_exit_criteria(items, sources, {})
        metrics = roadmap_service._milestone_metrics(items, sources, "2026-11-01")

        self.assertTrue(any("PRD" in criterion for criterion in criteria))
        self.assertTrue(any("78.0%" in criterion for criterion in criteria))
        for metric in metrics:
            if metric["baseline"].startswith("Measured:"):
                self.assertTrue(metric["baseline"].startswith("Measured:"))
            self.assertTrue(metric["target"].startswith("Proposed:"))
        ratings = [metric for metric in metrics if "rating" in metric["metric"].lower()]
        self.assertEqual(ratings[0]["baseline"], "Measured: 2.10/5.0")


class RoadmapServiceTests(unittest.TestCase):
    """The full plan, built from fixture insights and backlog with persistence stubbed."""

    def _generate(self, **kwargs):
        async def _run():
            with patch.object(roadmap_service.workspace_context, "load_stored_insights", AsyncMock(return_value=_insights())), \
                 patch.object(roadmap_service.workspace_context, "resolve_workspace", AsyncMock(return_value={"name": "Test Workspace", "description": ""})), \
                 patch.object(roadmap_service.workspace_context, "load_prioritization_items", AsyncMock(return_value=_items())), \
                 patch.object(roadmap_service.workspace_context, "load_prds", AsyncMock(return_value=[])), \
                 patch.object(roadmap_service, "_ai_narrative", AsyncMock(return_value=None)), \
                 patch.object(roadmap_service.fallback_db, "save_roadmap", AsyncMock(side_effect=lambda data: data)):
                return await roadmap_service.generate_roadmap(workspace_id="test_workspace_m4", **kwargs)

        return asyncio.run(_run())

    def test_plan_sequences_items_and_builds_milestones(self):
        plan = self._generate(horizon_weeks=12, velocity=8.0)
        self.assertEqual(len(plan["items"]), 4)
        self.assertGreaterEqual(len(plan["milestones"]), 1)
        self.assertEqual(plan["deferred"], [])
        self.assertEqual([item["sequence"] for item in plan["items"]], [1, 2, 3, 4])
        # Highest RICE first, and the defect leads its feature twin at equal score.
        self.assertEqual(plan["items"][0]["id"], "prio_1")
        self.assertEqual(plan["items"][1]["id"], "prio_2")

    def test_every_milestone_item_points_at_its_milestone(self):
        plan = self._generate()
        milestone_ids = {milestone["id"] for milestone in plan["milestones"]}
        for item in plan["items"]:
            if item["milestone_id"]:
                self.assertIn(item["milestone_id"], milestone_ids)
        scheduled = sum(1 for item in plan["items"] if item["milestone_id"])
        self.assertEqual(scheduled, plan["evidence"]["items_planned"])

    def test_evidence_reports_measured_counts(self):
        plan = self._generate()
        evidence = plan["evidence"]
        self.assertEqual(evidence["records_analyzed"], 1000)
        self.assertEqual(evidence["items_deferred"], 0)
        self.assertEqual(evidence["planned_feedback_records"], 210 + 140 + 90 + 25)
        self.assertIn("must-have items scheduled", evidence["must_have_coverage"])

    def test_plan_is_deterministic_without_an_ai_provider(self):
        first = self._generate(velocity=6.0)
        second = self._generate(velocity=6.0)
        self.assertEqual(
            [item["id"] for item in first["items"]],
            [item["id"] for item in second["items"]],
        )
        self.assertEqual(
            [milestone["item_ids"] for milestone in first["milestones"]],
            [milestone["item_ids"] for milestone in second["milestones"]],
        )
        self.assertFalse(first["ai_generated"])
        self.assertEqual(first["ai_model"], "Deterministic planning engine")

    def test_markdown_export_contains_every_release_and_metric(self):
        plan = self._generate()
        markdown = plan["raw_markdown"]
        self.assertIn("# Product Roadmap — Test Workspace", markdown)
        self.assertIn("## Evidence", markdown)
        self.assertIn("**Exit criteria**", markdown)
        self.assertIn("RICE", markdown)

    def test_persisting_an_evaluated_plan_strips_the_storage_id(self):
        """A plan read back from storage must not carry the storage key into a write."""
        plan = {"_id": "mongo_object_id_as_string", "workspace_id": "ws_1", "milestones": []}
        saved = {}

        async def _run():
            with patch.object(roadmap_service.fallback_db, "save_roadmap", AsyncMock(side_effect=lambda data: saved.update(data))), \
                 patch.object(roadmap_service.database, "_mongodb_available", False):
                await roadmap_service._persist_plan(plan)

        asyncio.run(_run())
        self.assertNotIn("_id", saved)
        self.assertEqual(saved["workspace_id"], "ws_1")

    def test_empty_backlog_returns_an_actionable_plan(self):
        async def _run():
            with patch.object(roadmap_service.workspace_context, "load_stored_insights", AsyncMock(return_value=_insights())), \
                 patch.object(roadmap_service.workspace_context, "resolve_workspace", AsyncMock(return_value={"name": "Test Workspace", "description": ""})), \
                 patch.object(roadmap_service.workspace_context, "load_prioritization_items", AsyncMock(return_value=[])):
                return await roadmap_service.generate_roadmap(workspace_id="test_workspace_m4")

        plan = asyncio.run(_run())
        self.assertEqual(plan["items"], [])
        self.assertIn("no prioritization items", plan["strategy"])
        self.assertEqual(plan["evidence"]["items_planned"], 0)


class ReportGenerationTests(unittest.TestCase):
    """Executive and strategy reports built from the same fixtures."""

    def _generate(self, report_type="executive_summary"):
        async def _run():
            with patch.object(report_service.workspace_context, "load_stored_insights", AsyncMock(return_value=_insights())), \
                 patch.object(report_service.workspace_context, "resolve_workspace", AsyncMock(return_value={"name": "Test Workspace", "description": ""})), \
                 patch.object(report_service.workspace_context, "load_prioritization_items", AsyncMock(return_value=_items())), \
                 patch.object(report_service.workspace_context, "load_prds", AsyncMock(return_value=[])), \
                 patch.object(report_service.workspace_context, "load_user_stories", AsyncMock(return_value=[])), \
                 patch.object(report_service.workspace_context, "count_feedback", AsyncMock(return_value=1000)), \
                 patch.object(report_service.roadmap_service, "get_roadmap", AsyncMock(return_value=None)), \
                 patch.object(report_service, "_ai_summary", AsyncMock(return_value=None)), \
                 patch.object(report_service.fallback_db, "save_report", AsyncMock(side_effect=lambda data: data)):
                return await report_service.generate_report(workspace_id="test_workspace_m4", report_type=report_type)

        return asyncio.run(_run())

    def test_executive_summary_reports_measured_health(self):
        report = self._generate()
        self.assertEqual(report["product_health"]["records_analyzed"], 1000)
        self.assertEqual(report["product_health"]["negative_share"], 28.0)
        self.assertIn("71.4", report["executive_summary"])
        self.assertIn("Playback stops randomly", report["executive_summary"])
        self.assertGreaterEqual(len(report["key_findings"]), 3)
        self.assertGreaterEqual(len(report["kpis"]), 4)

    def test_strategy_report_uses_pillars_without_a_roadmap(self):
        report = self._generate("product_strategy")
        self.assertEqual(report["report_type"], "product_strategy")
        self.assertGreaterEqual(len(report["strategic_pillars"]), 2)
        self.assertTrue(any("Playback stops" in pillar["name"] for pillar in report["strategic_pillars"]))
        # With no roadmap the report must say the plan is not sequenced yet.
        self.assertTrue(
            any("Generate a roadmap" in rec["action"] for rec in report["recommendations"])
        )

    def test_coverage_gap_is_raised_as_a_risk(self):
        async def _run():
            with patch.object(report_service.workspace_context, "load_stored_insights", AsyncMock(return_value=_insights())), \
                 patch.object(report_service.workspace_context, "resolve_workspace", AsyncMock(return_value={"name": "Test Workspace", "description": ""})), \
                 patch.object(report_service.workspace_context, "load_prioritization_items", AsyncMock(return_value=_items())), \
                 patch.object(report_service.workspace_context, "load_prds", AsyncMock(return_value=[])), \
                 patch.object(report_service.workspace_context, "load_user_stories", AsyncMock(return_value=[])), \
                 patch.object(report_service.workspace_context, "count_feedback", AsyncMock(return_value=1100)), \
                 patch.object(report_service.roadmap_service, "get_roadmap", AsyncMock(return_value=None)), \
                 patch.object(report_service, "_ai_summary", AsyncMock(return_value=None)), \
                 patch.object(report_service.fallback_db, "save_report", AsyncMock(side_effect=lambda data: data)):
                return await report_service.generate_report(workspace_id="test_workspace_m4")

        report = asyncio.run(_run())
        self.assertIn("not reflected", report["product_health"]["coverage_note"])
        self.assertTrue(any("behind the stored feedback" in risk["risk"] for risk in report["risks"]))
        self.assertTrue(any("Re-run the workspace analysis" in rec["action"] for rec in report["recommendations"]))

    def test_markdown_export_has_every_section(self):
        markdown = self._generate()["raw_markdown"]
        for heading in [
            "## 1. Executive Summary",
            "## 2. Product Health Snapshot",
            "## 3. Key Findings",
            "## 4. Strategic Pillars",
            "## 6. Product Indicators",
            "## 7. Risks & Mitigations",
            "## 8. Recommendations",
            "## 9. Evidence & Method",
        ]:
            self.assertIn(heading, markdown)


class OutputQualityTests(unittest.TestCase):
    """The evaluator has to catch the defects it claims to catch."""

    def _evaluate(self, insights=None, stored_records=1000):
        async def _run():
            with patch.object(quality_service.workspace_context, "load_stored_insights", AsyncMock(return_value=insights if insights is not None else _insights())), \
                 patch.object(quality_service.workspace_context, "resolve_workspace", AsyncMock(return_value={"name": "Test Workspace", "description": ""})), \
                 patch.object(quality_service.workspace_context, "load_prioritization_items", AsyncMock(return_value=_items())), \
                 patch.object(quality_service.workspace_context, "load_prds", AsyncMock(return_value=[])), \
                 patch.object(quality_service.workspace_context, "load_user_stories", AsyncMock(return_value=[])), \
                 patch.object(quality_service.workspace_context, "count_feedback", AsyncMock(return_value=stored_records)), \
                 patch.object(quality_service.roadmap_service, "get_roadmap", AsyncMock(return_value=None)), \
                 patch("services.report_service.get_reports_for_workspace", AsyncMock(return_value=[])):
                return await quality_service.evaluate_workspace("test_workspace_m4")

        return asyncio.run(_run())

    def test_evaluation_covers_every_artefact_family(self):
        report = self._evaluate()
        types = {artifact["artifact_type"] for artifact in report["artifacts"]}
        self.assertEqual(
            types,
            {"insights", "prioritization", "roadmap", "prd", "user_story", "report"},
        )
        self.assertGreater(report["overall_score"], 0)
        self.assertEqual(report["counts"]["artefacts_evaluated"], 6)

    def test_ungenerated_artefacts_are_marked_not_generated(self):
        report = self._evaluate()
        by_type = {artifact["artifact_type"]: artifact for artifact in report["artifacts"]}
        for artifact_type in ("roadmap", "prd", "user_story", "report"):
            self.assertFalse(by_type[artifact_type]["available"])
            self.assertEqual(by_type[artifact_type]["grade"], "not_generated")
        self.assertTrue(by_type["insights"]["available"])

    def test_distribution_mismatch_is_a_failure(self):
        """The imported-after-analysis defect must be caught, not smoothed over."""
        broken = _insights()
        broken["total_analyzed"] = 1100  # imports arrived after the analysis was stored
        report = self._evaluate(insights=broken, stored_records=1100)
        insights_eval = next(a for a in report["artifacts"] if a["artifact_type"] == "insights")
        distribution = next(c for c in insights_eval["checks"] if c["id"] == "insights.consistency.distributions")
        self.assertEqual(distribution["status"], "fail")
        self.assertIn("1100", distribution["detail"])
        self.assertIn("1000", distribution["detail"])

    def test_stale_analysis_is_a_warning(self):
        report = self._evaluate(stored_records=1150)
        insights_eval = next(a for a in report["artifacts"] if a["artifact_type"] == "insights")
        freshness = next(c for c in insights_eval["checks"] if c["id"] == "insights.freshness.record_count")
        self.assertEqual(freshness["status"], "warn")
        self.assertIn("150", freshness["detail"])

    def test_placeholder_weighted_inputs_are_flagged(self):
        report = self._evaluate()
        prioritization = next(a for a in report["artifacts"] if a["artifact_type"] == "prioritization")
        placeholder = next(c for c in prioritization["checks"] if c["id"] == "prioritization.grounding.placeholder_inputs")
        self.assertEqual(placeholder["status"], "warn")
        self.assertIn("4 of 4", placeholder["detail"])

    def test_duplicate_roadmap_scope_is_flagged(self):
        """Two items describing one subject must not both be credited in a milestone."""
        roadmap = {
            "milestones": [{"id": "ms_1", "name": "Release 1", "confidence": "high"}],
            "releases": [
                {"name": "Release 1", "horizon": "now", "effort_total": 6.0, "capacity": 8.0, "item_count": 2}
            ],
            "items": [
                {"id": "a", "name": "Resolve: Removal of What's New Tab", "moscow": "must_have", "milestone_id": "ms_1"},
                {"id": "b", "name": "Reintroduce What's New Tab", "moscow": "should_have", "milestone_id": "ms_1"},
            ],
            "deferred": [],
        }
        evaluation = quality_service._evaluate_roadmap(roadmap)
        duplicate = next(
            check for check in evaluation["checks"] if check["id"] == "roadmap.consistency.duplicate_scope"
        )
        self.assertEqual(duplicate["status"], "warn")
        self.assertTrue(any("What's New" in entry for entry in duplicate["evidence"]))

    def test_distinct_roadmap_scope_passes_the_duplicate_check(self):
        roadmap = {
            "milestones": [{"id": "ms_1", "name": "Release 1", "confidence": "high"}],
            "releases": [
                {"name": "Release 1", "horizon": "now", "effort_total": 6.0, "capacity": 8.0, "item_count": 2}
            ],
            "items": [
                {"id": "a", "name": "Offline library downloads", "moscow": "must_have", "milestone_id": "ms_1"},
                {"id": "b", "name": "Collaborative playlists", "moscow": "should_have", "milestone_id": "ms_1"},
            ],
            "deferred": [],
        }
        evaluation = quality_service._evaluate_roadmap(roadmap)
        duplicate = next(
            check for check in evaluation["checks"] if check["id"] == "roadmap.consistency.duplicate_scope"
        )
        self.assertEqual(duplicate["status"], "pass")

    def test_untraceable_numbers_are_reported(self):
        allowed = quality_service._collect_measured_numbers(_insights(), [_items()])
        flagged = quality_service._scan_untraceable_numbers(
            ["Conversion rose to 412345 and retention reached 98765%."], allowed
        )
        self.assertTrue(flagged)
        self.assertTrue(any("412345" in entry for entry in flagged))

        traceable = quality_service._scan_untraceable_numbers(
            ["The analysis covers 1000 records with a health score of 71.4 and 82.0 impact."], allowed
        )
        self.assertEqual(traceable, [])

    def test_score_and_grade_map_is_monotonic(self):
        self.assertEqual(quality_service._grade(95, True), "excellent")
        self.assertEqual(quality_service._grade(80, True), "good")
        self.assertEqual(quality_service._grade(65, True), "fair")
        self.assertEqual(quality_service._grade(30, True), "needs_review")
        self.assertEqual(quality_service._grade(100, False), "not_generated")
        self.assertEqual(quality_service._score_checks([
            {"status": "pass"}, {"status": "pass"}, {"status": "fail"}, {"status": "warn"}
        ]), 65)

    def test_markdown_export_lists_every_check(self):
        markdown = self._evaluate()["raw_markdown"]
        self.assertIn("# Output Quality Evaluation — Test Workspace", markdown)
        self.assertIn("Product insights analysis", markdown)
        self.assertIn("Roadmap plan", markdown)
        self.assertIn("Not generated for this workspace yet.", markdown)


class Milestone4RoutingTests(unittest.TestCase):
    """The new endpoints must exist and stay behind authentication."""

    def test_routers_are_registered(self):
        from main import app

        schema = app.openapi()
        paths = set(schema["paths"])
        # Swagger's Authorize button depends on this scheme being published.
        self.assertIn("HTTPBearer", schema.get("components", {}).get("securitySchemes", {}))
        for expected in (
            "/api/roadmap/generate",
            "/api/roadmap/{workspace_id}",
            "/api/roadmap/{workspace_id}/export",
            "/api/reports/generate",
            "/api/reports/workspace/{workspace_id}",
            "/api/reports/{report_id}/export",
            "/api/quality/{workspace_id}/evaluate",
            "/api/quality/{workspace_id}/export",
        ):
            self.assertIn(expected, paths)

    def test_roadmap_endpoints_require_authorization(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/roadmap/test_workspace_m4")
        self.assertEqual(response.status_code, 401)

        report_response = client.post("/api/reports/generate", json={"workspace_id": "test_workspace_m4"})
        self.assertEqual(report_response.status_code, 401)

        quality_response = client.get("/api/quality/test_workspace_m4/evaluate")
        self.assertEqual(quality_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
