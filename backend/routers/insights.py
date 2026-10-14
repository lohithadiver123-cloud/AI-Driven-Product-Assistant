"""
Insights Router for Milestone 2.
Provides canonical analysis pipeline for theme extraction, customer pain points,
feature request clustering, trend trajectory, and product health scoring.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from bson import ObjectId

import database
from database import db
from models.insights import (
    WorkspaceInsightsResponse,
    ThemeItem,
    PainPointItem,
    FeatureCluster,
    TrendDataPoint,
)
from services.categorization import categorize, detect_sentiment, batch_categorize
from services.theme_extraction import (
    extract_themes_from_feedback,
    extract_pain_points_from_feedback,
    assign_record_theme,
    measured_group_score,
    _resolve_category,
    _resolve_sentiment,
)
from services.clustering import (
    cluster_feature_requests,
    count_unique_requesters,
    workspace_has_customer_identity,
)
from services.preprocessing import STOPWORDS_SET
from services.text_mining import (
    absorb_overlapping_groups,
    distinctive_terms,
    match_records_by_terms as _match_records_by_terms,
    record_text as _record_text,
    stable_topic_id,
    titleize,
    top_phrases,
)
from services.title_normalizer import (
    needs_title_upgrade,
    normalize_title_groups,
    normalize_topic_titles,
)

from services.trend_analysis import generate_trend_analysis, calculate_health_score
from services.ai_service import check_ai_status, analyze_feedback_with_ai
from config import settings
import os
from routers.auth import get_authorization_header, get_current_user
from routers.feedback import _verify_workspace_access
from fallback_db import (
    find_feedback_by_workspace as fb_find_feedback_by_workspace,
    find_all_feedback_by_workspace as fb_find_all_feedback_by_workspace,
    save_workspace_insights as fb_save_workspace_insights,
    get_workspace_insights as fb_get_workspace_insights,
    _feedback_cache,
    _save_all,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/insights", tags=["insights"])


async def _get_user_from_token(authorization: str) -> dict:
    """Extract and validate the current user from the Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.replace("Bearer ", "")
    return await get_current_user(token)


async def _fetch_workspace_feedback_records(workspace_id: str) -> List[dict]:
    """Fetch all feedback records for a workspace, converting Mongo ObjectIds to strings."""
    if not database._mongodb_available:
        return await fb_find_all_feedback_by_workspace(workspace_id)

    cursor = db.feedback.find({"workspace_id": workspace_id}).sort("created_at", -1)
    records = await cursor.to_list(length=None)
    for r in records:
        r["_id"] = str(r["_id"])
    return records


async def _workspace_has_feedback(workspace_id: str) -> bool:
    """Whether there is anything at all to analyse — one indexed probe, not a count."""
    try:
        if not database._mongodb_available:
            page, _total = await fb_find_feedback_by_workspace(workspace_id, skip=0, limit=1)
            return bool(page)
        return await db.feedback.find_one(
            {"workspace_id": workspace_id}, {"_id": 1}
        ) is not None
    except Exception:
        # Fail open: if the probe itself errors, the analysis will surface the real error.
        return True


# Topic collections in a stored analysis, and the title rules each one follows.
_TITLE_TOPIC_TYPES = {
    "pain_points": "pain_point",
    "feature_clusters": "cluster",
    "themes": "theme",
}


def _sanitize_cached_insights(cached: dict) -> dict:
    """
    Sanitize cached insights dict before feeding into Pydantic.
    - Converts string analyzed_at → datetime
    - Fills missing sentiment_distribution from trends
    - Ensures health_score defaults exist
    """
    from datetime import datetime as dt

    # Fix analyzed_at: Pydantic expects datetime, DB may return string
    if "analyzed_at" in cached and isinstance(cached["analyzed_at"], str):
        try:
            cached["analyzed_at"] = dt.fromisoformat(cached["analyzed_at"].replace("Z", "+00:00"))
        except Exception:
            cached["analyzed_at"] = None

    # Ensure health_score has a sane default
    if not cached.get("health_score"):
        cached["health_score"] = 75.0

    # Fill sentiment_distribution from trend data if missing
    if not cached.get("sentiment_distribution"):
        trends = cached.get("trends", [])
        cached["sentiment_distribution"] = {
            "positive": sum(t.get("positive_count", 0) for t in trends),
            "neutral": sum(t.get("neutral_count", 0) for t in trends),
            "negative": sum(t.get("negative_count", 0) for t in trends),
        }

    # Ensure required list fields exist
    for field in ("themes", "pain_points", "feature_clusters", "trends"):
        if not cached.get(field):
            cached[field] = []

    # Ensure required fields exist
    if "total_analyzed" not in cached:
        cached["total_analyzed"] = cached.get("total_feedback", len(cached.get("pain_points", [])))

    if not cached.get("category_distribution"):
        cached["category_distribution"] = {}

    # Auto-normalize titles on read so legacy or un-migrated workspace records
    # always display clean human-grade titles and executive descriptions. Placeholders a
    # previous pass already wrote are left alone here: retrying them on every read would
    # send the same titles to the model on every page load.
    for field, topic_type in _TITLE_TOPIC_TYPES.items():
        if cached.get(field):
            cached[field] = normalize_topic_titles(cached[field], topic_type, revise_placeholders=False)

    return cached


def _titles_pending_upgrade(cached: dict) -> bool:
    """Whether any stored topic still displays an un-upgraded algorithmic title."""
    return any(
        needs_title_upgrade(topic, topic_type, revise_placeholders=False)
        for field, topic_type in _TITLE_TOPIC_TYPES.items()
        for topic in (cached.get(field) or [])
    )


async def _store_upgraded_titles(workspace_id: str, cached: dict) -> None:
    """
    Write the titles upgraded on read back to storage.

    Without this the same analysis would be re-normalised — and re-sent to the model — on
    every request, which is both slow and unstable: two readers would see two titles.
    """
    payload = {field: cached.get(field) or [] for field in _TITLE_TOPIC_TYPES}
    try:
        if database._mongodb_available:
            await db.workspace_insights.update_one({"workspace_id": workspace_id}, {"$set": payload})
        else:
            await fb_save_workspace_insights(workspace_id, cached)
    except Exception as e:
        logger.warning(f"Could not persist upgraded titles for {workspace_id}: {e}")


async def _sanitize_and_store(workspace_id: str, cached: dict) -> dict:
    """Upgrade titles for a read, persisting the upgrade once it has been computed."""
    pending = _titles_pending_upgrade(cached)
    cached = _sanitize_cached_insights(cached)
    if pending:
        await _store_upgraded_titles(workspace_id, cached)
    return cached


def _ai_pain_point_terms(ai_pain_point: Dict[str, Any], feedback_records: List[dict], limit: int = 10) -> List[str]:
    """
    Search terms that describe an AI pain point — and actually isolate it.

    The model tends to offer corpus-wide vocabulary (in a music app: "music", "song",
    "spotify", "ads"). Grouping on those makes several different pain points match the
    same complaints, so terms mentioned across most of the corpus are dropped here
    rather than used to define a topic.
    """
    terms = [str(k).lower() for k in (ai_pain_point.get("keywords") or []) if len(str(k)) > 2]
    terms += re.findall(r"[a-z]{4,}", str(ai_pain_point.get("title") or "").lower())
    ordered = [term for term in dict.fromkeys(terms) if term not in STOPWORDS_SET]
    return distinctive_terms(ordered, feedback_records)[:limit]


def _merge_ai_pain_points(
    pain_points: List[dict],
    ai_pain_points: List[dict],
    feedback_records: List[dict],
) -> List[dict]:
    """
    Attach each AI pain point to the deterministic group whose evidence it describes.

    Pairing by list position attached AI titles to unrelated quotes and counts, so a
    pain point about ads could report the complaint volume of the unsorted catch-all
    bucket. Pain points are matched on evidence overlap instead, and an AI pain point
    that matches no group is grounded directly in the feedback it quotes.
    """
    if not ai_pain_points:
        return pain_points

    evidence_texts = [
        [(_record_text(item), _resolve_sentiment(item)) for item in records[:400]]
        for records in _pain_point_evidence(pain_points, feedback_records)
    ]
    used_groups = set()

    for ai_pain_point in ai_pain_points:
        terms = _ai_pain_point_terms(ai_pain_point, feedback_records)
        if not terms:
            # Nothing distinctive enough to point at a subset of this corpus: the model's
            # label describes the product, not an issue, so it must not become a pain point.
            continue
        best_index, best_score = None, 0
        for index, texts in enumerate(evidence_texts):
            if index in used_groups:
                continue
            score = sum(1 for text, _ in texts if any(term in text for term in terms))
            if score > best_score:
                best_index, best_score = index, score

        # Require at least 2 matching records, or 100% of the group when small
        if best_index is not None and (best_score >= 2 or best_score >= len(evidence_texts[best_index])):
            used_groups.add(best_index)
            pain_point = pain_points[best_index]
            if ai_pain_point.get("title"):
                pain_point["mined_title"] = pain_point.get("title")
                pain_point["ai_title"] = str(ai_pain_point["title"])
                pain_point["title"] = str(ai_pain_point["title"])
            for field in ("root_cause", "recommended_action"):
                if ai_pain_point.get(field):
                    pain_point[field] = ai_pain_point[field]

            # Regenerate sample_quotes from records that actually match the
            # AI terms so the displayed quote is always topically consistent
            # with the pain point heading — not a leftover from the mined group.
            matched_records = _match_records_by_terms(feedback_records, terms)[:20]
            if matched_records:
                seen_q: set = set()
                fresh_quotes: List[str] = []
                for rec in matched_records:
                    q = (rec.get("content") or rec.get("title") or "").strip()
                    if q and q not in seen_q and len(fresh_quotes) < 3:
                        seen_q.add(q)
                        fresh_quotes.append(q[:130] + ("..." if len(q) > 130 else ""))
                if fresh_quotes:
                    pain_point["sample_quotes"] = fresh_quotes
                    pain_point["distinct_sample_quotes"] = fresh_quotes
            continue


        grounded = _ground_pain_point(ai_pain_point, terms, feedback_records)
        if grounded:
            pain_points.append(grounded)

    for pain_point in pain_points:
        if not pain_point.get("root_cause"):
            pain_point["root_cause"] = (
                f"Underlying friction in {pain_point.get('category', 'system')} flow affecting user workflow."
            )
    return pain_points


def _pain_point_evidence(pain_points: List[dict], feedback_records: List[dict]) -> List[List[dict]]:
    """Recover the feedback records each pain point was built from."""
    quotes_to_records = {}
    for item in feedback_records:
        for quote in ((item.get("content") or ""), (item.get("title") or "")):
            quote = quote.strip()
            if quote:
                quotes_to_records.setdefault(quote[:130], item)

    evidence = []
    for pain_point in pain_points:
        records = []
        for quote in pain_point.get("sample_quotes") or []:
            lookup = str(quote).strip()
            if lookup.endswith("..."):
                lookup = lookup[:-3]
            record = quotes_to_records.get(lookup)
            if record is not None:
                records.append(record)
        evidence.append(records)
    return evidence


def _ground_pain_point(ai_pain_point: dict, terms: List[str], feedback_records: List[dict]) -> Optional[dict]:
    """
    Build a pain point from the records its distinctive terms actually select.

    Matching is whole-word (substring matching counted "downloads" as a mention of "ads")
    and the title, severity and impact come from the matched records — the phrase they
    share, scored by the same measurement formula the mined pain points use. The model's
    own title is retained as provenance only.
    """
    if not terms:
        return None
    matches = _match_records_by_terms(feedback_records, terms)[:500]
    if not matches:
        return None

    measured = measured_group_score(matches, len(feedback_records))
    mined = top_phrases(matches, limit=1)
    ai_title = str(ai_pain_point.get("title") or "Customer friction")
    title = titleize(mined[0]) if mined else ai_title

    seen_quotes = set()
    quotes = []
    for item in matches:
        quote = (item.get("content") or item.get("title") or "").strip()
        if quote and quote not in seen_quotes and len(quotes) < 3:
            seen_quotes.add(quote)
            quotes.append(quote[:130] + ("..." if len(quote) > 130 else ""))

    return {
        "id": "",
        "title": title,
        "ai_title": ai_title,
        "description": str(ai_pain_point.get("description") or f"Observed in {measured['count']} customer complaints."),
        "severity": measured["severity"],
        "impact_score": measured["impact_score"],
        "affected_users_count": measured["count"],
        "category": ai_pain_point.get("category") or "general_feedback",
        "root_cause": ai_pain_point.get("root_cause"),
        "recommended_action": ai_pain_point.get("recommended_action") or "Triage these complaints with engineering.",
        "keywords": terms[:6],
        "sample_quotes": quotes,
        "distinct_sample_quotes": quotes,
        "score_breakdown": {
            "frequency": measured["count"],
            "avg_rating": measured["avg_rating"],
            "negative_sentiment_pct": measured["negative_pct"],
            "negative_sentiment_count": measured["negative_count"],
            "bug_count": measured["bug_count"],
            "severity_level": measured["severity"],
            "matched_terms": terms[:6],
            "source": "ai_matched_feedback",
            "formula_weights": "Volume (35%) + Low Rating (25%) + Negative % (25%) + Bug Ratio (15%)",
        },
    }


def _record_key(record: Dict[str, Any]) -> str:
    """Stable identity for a feedback record inside one analysis run."""
    return str(record.get("_id") if record.get("_id") is not None else id(record))


def _topic_members(topic: Dict[str, Any], feedback_records: List[dict]) -> set:
    """Records a topic's own terms select, used to detect topics that overlap."""
    terms = [str(term).lower() for term in (topic.get("keywords") or [])][:6]
    terms += re.findall(r"[a-z]{4,}", str(topic.get("title") or topic.get("cluster_name") or "").lower())
    terms = [term for term in dict.fromkeys(terms) if term and term not in STOPWORDS_SET]
    if not terms:
        return set()
    return {_record_key(record) for record in _match_records_by_terms(feedback_records, terms)}


def _identify_topics(
    topics: List[dict],
    feedback_records: List[dict],
    prefix: str,
    containment: float = 0.8,
) -> List[dict]:
    """
    Collapse topics that describe the same records and give the survivors stable ids.

    Two topics whose evidence largely overlaps are one issue reported twice: keeping both
    inflates the complaint count and makes a PM act on a duplicate. The absorbed label is
    kept on the survivor, so nothing a customer said is lost — it is attributed to the
    issue it belongs to.

    The threshold is deliberately strict (80% of a topic's records already covered). A
    looser rule merged app-breakage complaints under a monetisation headline; topics that
    merely share user vocabulary stay separate, and a reviewer sees more of them rather
    than one over-general issue.
    """
    if not topics:
        return []

    ordered = sorted(
        topics,
        key=lambda topic: float(topic.get("impact_score") or topic.get("priority_score") or 0.0),
        reverse=True,
    )
    labels = [str(topic.get("title") or topic.get("cluster_name") or "topic") for topic in ordered]

    # Keyed by position, not by label: two topics can share a label (the miner falls back to
    # "Unclassified complaints" when a corpus is too small to name a group), and collapsing
    # by label text would treat one of them as an alias of the other.
    keyed = [(f"{index}\u0000{label}", _topic_members(topic, feedback_records)) for index, (topic, label) in enumerate(zip(ordered, labels))]
    kept, absorbed = absorb_overlapping_groups(keyed, containment=containment)
    kept_keys = {key for key, _ in kept}

    aliases: Dict[str, List[str]] = {}
    for absorbed_key, kept_key in absorbed:
        aliases.setdefault(kept_key, []).append(absorbed_key.split("\u0000", 1)[-1])

    identified: List[dict] = []
    for index, (topic, label) in enumerate(zip(ordered, labels)):
        key = f"{index}\u0000{label}"
        if key not in kept_keys:
            continue
        topic = dict(topic)
        topic["rank"] = len(identified) + 1
        topic["id"] = stable_topic_id(prefix, label, topic.get("keywords"))
        if aliases.get(key):
            topic["also_described_as"] = aliases[key][:4]
        identified.append(topic)
    return identified


import time
_stored_insights_cache: dict = {}  # workspace_id -> (insights_dict, expires_at)


async def _load_stored_insights(workspace_id: str) -> Optional[dict]:
    """
    Return the persisted analysis for a workspace, or None when it has never been analyzed.
    Cached for 30s in-memory so concurrent requests to clusters/pain-points don't repeat queries.
    """
    now = time.time()
    cached_entry = _stored_insights_cache.get(workspace_id)
    if cached_entry and cached_entry[1] > now:
        return cached_entry[0]

    if database._mongodb_available:
        cached = await db.workspace_insights.find_one({"workspace_id": workspace_id})
        if cached:
            cached.pop("_id", None)
            res = await _sanitize_and_store(workspace_id, cached)
            _stored_insights_cache[workspace_id] = (res, now + 30.0)
            return res
        return None

    cached = await fb_get_workspace_insights(workspace_id)
    if cached:
        res = await _sanitize_and_store(workspace_id, cached)
        _stored_insights_cache[workspace_id] = (res, now + 30.0)
        return res
    return None


async def run_analysis(
    workspace_id: str,
    authorization: str,
    progress: Optional[Any] = None,
) -> WorkspaceInsightsResponse:
    """
    Run the canonical Product Intelligence & Analysis Pipeline:
    1. Categorizes and computes deterministic sentiment for all workspace records.
    2. Mines high-level themes with exact sentiment counts.
    3. Detects customer pain points with severity & explainable impact scoring.
    4. Aggregates feature requests into semantic clusters with unique customer counts & distinct quotes.
    5. Generates chronological trends and product health score.
    6. Persists canonical analysis attributes back onto each feedback record in the database.

    This is the work itself, not a route: it runs on a background job (see
    services/analysis_jobs.py) so that no HTTP request waits on it. `progress` is an
    optional callback reporting which stage has been reached — it does no I/O of its
    own, and omitting it runs the pipeline exactly as before.
    """
    report = progress or (lambda _stage: None)
    user = await _get_user_from_token(authorization)
    workspace = await _verify_workspace_access(workspace_id, user)

    report("reading")
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)
    total_count = len(feedback_records)
    report("categorizing")

    # 1. Deterministic categorization and sentiment for every record.
    #    The values already stored are captured first so step 2 can skip writes that
    #    change nothing. The engine is deterministic, so re-analysing an unchanged
    #    workspace recomputes exactly what is already in the database — and writing
    #    10,100 identical updates to Atlas measured at ~29 s of a ~54 s request.
    analyzed_updates = []
    stored_analysis = {}
    for r in feedback_records:
        full_text = f"{r.get('title') or ''} {r.get('content') or ''}".strip()
        cat = categorize(full_text)
        sent = detect_sentiment(full_text, r.get("rating"))

        stored_analysis[str(r["_id"])] = {
            "category": r.get("category"),
            "sentiment": r.get("sentiment"),
            "cleaned": r.get("cleaned"),
            # Captured before step 2 overwrites it on the in-memory record.
            "theme": r.get("theme"),
        }

        r["category"] = cat
        r["sentiment"] = sent
        r["cleaned"] = True
        analyzed_updates.append((r["_id"], {"category": cat, "sentiment": sent, "cleaned": True}))

    # 2. Extract the workspace's themes, then tag each record with its own theme.
    #    Themes come from the corpus, so a record's theme is the mined topic it matches.
    report("themes")
    themes = extract_themes_from_feedback(feedback_records)
    updates_by_id = {str(rec_id): fields for rec_id, fields in analyzed_updates}
    for r in feedback_records:
        theme = assign_record_theme(f"{r.get('title') or ''} {r.get('content') or ''}", themes)
        r["theme"] = theme
        if str(r.get("_id")) in updates_by_id:
            updates_by_id[str(r["_id"])]["theme"] = theme

    # Persist canonical fields to DB, skipping unchanged records.
    #
    # The rows are identical in what they are being told: the analysis is deterministic, so
    # 10,000 records only ever need the handful of distinct (category, sentiment, cleaned,
    # theme) combinations written once each. Sending one update per record instead measured
    # at 30.3 s of a 73.8 s analysis against the deployed Atlas cluster (39 ms round trip),
    # which is what left the progress bar sitting on "Extracting themes" for most of a
    # minute. Grouping by the values being written turns those 10,000 round trips into a
    # few dozen.
    if database._mongodb_available:
        # The values that differ from what this record already stores, grouped by those
        # values, so one write serves every record that shares them.
        groups: Dict[tuple, Dict[str, Any]] = {}
        skipped = 0
        for rec_id, update_fields in analyzed_updates:
            before = stored_analysis.get(str(rec_id), {})
            changed_fields = {
                field: value
                for field, value in update_fields.items()
                if before.get(field) != value
            }
            if not changed_fields:
                # Nothing to say: the stored analysis already matches what we computed.
                skipped += 1
                continue

            key = tuple(sorted((field, str(value)) for field, value in changed_fields.items()))
            group = groups.setdefault(key, {"fields": changed_fields, "ids": []})
            group["ids"].append(rec_id)

        # All of the groups travel in one bulk_write. Sending them one at a time measured
        # at 0.3 s each against the deployed cluster — a few hundred round trips for what
        # is one write.
        from pymongo import UpdateMany

        # Bounded so one filter document stays a sane size whatever the corpus looks like.
        IDS_PER_WRITE = 2000
        written = 0
        ops = []
        for group in groups.values():
            ids = group["ids"]
            for start in range(0, len(ids), IDS_PER_WRITE):
                chunk = ids[start:start + IDS_PER_WRITE]
                targets = [
                    ObjectId(rec_id) if ObjectId.is_valid(str(rec_id)) else rec_id
                    for rec_id in chunk
                ]
                ops.append(UpdateMany({"_id": {"$in": targets}}, {"$set": group["fields"]}))
                written += len(chunk)
        for start in range(0, len(ops), 200):
            await db.feedback.bulk_write(ops[start:start + 200], ordered=False)
        logger.info(
            "analyse %s: %d records, %d written in %d grouped updates, %d already current",
            workspace_id, total_count, written, len(groups), skipped,
        )
    else:
        for rec_id, update_fields in analyzed_updates:
            if str(rec_id) in _feedback_cache:
                _feedback_cache[str(rec_id)].update(update_fields)
        _save_all()

    # 3. Customer Pain Points
    report("pain_points")
    pain_points = extract_pain_points_from_feedback(feedback_records)

    # 4. Feature Request Clusters
    report("clusters")
    feature_clusters = cluster_feature_requests(feedback_records)

    # 5. AI Intelligence Layer (Groq LLM)
    ai_summary = None
    ai_powered = False
    ai_model = None

    report("ai")
    ai_status = check_ai_status()
    if ai_status.get("available"):
        try:
            ai_data = analyze_feedback_with_ai(feedback_records)
            if ai_data:
                ai_summary = ai_data.get("ai_summary")
                ai_powered = True
                ai_model = ai_data.get("ai_model")

                # Merge AI root-cause analysis and actions into pain points
                pain_points = _merge_ai_pain_points(
                    pain_points, ai_data.get("pain_points", []), feedback_records
                )

                # Synthesize AI Feature Clusters
                ai_clusters = ai_data.get("feature_clusters", [])
                has_customer_identity = workspace_has_customer_identity(feedback_records)
                if ai_clusters and len(ai_clusters) >= 3:
                    synthesized_clusters = []
                    for idx, ac in enumerate(ai_clusters[:6]):
                        c_name = ac.get("cluster_name") or f"Feature Opportunity {idx+1}"
                        c_summary = ac.get("summary") or "High-value user requested capability."
                        c_kws = ac.get("keywords") or [w.lower() for w in c_name.split() if len(w) > 3]
                        
                        # Find matching user requests: whole-word mentions of distinctive terms
                        # only, so corpus-wide vocabulary cannot inflate an opportunity's volume.
                        cluster_terms = distinctive_terms(
                            [str(kw) for kw in c_kws if len(str(kw)) > 2]
                            + [w for w in c_name.split() if len(w) > 3],
                            feedback_records,
                        )
                        matched_items = _match_records_by_terms(feedback_records, cluster_terms) if cluster_terms else []

                        # If no direct match, fallback to matched slice
                        if not matched_items and idx < len(feature_clusters):
                            matched_items = [it for it in feedback_records if it.get("_id") in feature_clusters[idx].get("feedback_ids", [])]
                        if not matched_items:
                            # No workspace record backs this AI cluster — skip it rather
                            # than present an opportunity with fabricated volume.
                            continue

                        count = len(matched_items)
                        unique_users = count_unique_requesters(matched_items, has_customer_identity)
                        
                        seen_q = set()
                        quotes = []
                        for it in matched_items:
                            q = (it.get("content") or it.get("title") or "").strip()
                            if q and q not in seen_q and len(quotes) < 3:
                                seen_q.add(q)
                                quotes.append(q[:130] + ("..." if len(q) > 130 else ""))

                        # Priority and demand
                        p_score = float(ac.get("priority_score", 65.0))
                        d_level = ac.get("demand_level", "high" if p_score >= 55.0 else ("medium" if p_score >= 32.0 else "low")).lower()
                        if d_level not in ("high", "medium", "low"):
                            d_level = "medium"

                        synthesized_clusters.append({
                            "id": "",
                            "cluster_name": c_name,
                            "ai_cluster_name": c_name,
                            "summary": c_summary,
                            "request_count": count,
                            "unique_customers_count": unique_users,
                            "demand_level": d_level,
                            "priority_score": round(p_score, 1),
                            "keywords": (cluster_terms or [str(kw) for kw in c_kws])[:5],
                            "sample_requests": quotes if quotes else (feature_clusters[idx].get("sample_requests", []) if idx < len(feature_clusters) else []),
                            "distinct_sample_quotes": quotes if quotes else (feature_clusters[idx].get("distinct_sample_quotes", []) if idx < len(feature_clusters) else []),
                            "feedback_ids": [str(it.get("_id", "")) for it in matched_items[:10]],
                            "score_breakdown": {
                                "request_count": count,
                                "unique_customers_count": unique_users,
                                "unique_customers_count_basis": (
                                    "unique_customers" if has_customer_identity else "unavailable"
                                ),
                                "demand_level": d_level,
                                "formula_weights": (
                                    "Priority score synthesised by the AI model — measured inputs: request volume, unique customers and rating satisfaction"
                                    if has_customer_identity
                                    else "Priority score synthesised by the AI model — measured inputs: request volume and rating satisfaction."
                                         " Requester breadth is excluded because this workspace carries no per-user identity"
                                ),
                            }
                        })
                    if synthesized_clusters:
                        feature_clusters = synthesized_clusters
        except Exception as e:
            logger.warning(f"AI feedback analysis error: {e}")


    # 5b. Topic hygiene for both paths: collapse topics that describe the same records
    #     (one complaint reported four times inflates every count downstream) and assign
    #     ids derived from each topic so links survive the next analysis.
    pain_points = _identify_topics(pain_points, feedback_records, "pain_point")
    feature_clusters = _identify_topics(feature_clusters, feedback_records, "cluster")

    # 5c. Professional Title Normalization: Upgrade raw n-gram titles into clean PM titles.
    #     All three kinds travel in one prompt — see normalize_title_groups — because three
    #     separate calls made this the slowest stage of an analysis whenever the first
    #     provider was rate limited.
    report("titles")
    normalize_title_groups([
        (pain_points, "pain_point"),
        (feature_clusters, "cluster"),
        (themes, "theme"),
    ])

    # 6. Trend Analysis & Health Score

    report("trends")
    trends = generate_trend_analysis(feedback_records)
    health_score = calculate_health_score(feedback_records)

    # Category distribution
    category_counts: Dict[str, int] = {}
    sentiment_counts: Dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}

    from services.theme_extraction import _resolve_category, _resolve_sentiment

    for it in feedback_records:
        c = _resolve_category(it)
        category_counts[c] = category_counts.get(c, 0) + 1
        s = _resolve_sentiment(it)
        if s in sentiment_counts:
            sentiment_counts[s] += 1
        else:
            sentiment_counts[s] = 1


    report("saving")
    now = datetime.utcnow()
    insights_data = {
        "workspace_id": workspace_id,
        "workspace_name": workspace.get("name", "Product Workspace"),
        "total_analyzed": total_count,
        "health_score": health_score,
        "themes": themes,
        "pain_points": pain_points,
        "feature_clusters": feature_clusters,
        "trends": trends,
        "category_distribution": category_counts,
        "sentiment_distribution": sentiment_counts,
        "ai_summary": ai_summary,
        "ai_powered": ai_powered,
        "ai_model": ai_model,
        "analyzed_at": now,
    }

    # Store or update in MongoDB if available
    if database._mongodb_available:
        await db.workspace_insights.update_one(
            {"workspace_id": workspace_id},
            {"$set": insights_data},
            upsert=True,
        )
    else:
        await fb_save_workspace_insights(workspace_id, insights_data)

    _stored_insights_cache.pop(workspace_id, None)

    return WorkspaceInsightsResponse(**insights_data)


@router.get("/ai/status")
async def get_ai_status(authorization: str = Depends(get_authorization_header)):
    """Check whether Groq AI is active or running in heuristic mode."""
    await _get_user_from_token(authorization)
    return check_ai_status()


@router.post("/ai/configure-key")
async def configure_ai_key(
    payload: Dict[str, str],
    authorization: str = Depends(get_authorization_header),
):
    """Dynamically configure or test the Groq API key."""
    await _get_user_from_token(authorization)
    key = payload.get("api_key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key is required")

    settings.GROQ_API_KEY = key
    os.environ["GROQ_API_KEY"] = key
    status_res = check_ai_status()
    if not status_res.get("available"):
        raise HTTPException(status_code=400, detail=f"Failed to activate key: {status_res.get('message')}")
    return status_res


def _empty_insights(workspace_id: str, workspace: Optional[dict]) -> WorkspaceInsightsResponse:
    """A valid, honest "nothing analysed yet" payload — never a fake score."""
    return WorkspaceInsightsResponse(
        workspace_id=workspace_id,
        workspace_name=(workspace or {}).get("name"),
        total_analyzed=0,
        health_score=0.0,
    )


@router.post("/{workspace_id}/analyze", response_model=Dict[str, Any], status_code=status.HTTP_202_ACCEPTED)
async def start_workspace_analysis(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """
    Queue a full analysis of a workspace and return its status at once.

    The pipeline takes ~a minute on a large workspace and can wait on rate-limited
    providers, so the caller polls GET /{workspace_id}/status rather than holding the
    request open. A workspace already being analysed is joined, not restarted.
    """
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    from services.analysis_jobs import start

    return start(workspace_id, authorization, reason="manual")


@router.get("/{workspace_id}/status", response_model=Dict[str, Any])
async def get_workspace_analysis_status(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """What the analysis for this workspace is doing right now, and what it last produced."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    from services.analysis_jobs import get_status

    return await get_status(workspace_id)


@router.get("/{workspace_id}", response_model=WorkspaceInsightsResponse)
async def get_workspace_insights(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """
    Get the computed insights for a workspace.

    Returns what has already been computed. If nothing has, the analysis is queued in
    the background and an empty payload returns immediately: this used to run the whole
    pipeline inside the request, which made opening Insights block for a minute.
    """
    user = await _get_user_from_token(authorization)
    workspace = await _verify_workspace_access(workspace_id, user)

    if database._mongodb_available:
        cached = await db.workspace_insights.find_one({"workspace_id": workspace_id})
        if cached:
            cached.pop("_id", None)
            cached = await _sanitize_and_store(workspace_id, cached)
            return WorkspaceInsightsResponse(**cached)
    else:
        cached = await fb_get_workspace_insights(workspace_id)
        if cached:
            cached = await _sanitize_and_store(workspace_id, cached)
            return WorkspaceInsightsResponse(**cached)

    if not await _workspace_has_feedback(workspace_id):
        # Nothing to analyse. Queueing anyway would store an empty analysis and make the
        # workspace look processed when it is simply unpopulated.
        return _empty_insights(workspace_id, workspace)

    from services.analysis_jobs import start

    start(workspace_id, authorization, reason="auto")
    return _empty_insights(workspace_id, workspace)


@router.get("/{workspace_id}/themes", response_model=List[ThemeItem])
async def get_workspace_themes(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Get extracted customer feedback themes for a workspace."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    stored = await _load_stored_insights(workspace_id)
    if stored and stored.get("themes"):
        return stored["themes"]
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)
    return normalize_topic_titles(extract_themes_from_feedback(feedback_records), "theme")


@router.get("/{workspace_id}/pain-points", response_model=List[PainPointItem])
async def get_workspace_pain_points(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Get identified customer pain points and severity rankings."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    stored = await _load_stored_insights(workspace_id)
    if stored and stored.get("pain_points"):
        return sorted(stored["pain_points"], key=lambda p: p.get("impact_score", 0.0), reverse=True)
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)
    return normalize_topic_titles(extract_pain_points_from_feedback(feedback_records), "pain_point")


@router.get("/{workspace_id}/clusters", response_model=List[FeatureCluster])
async def get_workspace_feature_clusters(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Get aggregated feature request clusters."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    stored = await _load_stored_insights(workspace_id)
    if stored and stored.get("feature_clusters"):
        return sorted(stored["feature_clusters"], key=lambda c: c.get("priority_score", 0.0), reverse=True)
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)
    return normalize_topic_titles(cluster_feature_requests(feedback_records), "cluster")



@router.get("/{workspace_id}/trends", response_model=List[TrendDataPoint])
async def get_workspace_trends(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """Get trend trajectory and sentiment history."""
    user = await _get_user_from_token(authorization)
    await _verify_workspace_access(workspace_id, user)
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)
    return generate_trend_analysis(feedback_records)


@router.post("/{workspace_id}/crew-ai-analyze")
async def run_crew_ai_insights_endpoint(
    workspace_id: str,
    authorization: str = Depends(get_authorization_header),
):
    """
    Execute the Milestone 2 CrewAI Multi-Agent Pipeline:
    - Agent 1: Theme & Pain Point Analyst
    - Agent 2: Feature Request & Opportunity Strategist
    - Agent 3: Product Trend & Sentiment Trajectory Analyst
    """
    user = await _get_user_from_token(authorization)
    workspace = await _verify_workspace_access(workspace_id, user)
    feedback_records = await _fetch_workspace_feedback_records(workspace_id)

    if not feedback_records:
        raise HTTPException(status_code=400, detail="No feedback records found in this workspace to run CrewAI analysis.")

    try:
        from agents.crew import run_milestone2_crew
        crew_res = run_milestone2_crew(feedback_records, workspace.get("name", "Product Workspace"))

        # Calculate category and sentiment distributions
        category_counts: Dict[str, int] = {}
        sentiment_counts: Dict[str, int] = {"positive": 0, "neutral": 0, "negative": 0}
        from services.theme_extraction import _resolve_category, _resolve_sentiment

        for it in feedback_records:
            c = _resolve_category(it)
            category_counts[c] = category_counts.get(c, 0) + 1
            s = _resolve_sentiment(it)
            if s in sentiment_counts:
                sentiment_counts[s] += 1
            else:
                sentiment_counts[s] = 1

        # Save to database
        now = datetime.utcnow()
        insights_data = {
            "workspace_id": workspace_id,
            "workspace_name": workspace.get("name", "Product Workspace"),
            "total_analyzed": len(feedback_records),
            "health_score": crew_res.get("health_score", 75.0),
            "themes": crew_res.get("themes", []),
            "pain_points": crew_res.get("pain_points", []),
            "feature_clusters": crew_res.get("feature_clusters", []),
            "trends": crew_res.get("trends", []),
            "category_distribution": category_counts,
            "sentiment_distribution": sentiment_counts,
            "ai_powered": True,
            "ai_model": "CrewAI (3 Multi-Agent Crew)",
            "analyzed_at": now,
        }

        if database._mongodb_available:
            await db.workspace_insights.update_one(
                {"workspace_id": workspace_id},
                {"$set": insights_data},
                upsert=True,
            )

        return {
            "status": "success",
            "message": "Milestone 2 CrewAI Multi-Agent execution finished.",
            "agents_executed": crew_res.get("agents", []),
            "crew_output": crew_res.get("crew_output"),
            "insights": insights_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CrewAI execution error: {str(e)}")

