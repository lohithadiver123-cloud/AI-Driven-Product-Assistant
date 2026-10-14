"""
Feature Request Aggregation and Clustering engine.
Clusters user requests into product opportunities with deterministic priority scoring,
unique requester counts, and deduplicated representative quotes.

Clusters are derived from the workspace's OWN feedback: candidate phrases are mined
from the corpus, requests are grouped by the strongest phrase they mention, and each
cluster's name, summary and keywords are built from the words users actually wrote.
No catalogue of product features is involved, so the same code produces music-app
clusters for a music app and social-app clusters for a social app.
"""

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set

from services.text_mining import (
    FEATURE_INTENT_KEYWORDS,
    REQUEST_MARKERS,
    build_surface_index,
    group_by_phrases,
    group_keywords,
    label_group,
    record_text,
    stable_topic_id,
)
from services.theme_extraction import _resolve_sentiment


# A cluster is only seeded by a phrase that describes a subset of the corpus. A phrase
# mentioned in more than this share of all requests is background vocabulary.
CORPUS_WIDE_PHRASE_SHARE = 0.2

# Feedback fields that identify the person who left the record, in priority order.
IDENTITY_FIELDS = (
    "customer_name",
    "customer_email",
    "user_id",
    "author",
    "username",
    "reviewer",
    "reviewer_name",
    "source_user",
)


def compute_jaccard_similarity(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    """Compute Jaccard token overlap similarity between two sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a.intersection(tokens_b))
    union = len(tokens_a.union(tokens_b))
    return intersection / union if union > 0 else 0.0


# --------------------------------------------------------------------------
# Requester identity
# --------------------------------------------------------------------------


def _identity_value(item: Dict[str, Any]) -> Optional[str]:
    for field in IDENTITY_FIELDS:
        value = item.get(field)
        if value is not None and str(value).strip():
            return str(value).strip().lower()
    return None


def workspace_has_customer_identity(feedback_list: List[Dict[str, Any]]) -> bool:
    """True when at least one record carries a real per-person identifier."""
    return any(_identity_value(item) for item in feedback_list)


def count_unique_requesters(items: List[Dict[str, Any]], has_identity: Optional[bool] = None) -> int:
    """
    Count distinct requesters, or 0 when the workspace cannot answer that question.

    0 means "unknown": most CSV imports carry no per-person identifier. Fabricating one
    identifier per record would make this number silently identical to the request count
    and inflate every priority score.
    """
    if not items:
        return 0
    if has_identity is None:
        has_identity = workspace_has_customer_identity(items)
    if not has_identity:
        return 0
    return len({_identity_value(item) for item in items if _identity_value(item)})


# --------------------------------------------------------------------------
# Feature-request selection
# --------------------------------------------------------------------------


def _select_feature_items(feedback_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep feedback that actually asks for a change, filtering out pure bug reports."""
    categorized_features = [
        item for item in feedback_list
        if item.get("category") == "feature_request"
    ]
    if len(categorized_features) >= 5:
        return categorized_features

    feature_items = [
        item for item in feedback_list
        if item.get("category") != "bug_report"
        and any(marker in record_text(item) for marker in REQUEST_MARKERS)
    ]

    if len(feature_items) < 2:
        feature_items = [
            item for item in feedback_list
            if item.get("category") != "bug_report"
            and any(keyword in record_text(item) for keyword in FEATURE_INTENT_KEYWORDS)
        ]
    if not feature_items:
        feature_items = feedback_list[: max(3, len(feedback_list) // 4)]
    return feature_items



# --------------------------------------------------------------------------
# Clustering
# --------------------------------------------------------------------------


def _representative_quotes(items: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    seen = set()
    quotes = []
    for item in items:
        quote = (item.get("content") or item.get("title") or "").strip()
        if quote and quote not in seen and len(quotes) < limit:
            seen.add(quote)
            quotes.append(quote[:130] + ("..." if len(quote) > 130 else ""))
    return quotes


def cluster_feature_requests(feedback_list: List[Dict[str, Any]], max_clusters: int = 6) -> List[Dict[str, Any]]:
    """
    Cluster the workspace's feature requests into ranked opportunities.

    Cluster names, keywords and summaries are mined from the feedback itself and the
    priority score is a deterministic blend of volume, requester breadth and rating.
    """
    if not feedback_list:
        return []

    feature_items = _select_feature_items(feedback_list)
    total_items = max(len(feature_items), 1)
    has_customer_identity = workspace_has_customer_identity(feedback_list)

    phrases_per_item, surface_index = build_surface_index(feature_items)
    groups, corpus_freq = group_by_phrases(
        phrases_per_item,
        max_groups=max_clusters,
        max_share=CORPUS_WIDE_PHRASE_SHARE,
    )

    clusters = []
    used_labels: Set[str] = set()
    for seed, members in groups:
        items = [feature_items[index] for index in members]
        count = len(items)

        phrase_freq: Counter = Counter()
        for index in members:
            phrase_freq.update(phrases_per_item[index])

        label = label_group(
            seed,
            phrase_freq,
            corpus_freq,
            total_items,
            surface_index,
            used_labels,
            max_share=CORPUS_WIDE_PHRASE_SHARE,
        )
        used_labels.add(label.lower())
        keywords = group_keywords(
            label, phrase_freq, corpus_freq, surface_index, total_items, max_share=CORPUS_WIDE_PHRASE_SHARE
        )

        ratings = [it.get("rating") for it in items if it.get("rating") is not None]
        avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 4.0
        negative_count = sum(1 for it in items if _resolve_sentiment(it) == "negative")

        unique_requesters = count_unique_requesters(items, has_customer_identity)

        vol_score = min(45.0, (count / total_items) * 100.0 * 1.5)
        breadth_score = min(30.0, (unique_requesters / total_items) * 100.0 * 1.5) if has_customer_identity else 0.0
        rating_score = (avg_rating / 5.0) * 25.0
        priority_score = round(min(98.0, max(20.0, vol_score + breadth_score + rating_score)), 1)

        if priority_score >= 55.0 or count >= 50:
            demand_level = "high"
        elif priority_score >= 32.0 or count >= 10:
            demand_level = "medium"
        else:
            demand_level = "low"

        top_terms = ", ".join(keywords[1:4]) or label.lower()
        summary = (
            f"{count} requests mention {top_terms}, averaging {avg_rating}/5.0 rating"
            f" ({negative_count} negative)."
        )

        clusters.append({
            "id": "",
            "cluster_name": label,
            "summary": summary,
            "request_count": count,
            "unique_customers_count": unique_requesters,
            "demand_level": demand_level,
            "priority_score": priority_score,
            "keywords": keywords,
            "sample_requests": _representative_quotes(items),
            "distinct_sample_quotes": _representative_quotes(items),
            "feedback_ids": [str(it.get("_id", "")) for it in items],
            "score_breakdown": {
                "request_count": count,
                "unique_customers_count": unique_requesters,
                "unique_customers_count_basis": (
                    "unique_customers" if has_customer_identity else "unavailable"
                ),
                "avg_rating": avg_rating,
                "negative_sentiment_count": negative_count,
                "demand_level": demand_level,
                "formula_weights": (
                    "Request Volume (45%) + Unique Customers (30%) + Rating Satisfaction (25%)"
                    if has_customer_identity
                    else "Request Volume (45%) + Rating Satisfaction (25%) — requester breadth is"
                         " excluded because this workspace carries no per-user identity"
                ),
            },
        })

    # Stable ids, as in the pain-point and theme engines: a rank-based id changes on the
    # next analysis and breaks every document and prioritization item that linked to it.
    clusters.sort(key=lambda cluster: cluster["priority_score"], reverse=True)
    clusters = clusters[:max_clusters]
    for rank, cluster in enumerate(clusters, start=1):
        cluster["id"] = stable_topic_id("cluster", cluster.get("cluster_name", ""), cluster.get("keywords"))
        cluster["rank"] = rank
    return clusters
