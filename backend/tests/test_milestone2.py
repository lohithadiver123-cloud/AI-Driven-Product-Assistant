"""
Milestone 2 Validation Test Suite.
Validates:
1. Theme extraction & NLP topic mining
2. Customer pain-point detection and impact severity scoring
3. Feature request clustering and aggregation accuracy
4. Temporal trend analysis and Product Health Score calculation
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.theme_extraction import (
    extract_themes_from_feedback,
    extract_pain_points_from_feedback,
    extract_keywords_and_phrases,
    assign_record_theme,
)
from services.clustering import cluster_feature_requests
from services.trend_analysis import generate_trend_analysis, calculate_health_score


class InsightsMergeValidation(unittest.TestCase):
    """The AI layer must attach its pain points to matching evidence, not to positions."""

    def test_ai_pain_points_pair_with_their_own_evidence(self):
        from routers.insights import _merge_ai_pain_points

        def record(index, text):
            return {"_id": str(index), "title": "", "content": text, "rating": 1, "sentiment": "negative"}

        feedback = [
            record(1, "too many ads, cannot skip them at all"),
            record(2, "app crashes every time I open a playlist"),
        ]
        # Deterministic groups in the opposite order to the AI list.
        pain_points = [
            {
                "id": "pain_point_1",
                "title": "Friction in Performance & Stability",
                "sample_quotes": ["app crashes every time I open a playlist"],
                "category": "bug_report",
                "impact_score": 70.0,
            },
            {
                "id": "pain_point_2",
                "title": "Friction in UI & User Experience",
                "sample_quotes": ["too many ads, cannot skip them at all"],
                "category": "general_feedback",
                "impact_score": 50.0,
            },
        ]
        ai_pain_points = [
            {"title": "Excessive Ads with No Skip Option", "keywords": ["ads", "skip"], "impact_score": 85.0},
            {"title": "Frequent App Crashes", "keywords": ["crashes"], "impact_score": 88.0},
        ]

        merged = _merge_ai_pain_points(pain_points, ai_pain_points, feedback)
        by_title = {p["title"]: p for p in merged}

        self.assertIn("Frequent App Crashes", by_title)
        self.assertEqual(by_title["Frequent App Crashes"]["sample_quotes"], ["app crashes every time I open a playlist"])
        self.assertIn("Excessive Ads with No Skip Option", by_title)
        self.assertEqual(by_title["Excessive Ads with No Skip Option"]["sample_quotes"], ["too many ads, cannot skip them at all"])

    def test_cluster_evidence_matching_is_whole_word(self):
        from routers.insights import _match_records_by_terms

        records = [
            {"_id": "1", "content": "the ads are unbearable"},
            {"_id": "2", "content": "downloads are very slow"},
            {"_id": "3", "content": "no skip button for ads"},
        ]
        matched = _match_records_by_terms(records, ["ads"])
        self.assertEqual([r["_id"] for r in matched], ["1", "3"])


class Milestone2Validation(unittest.TestCase):
    def setUp(self):
        self.sample_dataset = [
            {
                "_id": "1",
                "title": "Login crash on iOS",
                "content": "The app crashes every time I enter my password on the signin screen.",
                "category": "bug_report",
                "sentiment": "negative",
                "rating": 1,
                "created_at": "2025-01-10T10:00:00",
            },
            {
                "_id": "2",
                "title": "Need dark mode support",
                "content": "Please add dark mode support! Working at night hurts my eyes.",
                "category": "feature_request",
                "sentiment": "positive",
                "rating": 5,
                "created_at": "2025-01-11T10:00:00",
            },
            {
                "_id": "3",
                "title": "Dark theme request",
                "content": "Would love a dark theme option in settings.",
                "category": "feature_request",
                "sentiment": "positive",
                "rating": 4,
                "created_at": "2025-01-12T10:00:00",
            },
            {
                "_id": "4",
                "title": "Very slow dashboard load times",
                "content": "Dashboard takes over 15 seconds to load. Performance is unacceptable.",
                "category": "performance_issue",
                "sentiment": "negative",
                "rating": 1,
                "created_at": "2025-01-13T10:00:00",
            },
            {
                "_id": "5",
                "title": "Export to CSV or PDF",
                "content": "Can we please export feedback reports as CSV or PDF for management meetings?",
                "category": "feature_request",
                "sentiment": "neutral",
                "rating": 4,
                "created_at": "2025-01-14T10:00:00",
            },
            {
                "_id": "6",
                "title": "Slack integration please",
                "content": "It would be great to receive real-time notifications in Slack via webhooks.",
                "category": "feature_request",
                "sentiment": "positive",
                "rating": 5,
                "created_at": "2025-01-15T10:00:00",
            },
        ]

    def test_extract_themes(self):
        themes = extract_themes_from_feedback(self.sample_dataset)
        self.assertGreater(len(themes), 0)

        # Themes are mined from the records, so the two dark-theme requests must show
        # up as an identifiable topic instead of a hardcoded domain label.
        dark_theme = next((t for t in themes if "dark" in " ".join(t["keywords"]).lower()), None)
        self.assertIsNotNone(dark_theme)
        self.assertGreaterEqual(dark_theme["frequency"], 2)

        # Every record is assigned to a mined theme (or honestly left unclassified).
        assigned = [assign_record_theme(f"{it['title']} {it['content']}", themes) for it in self.sample_dataset]
        self.assertEqual(len(assigned), len(self.sample_dataset))
        self.assertIn(dark_theme["title"], assigned)

        for theme in themes:
            self.assertIn("frequency", theme)
            self.assertIn("sentiment_score", theme)
            self.assertIn("keywords", theme)
            self.assertIn("match_phrases", theme)

    def test_extract_pain_points_severity_and_impact(self):
        pain_points = extract_pain_points_from_feedback(self.sample_dataset)
        self.assertGreater(len(pain_points), 0)

        # Pain point titles must be built from the complaint language itself.
        titles = [p["title"].lower() for p in pain_points]
        self.assertTrue(
            any(word in title for title in titles for word in ("login", "crash", "slow", "dashboard")),
            f"pain point titles are not grounded in the complaints: {titles}",
        )

        # Check severity and impact scores
        for pp in pain_points:
            self.assertIn(pp["severity"], ["high", "medium", "low"])
            self.assertGreaterEqual(pp["impact_score"], 0)
            self.assertLessEqual(pp["impact_score"], 100)
            self.assertTrue(len(pp["recommended_action"]) > 10)

    def test_feature_request_clustering(self):
        clusters = cluster_feature_requests(self.sample_dataset)
        self.assertGreater(len(clusters), 0)

        cluster_names = [c["cluster_name"] for c in clusters]
        # Dark mode requests (2 items) should be grouped into Dark Mode cluster
        dark_mode_cluster = next((c for c in clusters if "Dark Mode" in c["cluster_name"]), None)
        self.assertIsNotNone(dark_mode_cluster)
        self.assertGreaterEqual(dark_mode_cluster["request_count"], 2)
        self.assertIn("dark mode", [k.lower() for k in dark_mode_cluster["keywords"]])

    def test_trend_analysis_and_health_score(self):
        trends = generate_trend_analysis(self.sample_dataset)
        self.assertGreater(len(trends), 0)

        for pt in trends:
            self.assertIn("period", pt)
            self.assertIn("total_count", pt)
            self.assertIn("sentiment_score", pt)

        health_score = calculate_health_score(self.sample_dataset)
        self.assertGreaterEqual(health_score, 0.0)
        self.assertLessEqual(health_score, 100.0)

    def test_keyword_and_ngram_extraction(self):
        texts = [
            "Dark mode theme is awesome",
            "Dark mode theme requested by many users",
            "Export reports to CSV or Excel",
        ]
        phrases = extract_keywords_and_phrases(texts, top_k=5)
        phrase_words = [p[0] for p in phrases]
        self.assertTrue(any("dark" in p for p in phrase_words))

    def test_ai_status_and_models(self):
        from services.ai_service import check_ai_status, analyze_feedback_with_ai
        from models.insights import PainPointItem, WorkspaceInsightsResponse

        status = check_ai_status()
        self.assertIn("available", status)
        self.assertIn("provider", status)
        self.assertIn("model", status)
        # The provider is reported honestly in fallback-chain order, and "None" only when
        # no key at all is configured.
        if status["available"]:
            self.assertNotEqual(status["provider"], "None")
            self.assertTrue(status["model"])
            for name in status["provider"].split(" + "):
                self.assertIn(name, ["Gemini", "Mistral", "Groq", "OpenRouter"])
        else:
            self.assertEqual(status["provider"], "None")

        # Fallback handling on empty input
        res = analyze_feedback_with_ai([])
        self.assertIsNone(res)

        # Test model fields
        pp = PainPointItem(
            id="pp1",
            title="Search latency",
            description="Slow search queries",
            severity="high",
            impact_score=85.0,
            affected_users_count=5,
            category="performance_issue",
            root_cause="Missing database compound index on query keywords",
            recommended_action="Create text index"
        )
        self.assertEqual(pp.root_cause, "Missing database compound index on query keywords")


if __name__ == "__main__":
    unittest.main()

