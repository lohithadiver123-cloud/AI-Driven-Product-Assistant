"""
Tests for batch-to-batch outcome tracking.

Validates:
1. Feedback is split into the imports it arrived in, oldest first, with records
   that carry no batch and import logs whose rows were all removed as duplicates
   both reported rather than silently dropped.
2. The comparison normalises per 100 records, so a larger later collection is
   not read as a rise in everything.
3. Every threshold is honoured: a movement is only claimed above the mention floor
   and the noise band, and a topic short of either is reported as such.
4. Verdicts are deterministic, so a number from this service can be quoted.
5. The Markdown export and both API routes (including their auth requirement).

No network and no database: the pure comparison runs on fixtures, and persistence
is patched with AsyncMock.
"""

import asyncio
import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services import outcome_service


def _record(
    text,
    batch="log_a",
    when="2026-01-05T10:00:00+00:00",
    rating=None,
    sentiment=None,
    category=None,
    title=None,
):
    """One feedback record shaped like the stored document."""
    return {
        "_id": f"{batch}-{abs(hash((text, when, title))) % 10**8}",
        "workspace_id": "test_workspace_outcome",
        "title": title,
        "content": text,
        "rating": rating,
        "sentiment": sentiment,
        "category": category,
        "imported_via": batch,
        "imported_at": when,
        "created_at": when,
    }


CRASH_TEXTS = [
    "the app crashes every time i open the playlist screen",
    "crashes whenever i open the playlist screen on my phone",
    "app crashes on the playlist screen after the update",
]
DOWNLOAD_TEXTS = [
    "please add offline downloads so i can listen without data",
    "i want offline downloads for my saved albums",
    "add offline download support for music please",
]
# Deliberately free of the words the other fixtures use, so a topic lookup cannot
# land on the wrong row.
FILLER_TEXTS = [
    "great app i love the music library and the sound quality",
    "the sound quality is excellent and the library is huge",
]


def _crash_batch(count, batch, when):
    texts = [CRASH_TEXTS[index % len(CRASH_TEXTS)] for index in range(count)]
    return [_record(text, batch=batch, when=when, rating=1, category="bug_report") for text in texts]


def _download_batch(count, batch, when):
    texts = [DOWNLOAD_TEXTS[index % len(DOWNLOAD_TEXTS)] for index in range(count)]
    return [
        _record(text, batch=batch, when=when, rating=4, category="feature_request") for text in texts
    ]


def _filler_batch(count, batch, when):
    texts = [FILLER_TEXTS[index % len(FILLER_TEXTS)] for index in range(count)]
    return [_record(text, batch=batch, when=when, rating=5, sentiment="positive") for text in texts]


def _titled_batch(count, texts, category, rating, batch):
    """Records shaped like an import: every row carries a title column too."""
    return [
        _record(
            texts[index % len(texts)],
            batch=batch,
            rating=rating,
            category=category,
            title=f"review {index}",
        )
        for index in range(count)
    ]


def _batch(batch_id, when, items):
    return {
        "batch_id": batch_id,
        "filename": f"{batch_id}.csv",
        "imported_at": when,
        "stored": len(items),
        "reported": len(items),
        "items": items,
    }


def _row_for(rows, needles):
    """The comparison row whose topic mentions any of these words."""
    for row in rows:
        haystack = " ".join(
            [str(row.get("title", ""))]
            + [str(word) for word in row.get("keywords") or []]
            + [str(word) for word in row.get("match_phrases") or []]
        ).lower()
        if any(needle in haystack for needle in needles):
            return row
    return None


class BatchGroupingTests(unittest.TestCase):
    """Feedback is split into the imports it arrived in."""

    def test_records_are_grouped_by_import_and_ordered_oldest_first(self):
        records = (
            _crash_batch(3, "log_b", "2026-02-10T09:00:00+00:00")
            + _crash_batch(3, "log_a", "2026-01-05T09:00:00+00:00")
        )
        batches, unattributed, orphans = outcome_service.group_into_batches(records)
        self.assertEqual([batch["batch_id"] for batch in batches], ["log_a", "log_b"])
        self.assertEqual(batches[0]["stored"], 3)
        self.assertEqual(unattributed, 0)
        self.assertEqual(orphans, [])

    def test_batches_are_labelled_by_position_and_day(self):
        records = _crash_batch(2, "log_a", "2026-01-05T09:00:00+00:00")
        batches, _, _ = outcome_service.group_into_batches(records)
        outcome_service._label_batches(batches)
        self.assertEqual(batches[0]["label"], "Import 1 · 2026-01-05")
        self.assertEqual(batches[0]["index"], 1)

    def test_records_without_an_import_are_counted_not_assumed(self):
        records = _crash_batch(3, "log_a", "2026-01-05T09:00:00+00:00")
        records.append({"content": "seeded record with no batch", "workspace_id": "w"})
        batches, unattributed, _ = outcome_service.group_into_batches(records)
        self.assertEqual(unattributed, 1)
        self.assertEqual(len(batches), 1)

    def test_an_import_whose_rows_were_all_deleted_is_reported_as_an_orphan(self):
        records = _crash_batch(2, "log_a", "2026-01-05T09:00:00+00:00")
        logs = {
            "log_a": {"filename": "january.csv", "imported_at": "2026-01-05T09:00:00+00:00", "successful": 2},
            "log_b": {"filename": "february.csv", "imported_at": "2026-02-10T09:00:00+00:00", "successful": 300},
        }
        batches, _, orphans = outcome_service.group_into_batches(records, logs)
        self.assertEqual([batch["batch_id"] for batch in batches], ["log_a"])
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["filename"], "february.csv")
        # The log's own record count is kept so the loss is visible, not hidden.
        self.assertEqual(orphans[0]["reported"], 300)


class ComparisonTests(unittest.TestCase):
    """What changed between two imports, and how confidently it is claimed."""

    def _compare(self, before_items, after_items, max_themes=outcome_service.DEFAULT_MAX_THEMES):
        return outcome_service.compare_batches(
            before_items,
            after_items,
            _batch("log_a", "2026-01-05T09:00:00+00:00", before_items),
            _batch("log_b", "2026-02-10T09:00:00+00:00", after_items),
            max_themes=max_themes,
        )

    def test_a_falling_complaint_topic_is_reported_as_falling(self):
        before = _crash_batch(40, "log_a", "2026-01-05T09:00:00+00:00") + _download_batch(
            10, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _crash_batch(12, "log_b", "2026-02-10T09:00:00+00:00") + _download_batch(
            38, "log_b", "2026-02-10T09:00:00+00:00"
        )
        comparison = self._compare(before, after)

        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row, "expected a topic covering the crash reports")
        self.assertEqual(crash_row["direction"], "falling")
        self.assertEqual(crash_row["tone"], "success")
        self.assertIn("Fell", crash_row["reading"])

        download_row = _row_for(comparison["themes"], ["offline", "download"])
        self.assertIsNotNone(download_row, "expected a topic covering offline downloads")
        self.assertEqual(download_row["direction"], "rising")
        self.assertEqual(download_row["tone"], "accent")

    def test_counts_are_normalised_so_a_bigger_import_is_not_a_rise(self):
        # Raw complaint mentions go 5 → 20, but the collection grows 50 → 500, so the
        # rate actually falls. Reporting the raw count would invert the finding.
        before = _crash_batch(5, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            45, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _crash_batch(20, "log_b", "2026-02-10T09:00:00+00:00") + _filler_batch(
            480, "log_b", "2026-02-10T09:00:00+00:00"
        )
        comparison = self._compare(before, after, max_themes=12)

        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertGreater(crash_row["after_count"], crash_row["before_count"])
        self.assertLess(crash_row["after_per_100"], crash_row["before_per_100"])
        self.assertEqual(crash_row["direction"], "falling")

    def test_a_change_inside_the_noise_band_is_reported_as_steady(self):
        # 100 → 102 per 100 is inside both the floor and the relative band.
        before = _crash_batch(10, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            90, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _crash_batch(10, "log_b", "2026-02-10T09:00:00+00:00") + _filler_batch(
            98, "log_b", "2026-02-10T09:00:00+00:00"
        )
        comparison = self._compare(before, after)
        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertEqual(crash_row["direction"], "steady")
        self.assertEqual(crash_row["tone"], "neutral")

    def test_a_topic_below_the_mention_floor_is_not_called_a_trend(self):
        before = _crash_batch(4, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(2, "log_b", "2026-02-10T09:00:00+00:00")
        comparison = self._compare(before, after)
        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertEqual(crash_row["direction"], "insufficient_evidence")
        self.assertIn("Too few mentions", crash_row["reading"])

    def test_a_topic_absent_from_the_earlier_import_is_reported_as_new(self):
        before = _filler_batch(30, "log_a", "2026-01-05T09:00:00+00:00")
        after = _filler_batch(10, "log_b", "2026-02-10T09:00:00+00:00") + _crash_batch(
            20, "log_b", "2026-02-10T09:00:00+00:00"
        )
        comparison = self._compare(before, after, max_themes=12)
        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertEqual(crash_row["direction"], "appeared")
        self.assertEqual(crash_row["before_count"], 0)

    def test_snapshot_measures_each_import_on_its_own_terms(self):
        before = _crash_batch(8, "log_a", "2026-01-05T09:00:00+00:00")
        after = _filler_batch(8, "log_b", "2026-02-10T09:00:00+00:00")
        comparison = self._compare(before, after)

        self.assertEqual(comparison["before"]["total"], 8)
        self.assertEqual(comparison["after"]["total"], 8)
        self.assertEqual(comparison["before"]["avg_rating"], 1.0)
        self.assertEqual(comparison["after"]["avg_rating"], 5.0)
        self.assertEqual(comparison["before"]["problem_mentions"], 8)
        self.assertEqual(comparison["after"]["problem_mentions"], 0)
        self.assertGreater(comparison["after"]["health_score"], comparison["before"]["health_score"])
        self.assertEqual(comparison["deltas"]["total"], 0)

    def test_the_headline_states_the_measured_change(self):
        # Complaint rates of 400 then 100 per 100 records; ratings 3.4 then 4.7.
        before = _crash_batch(40, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            60, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _crash_batch(10, "log_b", "2026-02-10T09:00:00+00:00") + _filler_batch(
            90, "log_b", "2026-02-10T09:00:00+00:00"
        )
        comparison = self._compare(before, after)
        self.assertIn("Complaint volume fell", comparison["headline"])
        self.assertIn("Average rating is up", comparison["headline"])
        self.assertEqual(comparison["gap_days"], 36)
        self.assertGreater(comparison["after"]["health_score"], comparison["before"]["health_score"])

    def test_two_collections_that_are_entirely_complaints_have_the_same_rate(self):
        # Both imports are 100% bug reports, so the complaint *rate* is identical and
        # the headline must not claim an improvement just because the later import is
        # smaller. This is the case that raw counts get wrong.
        before = _crash_batch(40, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(10, "log_b", "2026-02-10T09:00:00+00:00")
        comparison = self._compare(before, after)
        # 100% of both collections is 100 per 100 — the base, not a coincidence.
        self.assertEqual(comparison["before"]["problem_per_100"], 100.0)
        self.assertEqual(comparison["after"]["problem_per_100"], 100.0)
        self.assertEqual(comparison["before"]["problem_per_100"], outcome_service.RATE_BASE)
        self.assertIn("held roughly steady", comparison["headline"])
        self.assertIn("fewer records", comparison["headline"])

    def test_a_topic_is_reported_once_even_when_the_extractor_labels_it_twice(self):
        before = _crash_batch(20, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            80, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _crash_batch(6, "log_b", "2026-02-10T09:00:00+00:00") + _filler_batch(
            94, "log_b", "2026-02-10T09:00:00+00:00"
        )
        rows = self._compare(before, after, max_themes=12)["themes"]
        titles = [row["title"].lower() for row in rows]
        self.assertEqual(len(titles), len(set(titles)))
        self.assertEqual(len({row["topic_id"] for row in rows}), len(rows))
        # Every topic carries a stable id derived from its own label, not its rank.
        self.assertTrue(all(row["topic_id"].startswith("outcome_topic_") for row in rows))

    def test_confidence_reflects_the_smallest_collection_and_the_gap(self):
        # Two large imports a month apart is the case a reader can lean on.
        before = _filler_batch(600, "log_a", "2026-01-05T09:00:00+00:00")
        after = _filler_batch(600, "log_b", "2026-02-10T09:00:00+00:00")
        self.assertEqual(self._compare(before, after)["confidence"], "high")

        # The same two imports a day apart are not.
        before_same_day = _filler_batch(20, "log_a", "2026-01-05T09:00:00+00:00")
        after_same_day = _filler_batch(20, "log_b", "2026-01-06T09:00:00+00:00")
        self.assertEqual(self._compare(before_same_day, after_same_day)["confidence"], "low")

    def test_unlike_collections_are_flagged_as_indicative_rather_than_clean(self):
        # A 5x size gap and a different dominant source are the two ways a pair of
        # imports can be too different for a clean before-and-after.
        before = _filler_batch(500, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(40, "log_b", "2026-02-10T09:00:00+00:00")
        for item in before:
            item["source"] = "app_review"
        for item in after:
            item["source"] = "Apple App Store"

        comparison = self._compare(before, after)
        notes = " ".join(comparison["notes"])
        self.assertIn("differ greatly in size", notes)
        self.assertIn("different sources", notes)
        self.assertEqual(comparison["before"]["dominant_source"], "app_review")
        self.assertEqual(comparison["after"]["dominant_source"], "Apple App Store")

    def test_two_like_imports_from_one_source_carry_no_caveat(self):
        before = _crash_batch(30, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(20, "log_b", "2026-02-10T09:00:00+00:00")
        comparison = self._compare(before, after)
        self.assertEqual(comparison["notes"], [])

    def test_thresholds_and_the_rate_base_are_published_with_the_result(self):
        before = _crash_batch(10, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(10, "log_b", "2026-02-10T09:00:00+00:00")
        method = self._compare(before, after)["method"]
        self.assertEqual(method["min_mentions"], outcome_service.MIN_MENTIONS)
        self.assertEqual(method["min_per_100_delta"], outcome_service.MIN_PER_100_DELTA)
        self.assertEqual(method["rate_base"], outcome_service.RATE_BASE)
        self.assertEqual(method["normalisation"], "mentions per 100 records in each import")
        self.assertFalse(method["axis_sampled"])

    def test_rates_are_expressed_per_hundred_not_per_thousand(self):
        # 5 complaints in 50 records is 10 per 100 (and would be 100 per 1,000).
        before = _crash_batch(5, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            45, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _filler_batch(50, "log_b", "2026-02-10T09:00:00+00:00")
        comparison = self._compare(before, after)
        self.assertEqual(comparison["before"]["problem_per_100"], 10.0)
        self.assertEqual(comparison["after"]["problem_per_100"], 0.0)
        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertEqual(crash_row["before_per_100"], 10.0)

    def test_every_record_lands_in_exactly_one_topic_and_a_common_word_cannot_inflate_one(self):
        # Every record carries "review" in its title, and the phrase list for both
        # topics contains it. Matching a topic by OR-ing its phrases counted all 100
        # records in every topic; assignment by the most specific phrase cannot.
        before = _titled_batch(40, CRASH_TEXTS, "bug_report", 1, "log_a") + _titled_batch(
            60, FILLER_TEXTS, "general_feedback", 5, "log_a"
        )
        after = _titled_batch(10, CRASH_TEXTS, "bug_report", 2, "log_b") + _titled_batch(
            90, FILLER_TEXTS, "general_feedback", 5, "log_b"
        )
        comparison = self._compare(before, after)

        self.assertEqual(
            sum(row["before_count"] for row in comparison["themes"]), comparison["before"]["total"]
        )
        self.assertEqual(
            sum(row["after_count"] for row in comparison["themes"]), comparison["after"]["total"]
        )

        crash_row = _row_for(comparison["themes"], ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertEqual(crash_row["before_count"], 40)
        self.assertEqual(crash_row["after_count"], 10)
        self.assertEqual(crash_row["direction"], "falling")

    def test_a_phrase_common_to_the_whole_corpus_is_not_listed_as_a_topic_keyword(self):
        # "review" sits in every title, so it describes the corpus rather than any
        # topic and must not be shown as one of a topic's keywords.
        before = _titled_batch(30, CRASH_TEXTS, "bug_report", 1, "log_a")
        after = _titled_batch(30, CRASH_TEXTS, "bug_report", 1, "log_b")
        rows = self._compare(before, after)["themes"]
        crash_row = _row_for(rows, ["crash", "playlist"])
        self.assertIsNotNone(crash_row)
        self.assertNotIn("review", crash_row["keywords"])

    def test_movement_is_ordered_ahead_of_volume(self):
        before = _crash_batch(30, "log_a", "2026-01-05T09:00:00+00:00") + _filler_batch(
            200, "log_a", "2026-01-05T09:00:00+00:00"
        )
        after = _filler_batch(200, "log_b", "2026-02-10T09:00:00+00:00") + _crash_batch(
            5, "log_b", "2026-02-10T09:00:00+00:00"
        )
        rows = self._compare(before, after, max_themes=12)["themes"]
        moving = [index for index, row in enumerate(rows) if row["direction"] in ("falling", "rising", "appeared", "disappeared")]
        self.assertTrue(moving)
        self.assertLess(max(moving), len(rows))

    def test_two_runs_of_the_same_comparison_are_identical(self):
        before = _crash_batch(30, "log_a", "2026-01-05T09:00:00+00:00")
        after = _crash_batch(8, "log_b", "2026-02-10T09:00:00+00:00")
        first = self._compare(deepcopy(before), deepcopy(after))
        second = self._compare(deepcopy(before), deepcopy(after))
        first.pop("generated_at")
        second.pop("generated_at")
        self.assertEqual(first, second)

    def test_a_very_large_corpus_is_mined_from_an_evenly_spaced_sample(self):
        items = _filler_batch(10, "log_a", "2026-01-05T09:00:00+00:00")
        with patch.object(outcome_service, "MAX_AXIS_RECORDS", 4):
            sampled, was_sampled = outcome_service._axis_sample(items)
        self.assertTrue(was_sampled)
        self.assertEqual(sampled, items[::3])
        self.assertLess(len(sampled), len(items))

        unsampled, flag = outcome_service._axis_sample(items)
        self.assertFalse(flag)
        self.assertEqual(len(unsampled), len(items))


class BuildComparisonTests(unittest.TestCase):
    """Selecting which two imports to compare, and saying so when there is one."""

    def _run(self, batches, unattributed=0, orphans=None, **kwargs):
        grouped = AsyncMock(return_value=(batches, unattributed, orphans or []))
        with patch.object(outcome_service, "_grouped", grouped):
            return asyncio.run(outcome_service.build_comparison("test_workspace_outcome", **kwargs))

    def _three_batches(self):
        first = _batch("log_a", "2026-01-05T09:00:00+00:00", _crash_batch(20, "log_a", "2026-01-05T09:00:00+00:00"))
        second = _batch("log_b", "2026-02-10T09:00:00+00:00", _crash_batch(10, "log_b", "2026-02-10T09:00:00+00:00"))
        third = _batch("log_c", "2026-03-20T09:00:00+00:00", _crash_batch(4, "log_c", "2026-03-20T09:00:00+00:00"))
        for index, batch in enumerate([first, second, third], start=1):
            batch["index"] = index
            batch["label"] = f"Import {index} · {batch['imported_at'][:10]}"
        return [first, second, third]

    def test_the_two_most_recent_imports_are_compared_by_default(self):
        comparison = self._run(self._three_batches())
        self.assertEqual(comparison["status"], "ready")
        self.assertEqual(comparison["compared"]["before"]["batch_id"], "log_b")
        self.assertEqual(comparison["compared"]["after"]["batch_id"], "log_c")
        self.assertEqual(len(comparison["batches"]), 3)

    def test_explicit_imports_are_honoured_in_date_order(self):
        comparison = self._run(
            self._three_batches(), before_batch_id="log_a", after_batch_id="log_c"
        )
        self.assertEqual(comparison["compared"]["before"]["batch_id"], "log_a")
        self.assertEqual(comparison["compared"]["after"]["batch_id"], "log_c")

    def test_an_unknown_batch_is_rejected_rather_than_guessed(self):
        with self.assertRaises(ValueError):
            self._run(self._three_batches(), before_batch_id="nope", after_batch_id="log_c")

    def test_comparing_a_batch_with_itself_is_rejected(self):
        with self.assertRaises(ValueError):
            self._run(self._three_batches(), before_batch_id="log_b", after_batch_id="log_b")

    def test_one_import_is_not_a_comparison_and_says_what_is_missing(self):
        single = _batch("log_a", "2026-01-05T09:00:00+00:00", _crash_batch(10, "log_a", "2026-01-05T09:00:00+00:00"))
        single["index"] = 1
        single["label"] = "Import 1 · 2026-01-05"

        result = self._run([single], unattributed=7)
        self.assertEqual(result["status"], "needs_two_imports")
        self.assertEqual(result["themes"], [])
        self.assertEqual(len(result["batches"]), 1)
        self.assertIn("Import", result["batches"][0]["label"])
        self.assertTrue(any("not tied to an import" in note for note in result["notes"]))
        self.assertTrue(any("again later" in note for note in result["notes"]))

    def test_an_import_with_no_records_left_is_explained(self):
        batches = self._three_batches()[:2]
        orphans = [{"batch_id": "log_c", "filename": "march.csv", "imported_at": "2026-03-20T09:00:00+00:00", "reported": 250}]
        comparison = self._run(batches, orphans=orphans)
        self.assertTrue(any("march.csv" in note and "duplicates" in note for note in comparison["notes"]))


class MarkdownExportTests(unittest.TestCase):
    """The comparison is quotable without re-typing it."""

    def _comparison(self):
        before = _batch("log_a", "2026-01-05T09:00:00+00:00", _crash_batch(30, "log_a", "2026-01-05T09:00:00+00:00"))
        after = _batch("log_b", "2026-02-10T09:00:00+00:00", _crash_batch(5, "log_b", "2026-02-10T09:00:00+00:00"))
        for index, batch in enumerate([before, after], start=1):
            batch["index"] = index
            batch["label"] = f"Import {index} · {batch['imported_at'][:10]}"
        return outcome_service.compare_batches(before["items"], after["items"], before, after)

    def test_the_export_carries_the_numbers_the_thresholds_and_the_caveats(self):
        comparison = self._compare_with_note()
        markdown = outcome_service.build_markdown(comparison)

        self.assertIn("# Outcome tracking", markdown)
        self.assertIn(comparison["headline"], markdown)
        self.assertIn(f"| Complaint mentions / {outcome_service.RATE_BASE} |", markdown)
        self.assertIn("## What moved, topic by topic", markdown)
        self.assertIn("A movement is claimed only above", markdown)
        self.assertIn("## Caveats", markdown)
        self.assertIn("carry no import batch", markdown)

    def _compare_with_note(self):
        comparison = self._comparison()
        comparison["notes"] = ["3 records carry no import batch."]
        return comparison

    def test_the_export_handles_a_workspace_with_nothing_to_compare(self):
        markdown = outcome_service.build_markdown(
            {
                "status": "needs_two_imports",
                "notes": ["Outcome tracking compares two imports of the same workspace."],
            }
        )
        self.assertIn("Not enough imports to compare yet.", markdown)
        self.assertIn("two imports of the same workspace", markdown)


class OutcomeRouteTests(unittest.TestCase):
    """The endpoints exist, require a session, and serve the comparison."""

    def test_outcome_routes_are_registered_and_require_authorization(self):
        from fastapi.testclient import TestClient
        from main import app

        paths = app.openapi()["paths"]
        for expected in (
            "/api/outcome/{workspace_id}/batches",
            "/api/outcome/{workspace_id}/compare",
            "/api/outcome/{workspace_id}/export",
        ):
            self.assertIn(expected, paths)

        client = TestClient(app, raise_server_exceptions=False)
        self.assertEqual(client.get("/api/outcome/test_workspace_outcome/compare").status_code, 401)
        self.assertEqual(client.get("/api/outcome/test_workspace_outcome/batches").status_code, 401)
        self.assertEqual(client.get("/api/outcome/test_workspace_outcome/export").status_code, 401)

    def test_the_compare_endpoint_serves_the_service_result(self):
        from fastapi.testclient import TestClient
        from main import app

        payload = {
            "status": "ready",
            "headline": "Complaint volume fell 60%.",
            "themes": [],
            "method": {"min_mentions": outcome_service.MIN_MENTIONS},
        }
        with patch(
            "routers.outcome._get_user_from_token", AsyncMock(return_value={"id": "u1"})
        ), patch(
            "routers.outcome._verify_workspace_access", AsyncMock(return_value={"workspace_id": "w"})
        ), patch(
            "services.outcome_service.build_comparison", AsyncMock(return_value=payload)
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/outcome/test_workspace_outcome/compare",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["headline"], "Complaint volume fell 60%.")

    def test_the_export_endpoint_returns_markdown(self):
        from fastapi.testclient import TestClient
        from main import app

        markdown = "# Outcome tracking\n\nMeasured change.\n"
        with patch(
            "routers.outcome._get_user_from_token", AsyncMock(return_value={"id": "u1"})
        ), patch(
            "routers.outcome._verify_workspace_access", AsyncMock(return_value={"workspace_id": "w"})
        ), patch(
            "services.outcome_service.build_comparison", AsyncMock(return_value={"status": "ready"})
        ), patch(
            "services.outcome_service.build_markdown", return_value=markdown
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/outcome/test_workspace_outcome/export",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Measured change.", response.text)

    def test_an_unknown_batch_returns_400_rather_than_a_guess(self):
        from fastapi.testclient import TestClient
        from main import app

        with patch(
            "routers.outcome._get_user_from_token", AsyncMock(return_value={"id": "u1"})
        ), patch(
            "routers.outcome._verify_workspace_access", AsyncMock(return_value={"workspace_id": "w"})
        ), patch(
            "services.outcome_service.build_comparison",
            AsyncMock(side_effect=ValueError("Unknown import batch for this workspace")),
        ):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/api/outcome/test_workspace_outcome/compare?before=nope&after=log_b",
                headers={"Authorization": "Bearer token"},
            )

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
