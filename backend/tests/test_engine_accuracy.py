"""
Accuracy tests for the insight engines and the prioritisation seeder.

These cover the defects found by reading a real workspace's outputs:

1. Topics were labelled and scored from the model's own wording — corpus-wide vocabulary
   ("music", "song", "spotify") grouped overlapping records into several "different" pain
   points, and the model's impact number replaced the measured one.
2. Topic ids were rank-based, so re-running an analysis renumbered them and every
   document, backlog item and roadmap entry that linked to one silently pointed elsewhere.
3. The seeder invented customer reach (a sample count times 45-50), which made RICE a
   restatement of volume, and mapped severity straight to MoSCoW so 7 of 9 items were
   must-have.
4. Any title the model supplied counted as an already-upgraded one, so the raw algorithmic
   n-grams it left behind ("Pay Premium", "Skip Songs") kept reaching the dashboard, the PRD
   and the backlog even though an upgrader for them had been written.

Everything here runs offline and without a database.
"""

import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.insights import _ai_pain_point_terms, _ground_pain_point, _identify_topics
from services.clustering import cluster_feature_requests
from services.title_normalizer import (
    MAX_TITLE_ATTEMPTS,
    TITLE_SOURCE_AI,
    TITLE_SOURCE_HEURISTIC,
    needs_title_upgrade,
    normalize_topic_titles,
)
from services.prioritization_service import measured_priority_inputs
from services.quality_service import _evaluate_prioritization, _evaluate_roadmap
from services.roadmap_service import _EvidenceIndex
from services.text_mining import (
    absorb_overlapping_groups,
    distinctive_terms,
    stable_topic_id,
)
from services.theme_extraction import (
    extract_pain_points_from_feedback,
    measured_group_score,
)


def _corpus():
    """
    A music-app corpus shaped like the real one: generic vocabulary (music, listen) in
    almost every record, and two genuinely different issues underneath it — each of them
    a minority of the corpus, as a real issue is.
    """
    records = []
    for index in range(15):
        records.append({"content": f"the ads keep interrupting my music while i listen {index}", "rating": 1, "title": "ads"})
    for index in range(15):
        records.append({"content": f"the app crashes when i open the library {index}", "rating": 1, "title": "crash"})
    for index in range(70):
        records.append({"content": f"love the music and i listen every day {index}", "rating": 5, "title": "great"})
    return records


def _ads_records(corpus):
    return [record for record in corpus if "ads" in record["content"]]


class TopicHygieneTests(unittest.TestCase):
    """Labelling, scoring and id stability for mined topics."""

    def test_corpus_wide_terms_are_not_treated_as_topics(self):
        corpus = _corpus()
        kept = distinctive_terms(["music", "ads", "crashes", "listen", "playlist"], corpus, max_share=0.2)
        self.assertNotIn("music", kept)   # in almost every record
        self.assertNotIn("listen", kept)  # idem
        self.assertIn("ads", kept)
        self.assertIn("crashes", kept)

    def test_terms_that_match_nothing_are_dropped(self):
        self.assertEqual(distinctive_terms(["quantum", "ads"], _corpus()), ["ads"])

    def test_stable_id_ignores_word_order_and_word_choice(self):
        self.assertEqual(
            stable_topic_id("pain_point", "Cosmetic Ads"),
            stable_topic_id("pain_point", "Ads Cosmetic"),
        )
        self.assertNotEqual(
            stable_topic_id("pain_point", "Cosmetic Ads"),
            stable_topic_id("pain_point", "Playlist Crash"),
        )
        self.assertTrue(stable_topic_id("pain_point", "Cosmetic Ads").startswith("pain_point_"))

    def test_overlapping_groups_are_absorbed_with_their_alias(self):
        kept, absorbed = absorb_overlapping_groups(
            [("Playback Ads", {1, 2, 3, 4}), ("Interrupting Ads", {1, 2, 3}), ("Playlist Crash", {5, 6, 7})]
        )
        self.assertEqual([label for label, _ in kept], ["Playback Ads", "Playlist Crash"])
        self.assertEqual(absorbed, [("Interrupting Ads", "Playback Ads")])

    def test_measured_score_matches_the_documented_formula(self):
        corpus = _corpus()
        measured = measured_group_score(_ads_records(corpus), len(corpus))
        # volume 15/100 * 100 * 2 = 30 + rating penalty (5.0-1.0)*5 = 20
        # + negative share 100% of 25 = 25 + bug share 0 (no category is set on these records)
        self.assertEqual(measured["count"], 15)
        self.assertEqual(measured["impact_score"], 75.0)
        self.assertEqual(measured["negative_pct"], 100.0)
        self.assertEqual(measured["avg_rating"], 1.0)
        self.assertEqual(measured["severity"], "high")

    def test_mined_pain_point_ids_survive_reordering_of_the_corpus(self):
        corpus = _corpus()
        first = extract_pain_points_from_feedback(corpus)
        second = extract_pain_points_from_feedback(list(reversed(corpus)))
        self.assertEqual([point["id"] for point in first], [point["id"] for point in second])
        self.assertTrue(all(point["id"] != f"pain_point_{point['rank']}" for point in first))

    def test_mined_pain_points_carry_a_rank_and_a_stable_id(self):
        points = extract_pain_points_from_feedback(_corpus())
        self.assertTrue(points)
        for index, point in enumerate(points, start=1):
            self.assertEqual(point["rank"], index)
            self.assertTrue(point["id"].startswith("pain_point_"))
            self.assertGreater(point["affected_users_count"], 0)

    def test_cluster_ids_are_stable_across_runs(self):
        def requests():
            return [
                {"content": "please add offline downloads for my albums", "rating": 5},
                {"content": "i want offline downloads of playlists", "rating": 5},
                {"content": "would like an equaliser for bass", "rating": 4},
                {"content": "please add an equaliser with bass control", "rating": 4},
            ]

        first = cluster_feature_requests(requests())
        second = cluster_feature_requests(requests())
        self.assertEqual([cluster["id"] for cluster in first], [cluster["id"] for cluster in second])
        self.assertTrue(all(cluster["id"].startswith("cluster_") for cluster in first))


class GroundingTests(unittest.TestCase):
    """How AI-sourced topics are grounded, measured and collapsed."""

    def test_grounding_matches_whole_words_only(self):
        corpus = [
            {"content": "offline downloads never finish", "rating": 2, "title": ""},
            {"content": "the ads are everywhere", "rating": 1, "title": "ads"},
        ]
        grounded = _ground_pain_point({"title": "Ads", "keywords": ["ads"]}, ["ads"], corpus)
        self.assertEqual(grounded["affected_users_count"], 1)  # "downloads" is not a mention of "ads"

    def test_grounding_uses_measured_score_and_keeps_the_model_title_as_provenance(self):
        corpus = _corpus()
        grounded = _ground_pain_point(
            {"title": "Pay Premium", "keywords": ["ads"], "impact_score": 98.0},
            ["ads"],
            corpus,
        )
        # The same records scored by measurement: the model's 98.0 is not used for priority.
        expected = measured_group_score(_ads_records(corpus), len(corpus))
        self.assertEqual(grounded["impact_score"], expected["impact_score"])
        self.assertEqual(grounded["severity"], expected["severity"])
        self.assertEqual(grounded["affected_users_count"], expected["count"])
        self.assertEqual(grounded["ai_title"], "Pay Premium")
        self.assertNotEqual(grounded["title"], "Pay Premium")                # labelled from the records
        self.assertIn("negative_sentiment_pct", grounded["score_breakdown"])

    def test_topics_sharing_a_fallback_label_stay_separate(self):
        """Two groups the miner could not name must not absorb each other."""
        topics = [
            {"title": "Unclassified complaints", "keywords": ["ads"], "impact_score": 75.0},
            {"title": "Unclassified complaints", "keywords": ["crashes"], "impact_score": 90.0},
        ]
        identified = _identify_topics(topics, _corpus(), "pain_point")
        self.assertEqual(len(identified), 2)
        self.assertNotEqual(identified[0]["id"], identified[1]["id"])

    def test_model_terms_that_describe_the_whole_corpus_are_dropped(self):
        terms = _ai_pain_point_terms(
            {"title": "Music Ads", "keywords": ["music", "ads", "listen"]},
            _corpus(),
        )
        self.assertNotIn("music", terms)
        self.assertNotIn("listen", terms)
        self.assertIn("ads", terms)

    def test_identical_topics_collapse_and_record_their_alias(self):
        topics = [
            {"title": "Ads Interrupting", "keywords": ["ads"], "impact_score": 80.0, "affected_users_count": 40},
            {"title": "Ads Annoying", "keywords": ["ads"], "impact_score": 60.0, "affected_users_count": 40},
            {"title": "Crashes", "keywords": ["crashes"], "impact_score": 70.0, "affected_users_count": 30},
        ]
        identified = _identify_topics(topics, _corpus(), "pain_point")
        self.assertEqual([topic["title"] for topic in identified], ["Ads Interrupting", "Crashes"])
        self.assertEqual(identified[0]["also_described_as"], ["Ads Annoying"])
        self.assertEqual(identified[0]["rank"], 1)
        self.assertTrue(identified[0]["id"].startswith("pain_point_"))


class SeederInputTests(unittest.TestCase):
    """The prioritisation seeder must measure reach and discriminate MoSCoW."""

    def test_reach_is_the_measured_count(self):
        self.assertEqual(measured_priority_inputs(615, "high")["reach"], 615.0)

    def test_impact_and_confidence_are_differentiated(self):
        big = measured_priority_inputs(615, "high")
        mid = measured_priority_inputs(120, "high")
        small = measured_priority_inputs(18, "high")
        self.assertEqual([big["impact"], mid["impact"], small["impact"]], [3.0, 2.0, 1.0])
        self.assertEqual([big["confidence"], mid["confidence"], small["confidence"]], [0.9, 0.8, 0.7])
        # A tiny pain point can no longer be a must-have.
        self.assertEqual(big["moscow"], "must_have")
        self.assertEqual(mid["moscow"], "must_have" if mid["reach"] >= 100 else "should_have")
        self.assertEqual(small["moscow"], "should_have")

    def test_effort_is_an_explicit_placeholder(self):
        self.assertEqual(measured_priority_inputs(615, "high")["effort"], 2.0)

    def test_an_unknown_urgency_falls_back_to_medium(self):
        self.assertEqual(measured_priority_inputs(50, "urgent")["impact"], 1.0)


class LinkIntegrityTests(unittest.TestCase):
    """Stale provenance must be reported, not silently ignored."""

    def _insights(self):
        return {
            "pain_points": [{"id": "pain_point_abc", "title": "Ads Interrupting", "affected_users_count": 40}],
            "feature_clusters": [{"id": "cluster_def", "cluster_name": "Offline Downloads", "request_count": 20}],
        }

    def _items(self, source_key, source_id, name):
        return [
            {
                "id": "prio_1",
                "name": name,
                source_key: source_id,
                "rice": {"score": 100.0, "effort": 2.0},
                "weighted": {"feasibility_score": 50.0, "risk_mitigation_score": 50.0, "final_score": 60.0},
                "moscow": "must_have",
                "ai_rationale": "Measured: 40 records.",
            }
        ]

    def test_resolving_links_pass(self):
        evaluation = _evaluate_prioritization(
            self._items("source_pain_point_id", "pain_point_abc", "Resolve: Ads Interrupting"),
            self._insights(),
        )
        check = next(c for c in evaluation["checks"] if c["id"] == "prioritization.grounding.source_links")
        self.assertEqual(check["status"], "pass")

    def test_dangling_links_fail(self):
        evaluation = _evaluate_prioritization(
            self._items("source_cluster_id", "ai_cluster_1", "Offline Downloads"),
            self._insights(),
        )
        check = next(c for c in evaluation["checks"] if c["id"] == "prioritization.grounding.source_links")
        self.assertEqual(check["status"], "fail")
        self.assertIn("ai_cluster_1", check["detail"])

    def test_a_link_to_the_wrong_topic_warns(self):
        evaluation = _evaluate_prioritization(
            self._items("source_pain_point_id", "pain_point_abc", "Resolve: Frequent App Crashes"),
            self._insights(),
        )
        check = next(c for c in evaluation["checks"] if c["id"] == "prioritization.grounding.source_links")
        self.assertEqual(check["status"], "warn")
        self.assertIn("Ads Interrupting", check["detail"])

    def test_missing_analysis_fails_the_check(self):
        evaluation = _evaluate_prioritization(self._items("source_pain_point_id", "pain_point_abc", "Anything"), None)
        check = next(c for c in evaluation["checks"] if c["id"] == "prioritization.grounding.source_links")
        self.assertEqual(check["status"], "fail")

    def test_roadmap_evidence_reattaches_a_stale_link_by_name(self):
        index = _EvidenceIndex(self._insights())
        evidence = index.for_item(
            {"name": "Resolve: Ads Interrupting", "source_pain_point_id": "pain_point_1", "feedback_count": 0}
        )
        self.assertEqual(evidence["source_type"], "pain_point")
        self.assertEqual(evidence["count"], 40)

    def test_roadmap_evidence_reports_no_source_when_nothing_matches(self):
        index = _EvidenceIndex(self._insights())
        evidence = index.for_item({"name": "Security hardening", "source_cluster_id": "ai_cluster_9"})
        self.assertEqual(evidence["source_type"], "prioritization")
        self.assertEqual(evidence["count"], 0)


class RoadmapQualityTests(unittest.TestCase):
    """The duplicate-scope and capacity checks still hold after the id changes."""

    def test_duplicate_scope_is_still_detected_with_new_ids(self):
        roadmap = {
            "milestones": [{"id": "ms_1", "name": "Release 1", "confidence": "high"}],
            "releases": [{"name": "Release 1", "horizon": "now", "effort_total": 4.0, "capacity": 8.0, "item_count": 2}],
            "items": [
                {"id": "cluster_a", "name": "Offline Downloads", "moscow": "must_have", "milestone_id": "ms_1"},
                {"id": "pain_point_b", "name": "Downloads Offline", "moscow": "should_have", "milestone_id": "ms_1"},
            ],
            "deferred": [],
        }
        evaluation = _evaluate_roadmap(roadmap)
        duplicate = next(c for c in evaluation["checks"] if c["id"] == "roadmap.consistency.duplicate_scope")
        self.assertEqual(duplicate["status"], "warn")


class TitleUpgradeTests(unittest.TestCase):
    """
    A model's own raw label is not evidence that a title was upgraded.

    The merge step stores the model's unpolished label in `ai_title`, so accepting that field
    as proof of normalisation left titles like "Pay Premium" on screen while the clean one
    was never generated.
    """

    def _merged_point(self, title):
        """A pain point exactly as `_merge_ai_pain_points` leaves it: the model's label in
        both `title` and `ai_title`, the mined n-gram kept beside it."""
        return {
            "id": "pain_point_595c93b1fa",
            "title": title,
            "mined_title": title,
            "ai_title": title,
            "keywords": [title.lower(), "ads"],
            "sample_quotes": ["why does it keep asking me to pay premium and shows ads"],
            "affected_users_count": 615,
            "score_breakdown": {"frequency": 615, "avg_rating": 1.4, "negative_sentiment_pct": 88},
        }

    def test_the_model_raw_label_does_not_block_the_upgrade(self):
        upgraded = normalize_topic_titles([self._merged_point("Pay Premium")], "pain_point", allow_ai=False)[0]
        self.assertNotEqual(upgraded["title"], "Pay Premium")
        self.assertEqual(upgraded["title_source"], TITLE_SOURCE_HEURISTIC)

    def test_the_algorithmic_title_survives_as_provenance(self):
        upgraded = normalize_topic_titles([self._merged_point("Pay Premium")], "pain_point", allow_ai=False)[0]
        self.assertEqual(upgraded["mined_title"], "Pay Premium")
        self.assertEqual(upgraded["raw_title"], "Pay Premium")

    def test_a_second_pass_leaves_upgraded_titles_alone(self):
        once = normalize_topic_titles(
            [self._merged_point("Pay Premium"), self._merged_point("Skip Songs")],
            "pain_point",
            allow_ai=False,
        )
        titles = [topic["title"] for topic in once]
        twice = normalize_topic_titles(once, "pain_point", allow_ai=False)
        self.assertEqual([topic["title"] for topic in twice], titles)
        self.assertEqual([topic["title_source"] for topic in twice], [TITLE_SOURCE_HEURISTIC] * 2)

    def test_an_analysis_upgraded_before_the_marker_existed_is_not_rewritten(self):
        legacy = {
            "id": "pain_point_legacy",
            "title": "Excessive Paywall Prompts",
            "raw_title": "Pay Premium",
            "ai_title": "Excessive Paywall Prompts",
        }
        self.assertFalse(needs_title_upgrade(legacy, "pain_point"))
        out = normalize_topic_titles([legacy], "pain_point", allow_ai=False)[0]
        self.assertEqual(out["title"], "Excessive Paywall Prompts")
        self.assertEqual(out["raw_title"], "Pay Premium")

    def test_only_the_topics_that_still_need_it_are_rewritten(self):
        done = {
            "id": "pain_point_done",
            "title": "Shuffle Repeats Same Tracks",
            "raw_title": "Songs Playlist",
            "title_source": TITLE_SOURCE_AI,
        }
        out = normalize_topic_titles(
            [self._merged_point("Pay Premium"), done], "pain_point", allow_ai=False
        )
        self.assertEqual(out[1]["title"], "Shuffle Repeats Same Tracks")
        self.assertEqual(out[1]["raw_title"], "Songs Playlist")
        self.assertNotEqual(out[0]["title"], "Pay Premium")

    def test_a_cluster_keeps_its_raw_name_and_settles_after_one_pass(self):
        cluster = {"id": "cluster_x", "cluster_name": "Offline Downloads", "keywords": ["offline", "download"]}
        out = normalize_topic_titles([cluster], "cluster", allow_ai=False)[0]
        self.assertEqual(out["raw_cluster_name"], "Offline Downloads")
        self.assertFalse(needs_title_upgrade(out, "cluster", allow_ai=False))

    def test_a_read_persists_the_upgrade_so_the_next_one_is_free(self):
        """The read path upgrades a legacy analysis once, then stops working on it."""
        from routers import insights as insights_router

        legacy = {
            "workspace_id": "ws",
            "pain_points": [self._merged_point("Pay Premium")],
            "feature_clusters": [],
            "themes": [],
            "trends": [],
        }
        writes = []

        async def fake_save(workspace_id, data):
            writes.append(data)

        with patch.object(insights_router, "fb_save_workspace_insights", fake_save), \
             patch.object(insights_router.database, "_mongodb_available", False), \
             patch("services.title_normalizer.get_gemini_client", return_value=None), \
             patch("services.title_normalizer.get_mistral_client", return_value=None), \
             patch("services.title_normalizer.get_groq_client", return_value=None):
            first = asyncio.run(insights_router._sanitize_and_store("ws", dict(legacy)))
            self.assertEqual(len(writes), 1)
            # The second read sees what was stored, so there is nothing left to do.
            second = asyncio.run(insights_router._sanitize_and_store("ws", dict(writes[0])))

        self.assertEqual(len(writes), 1)
        self.assertNotEqual(first["pain_points"][0]["title"], "Pay Premium")
        self.assertEqual(
            [point["title"] for point in second["pain_points"]],
            [point["title"] for point in first["pain_points"]],
        )

    class _FakeChatClient:
        """A chat-completions client that replays prepared answers and counts its calls."""

        def __init__(self, contents):
            self.calls = 0
            self._contents = list(contents)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, model=None, messages=None, **kwargs):
            self.calls += 1
            content = self._contents[min(self.calls - 1, len(self._contents) - 1)]
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    def _topics(self, titles):
        return [self._merged_point(title) for title in titles]

    def test_a_prose_wrapped_array_is_read_as_a_batch(self):
        """A model that introduces its array with a sentence still gets every title read."""
        answer = (
            "Here are the rewritten titles:\n\n```json\n"
            '[{"id": 0, "title": "Ads Displayed on Premium Tier"},\n'
            ' {"id": 1, "title": "Excessive Ad Frequency"}]\n```'
        )
        client = self._FakeChatClient([answer])
        with patch("services.title_normalizer.get_gemini_client", return_value=None), \
             patch("services.title_normalizer.get_groq_client", return_value=None), \
             patch("services.title_normalizer.get_openrouter_client", return_value=None), \
             patch("services.title_normalizer.get_mistral_client", return_value=client):
            out = normalize_topic_titles(self._topics(["Pay Premium", "Skip Songs"]), "pain_point")

        self.assertEqual([t["title"] for t in out], ["Ads Displayed on Premium Tier", "Excessive Ad Frequency"])
        self.assertEqual([t["title_source"] for t in out], [TITLE_SOURCE_AI] * 2)

    def test_a_partial_answer_is_completed_by_the_next_provider(self):
        """One answered topic used to end the search, stranding the rest on placeholders."""
        first = self._FakeChatClient(['[{"id": 0, "title": "Ads Displayed on Premium Tier"}]'])
        second = self._FakeChatClient(['[{"id": 1, "title": "Excessive Ad Frequency"}]'])
        with patch("services.title_normalizer.get_gemini_client", return_value=None), \
             patch("services.title_normalizer.get_openrouter_client", return_value=None), \
             patch("services.title_normalizer.get_mistral_client", return_value=first), \
             patch("services.title_normalizer.get_groq_client", return_value=second):
            out = normalize_topic_titles(self._topics(["Pay Premium", "Skip Songs"]), "pain_point")

        self.assertEqual([t["title"] for t in out], ["Ads Displayed on Premium Tier", "Excessive Ad Frequency"])
        self.assertEqual([t["title_source"] for t in out], [TITLE_SOURCE_AI] * 2)
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 1)

    def test_the_search_stops_once_every_title_is_answered(self):
        # Groq is asked first, so the client that answers every title sits there and the
        # one behind it must never be reached.
        complete = self._FakeChatClient(
            ['[{"id": 0, "title": "Ads Displayed on Premium Tier"}, {"id": 1, "title": "Excessive Ad Frequency"}]']
        )
        unused = self._FakeChatClient(['[]'])
        with patch("services.title_normalizer.get_gemini_client", return_value=None), \
             patch("services.title_normalizer.get_openrouter_client", return_value=None), \
             patch("services.title_normalizer.get_groq_client", return_value=complete), \
             patch("services.title_normalizer.get_mistral_client", return_value=unused):
            out = normalize_topic_titles(self._topics(["Pay Premium", "Skip Songs"]), "pain_point")

        self.assertEqual([t["title_source"] for t in out], [TITLE_SOURCE_AI] * 2)
        self.assertEqual(complete.calls, 1)
        self.assertEqual(unused.calls, 0)

    def test_the_attempt_cap_bounds_how_long_a_page_read_waits(self):
        """A model that always answers for one topic must not hold the request open."""
        always_partial = self._FakeChatClient(['[{"id": 0, "title": "Ads Displayed on Premium Tier"}]'])
        with patch("services.title_normalizer.get_gemini_client", return_value=None), \
             patch("services.title_normalizer.get_openrouter_client", return_value=None), \
             patch("services.title_normalizer.get_mistral_client", return_value=always_partial), \
             patch("services.title_normalizer.get_groq_client", return_value=always_partial):
            out = normalize_topic_titles(self._topics(["Pay Premium", "Skip Songs", "Songs Playlist"]), "pain_point")

        self.assertEqual(always_partial.calls, MAX_TITLE_ATTEMPTS)
        self.assertEqual(out[0]["title_source"], TITLE_SOURCE_AI)
        self.assertEqual(
            [t["title_source"] for t in out[1:]], [TITLE_SOURCE_HEURISTIC] * 2
        )

    def test_a_model_title_is_final_while_a_heuristic_one_is_a_placeholder(self):
        heuristic = {
            "title": "Subscription Pricing & Paywall Friction",
            "raw_title": "Pay Premium",
            "title_source": TITLE_SOURCE_HEURISTIC,
        }
        model = {
            "title": "Ads Displayed on Premium Tier",
            "raw_title": "Pay Premium",
            "title_source": TITLE_SOURCE_AI,
        }
        self.assertFalse(needs_title_upgrade(heuristic, "pain_point", allow_ai=False))
        self.assertFalse(needs_title_upgrade(model, "pain_point", allow_ai=False))
        # An upgrade run may replace a placeholder once a provider is reachable — and only it.
        with patch("services.title_normalizer.get_gemini_client", return_value=object()):
            self.assertTrue(needs_title_upgrade(heuristic, "pain_point", allow_ai=True))
            self.assertFalse(needs_title_upgrade(model, "pain_point", allow_ai=True))
            # A page read must not: it would re-ask the model on every request.
            self.assertFalse(
                needs_title_upgrade(heuristic, "pain_point", allow_ai=True, revise_placeholders=False)
            )
            read = normalize_topic_titles(
                [dict(heuristic)], "pain_point", allow_ai=True, revise_placeholders=False
            )[0]
            self.assertEqual(read["title"], heuristic["title"])


if __name__ == "__main__":
    unittest.main()
