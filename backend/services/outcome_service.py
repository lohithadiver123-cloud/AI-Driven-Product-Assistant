"""
Batch-to-batch outcome tracking.

This answers the question a plan cannot answer about itself: between the two times
this workspace collected customer feedback, did the signal actually move?

Method, and why it is built this way:

* **Two imports of the same workspace are the unit of comparison.** Every imported
  record already carries `imported_via` — the import log it arrived in — so the time
  axis exists in the data without asking anyone to remember a date or edit a CSV.
* **The topic axis is mined once, on the union of both collections**, and each
  record is then assigned to the topic whose mined phrase matches its text most
  specifically. Mining each side independently would produce two vocabularies that
  cannot be compared; measuring a topic by OR-matching its phrase list would count a
  record in every topic whose list contains a common word. Assignment by the most
  specific phrase counts every record in exactly one topic, which is what makes the
  two columns a like-for-like measurement.
* **Counts are normalised per 100 records.** The later collection is rarely the
  same size as the earlier one, and raw counts would report a larger import as a
  rise in every theme at once.
* **Every movement states its own threshold.** A change is only claimed when it
  clears both a floor and a relative band, and a topic seen too few times on either
  side is reported as insufficient evidence rather than as a trend.

Nothing here invents a number. Where a comparison cannot be made, the response says
so and explains what is missing.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

import database
import fallback_db
from database import db
from services.text_mining import rating_stats, record_text, stable_topic_id, term_mention_share
from services.theme_extraction import (
    THEME_MAX_SHARE,
    UNCLASSIFIED_THEME,
    assign_record_theme,
    extract_themes_from_feedback,
    _dominant_category,
    _resolve_category,
    _resolve_sentiment,
)
from services.trend_analysis import calculate_health_score

# --- decision thresholds --------------------------------------------------
# A theme needs at least this many mentions on *both* sides before a movement is
# claimed. Below it the honest answer is "not enough evidence", which is a real
# answer rather than a failure.
MIN_MENTIONS = 5
# Rates are stated per this many records. A per-100 rate reads closer to the raw
# counts a person sees on the feedback list than a per-1,000 rate does, while still
# being comparable between collections of different sizes.
RATE_BASE = 100
# Movement is measured in mentions per RATE_BASE records, so a shift smaller than
# this is inside the noise of a normal collection. 0.05 per 100 is 0.5 per 1,000.
MIN_PER_100_DELTA = 0.05
# ...and it must also clear this share of the earlier value, so a tiny base cannot
# generate a large-looking percentage.
RELATIVE_BAND = 0.10
# The topic axis is mined from at most this many records (deterministically strided,
# never randomly sampled) so a very large corpus cannot stall the endpoint. Full
# corpora are still measured in full — only the vocabulary is capped.
MAX_AXIS_RECORDS = 20000
DEFAULT_MAX_THEMES = 8

PROBLEM_CATEGORIES = ("bug_report", "performance_issue")
# Terms kept per topic when its mined phrases are matched against each import. A
# topic is described by its own phrases, and a handful is what the extractor mines;
# the cap only bounds the regex work on a runaway topic.
MAX_TOPIC_TERMS = 24

# Tones for the UI. A fall in problem mentions is good news; a fall in feature
# demand is not bad news either — it is simply not the same kind of news, so the
# two never share a colour.
FALLING_TONES = {"bug_report": "success", "performance_issue": "success", "feature_request": "neutral"}
RISING_TONES = {"bug_report": "danger", "performance_issue": "danger", "feature_request": "accent"}

DIRECTIONS = ("rising", "falling", "steady", "appeared", "disappeared", "insufficient_evidence")


# --- small helpers --------------------------------------------------------


def _parse_dt(value: Any) -> Optional[datetime]:
    """Best-effort datetime from what Mongo or the JSON fallback stores."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and len(value) >= 10:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _as_iso(value: Any) -> str:
    parsed = _parse_dt(value)
    return parsed.isoformat() if parsed else ""


def _per_100(count: int, total: int) -> float:
    """Mentions per RATE_BASE records — the comparable form across two collections."""
    if not total:
        return 0.0
    return round(count / total * RATE_BASE, 2)


def _change_pct(before_value: float, after_value: float) -> Optional[float]:
    if not before_value:
        return None
    return round((after_value - before_value) / before_value * 100.0, 1)


def _resolved(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Records with a sentiment and category filled in.

    Stored records only carry these once they have been categorised, so the rule
    engine's reading is used as the fallback. This is the same resolution the
    insights pipeline reports, which is what keeps a batch snapshot comparable with
    the dashboard numbers.
    """
    resolved = []
    for item in items:
        shallow = dict(item)
        if not shallow.get("sentiment"):
            shallow["sentiment"] = _resolve_sentiment(item)
        if not shallow.get("category"):
            shallow["category"] = _resolve_category(item)
        resolved.append(shallow)
    return resolved


def _snapshot(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Everything measurable about one collection of feedback, on its own terms."""
    resolved = _resolved(items)
    total = len(resolved)
    positives = sum(1 for item in resolved if item.get("sentiment") == "positive")
    negatives = sum(1 for item in resolved if item.get("sentiment") == "negative")
    neutrals = total - positives - negatives

    problems = sum(1 for item in resolved if item.get("category") in PROBLEM_CATEGORIES)
    features = sum(1 for item in resolved if item.get("category") == "feature_request")

    ratings = rating_stats(resolved)
    source_counts = Counter(str(item.get("source") or "unknown") for item in resolved)

    return {
        "total": total,
        "sources": dict(source_counts.most_common(3)),
        "dominant_source": source_counts.most_common(1)[0][0] if source_counts else "",
        "sentiment": {"positive": positives, "neutral": neutrals, "negative": negatives},
        "sentiment_score": round((positives - negatives) / total, 2) if total else 0.0,
        "negative_per_100": _per_100(negatives, total),
        "problem_mentions": problems,
        "problem_per_100": _per_100(problems, total),
        "feature_mentions": features,
        "feature_per_100": _per_100(features, total),
        "avg_rating": ratings["avg_rating"],
        "rated_count": ratings["rated_count"],
        "low_rating_count": ratings["low_rating_count"],
        "health_score": calculate_health_score(resolved) if resolved else None,
    }


def merge_topics(themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    One entry per topic, described by every phrase mined for it.

    The extractor can settle on the same label twice — two groups that both fall
    back to "Unclassified mentions", for instance — and reporting those as two rows
    with identical numbers reads as two findings when there is one.
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for theme in themes:
        title = str(theme.get("title") or "Untitled topic").strip() or "Untitled topic"
        entry = merged.setdefault(
            title.lower(),
            {"title": title, "category": theme.get("category") or "general_feedback", "terms": []},
        )
        for term in list(theme.get("match_phrases") or []) + list(theme.get("keywords") or []):
            text = str(term).strip()
            if text and text not in entry["terms"] and len(entry["terms"]) < MAX_TOPIC_TERMS:
                entry["terms"].append(text)
    return list(merged.values())


def display_terms(terms: List[str], corpus: List[Dict[str, Any]]) -> List[str]:
    """
    The phrases worth showing for a topic.

    A phrase that appears in most of the corpus describes the corpus, not the topic —
    a word like "review" that sits in every title would be listed against every topic
    and tell a reader nothing. Those are dropped from the displayed keywords, which
    does not change any count: counts come from assignment, not from phrase matching.
    """
    if not terms or not corpus:
        return terms
    kept = [term for term in terms if term_mention_share(term, corpus) <= THEME_MAX_SHARE]
    return kept or terms


def assign_groups(
    items: List[Dict[str, Any]], themes: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Split a collection into the topics its records are about.

    Every record lands in exactly one bucket — the topic whose mined phrase matches it
    most specifically, or the honest "unclassified" bucket when nothing matches — so the
    bucket sizes always add up to the collection, and a topic's count cannot be inflated
    by a word its neighbours also contain.
    """
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        groups[assign_record_theme(record_text(item), themes)].append(item)
    return groups


def _axis_sample(items: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    """
    The corpus the topic vocabulary is mined from.

    Strided rather than randomly sampled so the same workspace always yields the
    same vocabulary, and so the sample is spread across both collections instead of
    favouring whichever one was appended last.
    """
    if len(items) <= MAX_AXIS_RECORDS:
        return items, False
    stride = ceil(len(items) / MAX_AXIS_RECORDS)
    return items[::stride], True


# --- batch assembly -------------------------------------------------------


def group_into_batches(
    records: List[Dict[str, Any]],
    logs: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    """
    Split a workspace's feedback into the imports it arrived in.

    Returns the batches oldest-first (each with its own records), the number of
    records that carry no batch at all, and the import logs that have no surviving
    records left — rows removed as duplicates leave a log behind, and pretending
    those imports never happened would misstate the history.
    """
    logs = logs or {}
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unattributed = 0

    for record in records:
        batch_key = str(record.get("imported_via") or "").strip()
        if not batch_key:
            unattributed += 1
            continue
        grouped[batch_key].append(record)

    batches: List[Dict[str, Any]] = []
    for batch_id, items in grouped.items():
        log = logs.get(batch_id) or {}
        times = [
            parsed
            for parsed in (_parse_dt(item.get("imported_at")) or _parse_dt(item.get("created_at")) for item in items)
            if parsed
        ]
        imported_at = min(times) if times else _parse_dt(log.get("imported_at"))
        batches.append(
            {
                "batch_id": batch_id,
                "filename": log.get("filename") or "",
                "imported_at": imported_at.isoformat() if imported_at else "",
                "stored": len(items),
                "reported": int(log.get("successful") or log.get("record_count") or 0),
                "items": items,
            }
        )

    batches.sort(key=lambda batch: (batch["imported_at"] or "", batch["batch_id"]))

    orphans = []
    for batch_id, log in logs.items():
        if batch_id in grouped:
            continue
        orphans.append(
            {
                "batch_id": batch_id,
                "filename": log.get("filename") or "",
                "imported_at": _as_iso(log.get("imported_at")),
                "reported": int(log.get("successful") or log.get("record_count") or 0),
            }
        )
    orphans.sort(key=lambda orphan: orphan["imported_at"] or "")

    return batches, unattributed, orphans


def _label_batches(batches: List[Dict[str, Any]]) -> None:
    """Give every batch a stable, human label: position plus the day it landed."""
    for index, batch in enumerate(batches, start=1):
        day = (batch.get("imported_at") or "")[:10] or "undated"
        batch["index"] = index
        batch["label"] = f"Import {index} · {day}"


def _batch_meta(batch: Dict[str, Any]) -> Dict[str, Any]:
    """One batch as the API reports it — a label is derived when it was never set."""
    imported_at = batch.get("imported_at") or ""
    day = imported_at[:10] or "undated"
    index = batch.get("index")
    return {
        "batch_id": batch.get("batch_id") or "",
        "label": batch.get("label") or (f"Import {index} · {day}" if index else f"Import · {day}"),
        "index": index or 0,
        "filename": batch.get("filename") or "",
        "imported_at": imported_at,
        "stored": batch.get("stored") or len(batch.get("items") or []),
        "reported": batch.get("reported") or 0,
    }


async def _load_feedback(workspace_id: str) -> List[Dict[str, Any]]:
    if database._mongodb_available:
        cursor = db.feedback.find({"workspace_id": workspace_id})
        records = await cursor.to_list(length=None)
        for record in records:
            if "_id" in record:
                record["_id"] = str(record["_id"])
        return records
    return await fallback_db.find_all_feedback_by_workspace(workspace_id)


async def _load_import_logs(workspace_id: str) -> Dict[str, Dict[str, Any]]:
    if not database._mongodb_available:
        return {}
    cursor = db.import_logs.find({"workspace_id": workspace_id})
    logs = await cursor.to_list(length=None)
    return {str(log["_id"]): log for log in logs}


async def _grouped(workspace_id: str) -> Tuple[List[Dict[str, Any]], int, List[Dict[str, Any]]]:
    records = await _load_feedback(workspace_id)
    logs = await _load_import_logs(workspace_id)
    batches, unattributed, orphans = group_into_batches(records, logs)
    _label_batches(batches)
    return batches, unattributed, orphans


async def list_batches(workspace_id: str) -> List[Dict[str, Any]]:
    """The imports this workspace's feedback arrived in, oldest first."""
    batches, _, _ = await _grouped(workspace_id)
    return [_batch_meta(batch) for batch in batches]


# --- the comparison -------------------------------------------------------


def _classify(
    before_count: int,
    after_count: int,
    before_per_100: float,
    after_per_100: float,
    category: str,
) -> Tuple[str, str, str]:
    """Direction, badge tone and a plain sentence for one theme."""
    if before_count == 0 and after_count == 0:
        return "steady", "neutral", "Not raised in either collection."

    if before_count == 0:
        return (
            "appeared",
            RISING_TONES.get(category, "accent"),
            f"Not raised at all in the earlier import, {after_count} mentions ({after_per_100} per {RATE_BASE}) now.",
        )

    if after_count == 0:
        return (
            "disappeared",
            FALLING_TONES.get(category, "neutral"),
            f"Raised {before_count} times earlier and not once in the later import.",
        )

    if before_count < MIN_MENTIONS or after_count < MIN_MENTIONS:
        leaner = "earlier" if before_count < after_count else "later"
        return (
            "insufficient_evidence",
            "neutral",
            (
                f"Too few mentions to call either way ({before_count} then {after_count}); "
                f"the {leaner} collection is below the {MIN_MENTIONS}-mention floor."
            ),
        )

    delta = after_per_100 - before_per_100
    band = max(MIN_PER_100_DELTA, RELATIVE_BAND * before_per_100)
    if abs(delta) < band:
        return (
            "steady",
            "neutral",
            f"Held roughly steady ({before_per_100} → {after_per_100} per 100 records).",
        )

    change = _change_pct(before_per_100, after_per_100)
    shape = f"{before_per_100} → {after_per_100} per 100 records"
    if delta < 0:
        return (
            "falling",
            FALLING_TONES.get(category, "neutral"),
            f"Fell {abs(change)}% ({shape}).",
        )
    return (
        "rising",
        RISING_TONES.get(category, "neutral"),
        f"Rose {change}% ({shape}).",
    )


def comparability_notes(before: Dict[str, Any], after: Dict[str, Any]) -> List[str]:
    """
    The ways two imports can be too different for a clean before-and-after.

    A rate per 100 records is comparable between collections of different sizes, but
    two things genuinely change what a movement means: a collection an order of
    magnitude smaller is a sample rather than a census, and a collection dominated by
    a different source measures a different population. Both are stated with the
    result instead of being hidden in a footnote."""
    notes: List[str] = []
    smaller = min(before["total"], after["total"])
    larger = max(before["total"], after["total"])
    if smaller and larger / smaller >= 5:
        notes.append(
            f"The two imports differ greatly in size ({larger:,} then {smaller:,} records). Rates per 100"
            " stay comparable, but a movement between collections this unequal is indicative rather than precise."
        )

    before_source = before.get("dominant_source") or ""
    after_source = after.get("dominant_source") or ""
    if before_source and after_source and before_source != after_source:
        notes.append(
            f"The imports are dominated by different sources ({before_source} then {after_source}), so part of"
            " any change is a change in who was heard rather than in the product."
        )
    return notes


def _confidence(before: Dict[str, Any], after: Dict[str, Any], gap_days: Optional[int]) -> str:
    """How much a reader should lean on the comparison."""
    smallest = min(before["total"], after["total"])
    if smallest >= 500 and (gap_days or 0) >= 14:
        return "high"
    if smallest >= 150 and (gap_days or 0) >= 7:
        return "medium"
    return "low"


def _headline(before: Dict[str, Any], after: Dict[str, Any]) -> str:
    """One deterministic sentence: what moved, measured per 100 records."""
    parts: List[str] = []

    delta = round(after["problem_per_100"] - before["problem_per_100"], 2)
    band = max(MIN_PER_100_DELTA, RELATIVE_BAND * before["problem_per_100"])
    shape = f"{before['problem_per_100']} → {after['problem_per_100']} problem mentions per 100 records"

    if abs(delta) < band:
        parts.append(f"Complaint volume held roughly steady ({shape}).")
    else:
        change = abs(_change_pct(before["problem_per_100"], after["problem_per_100"]) or 0.0)
        verb = "fell" if delta < 0 else "rose"
        parts.append(f"Complaint volume {verb} {change}% ({shape}).")

    if before["avg_rating"] is not None and after["avg_rating"] is not None:
        rating_delta = round(after["avg_rating"] - before["avg_rating"], 2)
        if abs(rating_delta) < 0.05:
            parts.append(f"Average rating is unchanged at {after['avg_rating']}.")
        else:
            verb = "up" if rating_delta > 0 else "down"
            parts.append(
                f"Average rating is {verb} {abs(rating_delta)} ({before['avg_rating']} → {after['avg_rating']})."
            )

    if before["total"] and after["total"]:
        volume_change = _change_pct(before["total"], after["total"])
        if volume_change is not None and abs(volume_change) >= 10:
            direction = "more" if volume_change > 0 else "fewer"
            parts.append(f"The later import holds {abs(volume_change)}% {direction} records than the earlier one.")

    return " ".join(parts)


def compare_batches(
    before_items: List[Dict[str, Any]],
    after_items: List[Dict[str, Any]],
    before_meta: Dict[str, Any],
    after_meta: Dict[str, Any],
    max_themes: int = DEFAULT_MAX_THEMES,
    notes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compare two collections of feedback from the same workspace.

    Pure and deterministic: the same two collections always produce the same
    verdicts, which is what lets the result be quoted in a report.
    """
    before_snapshot = _snapshot(before_items)
    after_snapshot = _snapshot(after_items)

    axis_source, axis_sampled = _axis_sample(list(before_items) + list(after_items))
    mined = extract_themes_from_feedback(axis_source, max_themes=max_themes)
    mined_topics = merge_topics(mined)
    mined_by_title = {topic["title"].lower(): topic for topic in mined_topics}

    before_groups = assign_groups(before_items, mined)
    after_groups = assign_groups(after_items, mined)

    # A topic is reported when either collection raised it. The order of the mined
    # topics is preserved so the same workspace always lists topics the same way.
    candidates = [topic["title"] for topic in mined_topics]
    if UNCLASSIFIED_THEME in after_groups or UNCLASSIFIED_THEME in before_groups:
        candidates.append(UNCLASSIFIED_THEME)

    titles: List[str] = []
    seen: set = set()
    for title in candidates:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        titles.append(title)

    rows: List[Dict[str, Any]] = []
    for title in titles:
        before_group = before_groups.get(title) or []
        after_group = after_groups.get(title) or []
        before_count = len(before_group)
        after_count = len(after_group)

        terms = display_terms((mined_by_title.get(title.lower()) or {}).get("terms") or [], axis_source)
        before_per_100 = _per_100(before_count, before_snapshot["total"])
        after_per_100 = _per_100(after_count, after_snapshot["total"])
        # The dominant category is read from the records actually assigned to the topic
        # rather than from the label, so the row describes this workspace's feedback.
        category = _dominant_category(before_group + after_group) if before_group or after_group else "general_feedback"

        direction, tone, reading = _classify(
            before_count, after_count, before_per_100, after_per_100, category
        )

        rows.append(
            {
                "topic_id": stable_topic_id("outcome_topic", title, terms),
                "title": title,
                "category": category,
                "keywords": terms[:6],
                "match_phrases": terms[:8],
                "before_count": before_count,
                "after_count": after_count,
                "before_per_100": before_per_100,
                "after_per_100": after_per_100,
                "change_pct": _change_pct(before_per_100, after_per_100),
                "direction": direction,
                "tone": tone,
                "reading": reading,
            }
        )

    # Movement first, then volume: a reader should see what changed, not the
    # longest list of the same steady topics.
    rows.sort(
        key=lambda row: (
            0 if row["direction"] in ("rising", "falling", "appeared", "disappeared") else 1,
            -abs(row["after_per_100"] - row["before_per_100"]),
            -max(row["before_count"], row["after_count"]),
            row["title"].lower(),
        )
    )

    summary = {direction: 0 for direction in DIRECTIONS}
    for row in rows:
        summary[row["direction"]] += 1

    before_dt = _parse_dt(before_meta.get("imported_at"))
    after_dt = _parse_dt(after_meta.get("imported_at"))
    gap_days = (after_dt - before_dt).days if before_dt and after_dt else None

    confidence = _confidence(before_snapshot, after_snapshot, gap_days)

    method = {
        "unit": "one import of the workspace",
        "topic_axis": f"mined once on both imports together, {len(titles)} topics",
        "assignment": "each record is counted in exactly one topic, by its most specific mined phrase",
        "axis_records": len(axis_source),
        "axis_sampled": axis_sampled,
        "normalisation": f"mentions per {RATE_BASE} records in each import",
        "rate_base": RATE_BASE,
        "min_mentions": MIN_MENTIONS,
        "min_per_100_delta": MIN_PER_100_DELTA,
        "relative_band": RELATIVE_BAND,
        "max_themes": max_themes,
    }
    all_notes = list(notes or []) + comparability_notes(before_snapshot, after_snapshot)
    if axis_sampled:
        all_notes.append(
            f"The topic vocabulary was mined from {len(axis_source)} of {len(before_items) + len(after_items)} "
            "records (evenly spaced); every mention count still covers the full collections."
        )

    return {
        "status": "ready",
        "before": before_snapshot,
        "after": after_snapshot,
        "compared": {"before": _batch_meta(before_meta), "after": _batch_meta(after_meta)},
        "deltas": {
            "total": after_snapshot["total"] - before_snapshot["total"],
            "problem_per_100": round(
                after_snapshot["problem_per_100"] - before_snapshot["problem_per_100"], 2
            ),
            "negative_per_100": round(
                after_snapshot["negative_per_100"] - before_snapshot["negative_per_100"], 2
            ),
            "feature_per_100": round(
                after_snapshot["feature_per_100"] - before_snapshot["feature_per_100"], 2
            ),
            "avg_rating": (
                round(after_snapshot["avg_rating"] - before_snapshot["avg_rating"], 2)
                if before_snapshot["avg_rating"] is not None and after_snapshot["avg_rating"] is not None
                else None
            ),
            "sentiment_score": round(
                after_snapshot["sentiment_score"] - before_snapshot["sentiment_score"], 2
            ),
            "health_score": (
                round(after_snapshot["health_score"] - before_snapshot["health_score"], 1)
                if before_snapshot["health_score"] is not None and after_snapshot["health_score"] is not None
                else None
            ),
        },
        "headline": _headline(before_snapshot, after_snapshot),
        "themes": rows,
        "summary": summary,
        "confidence": confidence,
        "gap_days": gap_days,
        "method": method,
        "notes": all_notes,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def build_comparison(
    workspace_id: str,
    before_batch_id: Optional[str] = None,
    after_batch_id: Optional[str] = None,
    max_themes: int = DEFAULT_MAX_THEMES,
) -> Dict[str, Any]:
    """
    Compare two imports of a workspace, defaulting to the two most recent.

    When there is only one import there is nothing to compare yet, and the response
    says that instead of returning an empty shell — the workspace is one later
    import away from an answer.
    """
    batches, unattributed, orphans = await _grouped(workspace_id)
    metas = [_batch_meta(batch) for batch in batches]

    notes: List[str] = []
    if unattributed:
        notes.append(
            f"{unattributed} records are not tied to an import and are excluded from this comparison."
        )
    for orphan in orphans:
        name = orphan["filename"] or "an import"
        day = (orphan["imported_at"] or "")[:10] or "an unknown date"
        notes.append(
            f"{name} ({day}) has no records left in this workspace — its rows were removed as "
            "duplicates — so it cannot be compared."
        )

    if len(batches) < 2:
        return {
            "status": "needs_two_imports",
            "batches": metas,
            "themes": [],
            "notes": notes
            + [
                "Outcome tracking compares two imports of the same workspace. "
                "Import this product's feedback again later and the change between the two "
                "collections is measured from the records themselves."
            ],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    by_id = {batch["batch_id"]: batch for batch in batches}
    if before_batch_id or after_batch_id:
        if before_batch_id not in by_id or after_batch_id not in by_id:
            raise ValueError("Unknown import batch for this workspace")
        if before_batch_id == after_batch_id:
            raise ValueError("The two imports to compare must be different")
        before_batch, after_batch = by_id[before_batch_id], by_id[after_batch_id]
    else:
        before_batch, after_batch = batches[-2], batches[-1]

    if (before_batch["imported_at"] or "") > (after_batch["imported_at"] or ""):
        before_batch, after_batch = after_batch, before_batch

    comparison = compare_batches(
        before_batch["items"],
        after_batch["items"],
        before_batch,
        after_batch,
        max_themes=max_themes,
        notes=notes,
    )
    comparison["workspace_id"] = workspace_id
    comparison["batches"] = metas
    return comparison


# --- export ---------------------------------------------------------------


def build_markdown(comparison: Dict[str, Any]) -> str:
    """The comparison as a quotable Markdown block."""
    if comparison.get("status") != "ready":
        lines = ["# Outcome tracking", "", "Not enough imports to compare yet.", ""]
        for note in comparison.get("notes") or []:
            lines.append(f"- {note}")
        return "\n".join(lines) + "\n"

    before = comparison["before"]
    after = comparison["after"]
    before_meta = comparison["compared"]["before"]
    after_meta = comparison["compared"]["after"]
    deltas = comparison["deltas"]
    summary = comparison["summary"]

    lines = [
        "# Outcome tracking — measured change between two imports",
        "",
        f"**Earlier:** {before_meta['label']}"
        + (f" (`{before_meta['filename']}`)" if before_meta.get("filename") else "")
        + f" — {before['total']:,} records",
        f"**Later:** {after_meta['label']}"
        + (f" (`{after_meta['filename']}`)" if after_meta.get("filename") else "")
        + f" — {after['total']:,} records",
        f"**Gap:** {comparison['gap_days']} days · **Confidence:** {comparison['confidence']}",
        "",
        f"**{comparison['headline']}**",
        "",
        "## Measured snapshot",
        "",
        "| Measure | Earlier | Later | Change |",
        "| :--- | ---: | ---: | ---: |",
        f"| Records | {before['total']:,} | {after['total']:,} | {deltas['total']:+,} |",
        f"| Complaint mentions / 100 | {before['problem_per_100']} | {after['problem_per_100']} |"
        f" {deltas['problem_per_100']:+} |",
        f"| Feature demand / 100 | {before['feature_per_100']} | {after['feature_per_100']} |"
        f" {deltas['feature_per_100']:+} |",
        f"| Negative sentiment / 100 | {before['negative_per_100']} | {after['negative_per_100']} |"
        f" {deltas['negative_per_100']:+} |",
        f"| Average rating | {before['avg_rating'] if before['avg_rating'] is not None else 'n/a'} |"
        f" {after['avg_rating'] if after['avg_rating'] is not None else 'n/a'} |"
        f" {deltas['avg_rating'] if deltas['avg_rating'] is not None else 'n/a'} |",
        f"| Health score | {before['health_score'] if before['health_score'] is not None else 'n/a'} |"
        f" {after['health_score'] if after['health_score'] is not None else 'n/a'} |"
        f" {deltas['health_score'] if deltas['health_score'] is not None else 'n/a'} |",
        "",
        f"Topics: {summary['rising']} rising, {summary['falling']} falling, {summary['steady']} steady,"
        f" {summary['appeared']} new, {summary['disappeared']} gone,"
        f" {summary['insufficient_evidence']} without enough evidence either way.",
        "",
        "## What moved, topic by topic",
        "",
        f"| Topic | Category | Earlier | Later | Per {RATE_BASE} (earlier → later) | Reading |",
        "| :--- | :--- | ---: | ---: | :--- | :--- |",
    ]

    for row in comparison["themes"]:
        title = str(row["title"]).replace("|", "\\|")
        lines.append(
            f"| {title} | {row['category'].replace('_', ' ')} | {row['before_count']} |"
            f" {row['after_count']} | {row['before_per_100']} → {row['after_per_100']} |"
            f" {row['reading']} |"
        )

    method = comparison["method"]
    lines += [
        "",
        "## Method",
        "",
        f"- Compared unit: {method['unit']}.",
        f"- Topic axis: {method['topic_axis']} — {method['assignment']}.",
        f"- {method['normalisation']}, so a larger second collection is not read as a rise in everything.",
        f"- A movement is claimed only above {method['min_mentions']} mentions on both sides and"
        f" {method['min_per_100_delta']} per 100 records, or {int(method['relative_band'] * 100)}% of the"
        " earlier value — whichever is larger.",
        "- Collections dated from the imports themselves, not from any date in the source file.",
    ]

    if comparison.get("notes"):
        lines += ["", "## Caveats", ""]
        lines += [f"- {note}" for note in comparison["notes"]]

    lines += ["", f"_Generated {comparison['generated_at']}._", ""]
    return "\n".join(lines)
