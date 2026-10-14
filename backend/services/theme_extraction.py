"""
Theme extraction and Customer Pain-Point identification engine.

Themes and pain points are mined from the feedback itself: the recurring phrases users
write are the topics, and each topic's severity/impact is a deterministic function of
the records inside it. Nothing here names a product, a feature or a domain, so the same
engine describes a music app, a bank app or an internal tool without modification.
"""

from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

from services.categorization import detect_sentiment, categorize
from services.preprocessing import normalize, STOPWORDS_SET
from services.text_mining import (
    build_surface_index,
    display_phrase,
    group_by_phrases,
    group_keywords,
    label_group,
    record_text,
    stable_topic_id,
    titleize,
    top_phrases,
)


UNCLASSIFIED_THEME = "Unclassified mentions"

# A topic may describe up to this share of a corpus; beyond that it is the corpus itself.
THEME_MAX_SHARE = 0.6
PAIN_POINT_MAX_SHARE = 0.5


def _resolve_sentiment(item: Dict[str, Any]) -> str:
    s = item.get("sentiment")
    if s:
        return s
    text = f"{item.get('title') or ''} {item.get('content') or ''}".strip()
    return detect_sentiment(text, item.get("rating"))


def _resolve_category(item: Dict[str, Any]) -> str:
    c = item.get("category")
    if c:
        return c
    text = f"{item.get('title') or ''} {item.get('content') or ''}".strip()
    return categorize(text)


def extract_ngrams(tokens: List[str], n: int = 2) -> List[str]:
    """Generate n-grams from a list of tokens."""
    if len(tokens) < n:
        return []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def extract_keywords_and_phrases(texts: List[str], top_k: int = 8) -> List[Tuple[str, int]]:
    """
    Extract most frequent relevant unigrams and bigrams from a list of texts.

    Samples evenly across the corpus (callers pass newest-first feedback, so a head
    slice would describe only the latest records) to keep execution sub-second.
    """
    unigram_counts: Counter = Counter()
    bigram_counts: Counter = Counter()

    if len(texts) > 400:
        stride = len(texts) / 400
        sample_texts = [texts[int(index * stride)] for index in range(400)]
    else:
        sample_texts = texts

    for text in sample_texts:
        tokens = normalize(text)
        filtered_tokens = [t for t in tokens if len(t) > 2 and t not in STOPWORDS_SET]
        unigram_counts.update(filtered_tokens)
        bigram_counts.update(extract_ngrams(filtered_tokens, 2))

    combined = unigram_counts.most_common(top_k) + bigram_counts.most_common(top_k // 2)
    return sorted(combined, key=lambda x: x[1], reverse=True)[:top_k]


def _representative_quotes(items: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    seen = set()
    quotes = []
    for item in items:
        quote = (item.get("content") or item.get("title") or "").strip()
        if quote and quote not in seen and len(quotes) < limit:
            seen.add(quote)
            quotes.append(quote[:130] + ("..." if len(quote) > 130 else ""))
    return quotes


def _group_members(
    items: List[Dict[str, Any]],
    max_groups: int,
    max_share: float,
    min_size: int = 2,
):
    """Mine phrase groups from a record list, with everything needed to describe them."""
    phrases_per_item, surface_index = build_surface_index(items)
    groups, corpus_freq = group_by_phrases(
        phrases_per_item,
        max_groups=max_groups,
        max_share=max_share,
        min_size=min_size,
    )
    return groups, corpus_freq, phrases_per_item, surface_index


def extract_themes_from_feedback(feedback_list: List[Dict[str, Any]], max_themes: int = 8) -> List[Dict[str, Any]]:
    """
    Group all feedback into the topics users actually write about.

    Each theme is a mined phrase; its frequency, sentiment split and keywords are
    computed from the records inside it.
    """
    if not feedback_list:
        return []

    groups, corpus_freq, phrases_per_item, surface_index = _group_members(
        feedback_list, max_groups=max_themes, max_share=THEME_MAX_SHARE
    )

    themes = []
    used_labels: Set[str] = set()
    for seed, members in groups:
        items = [feedback_list[index] for index in members]
        total = len(items)

        phrase_freq: Counter = Counter()
        for index in members:
            phrase_freq.update(phrases_per_item[index])

        title = label_group(
            seed,
            phrase_freq,
            corpus_freq,
            len(feedback_list),
            surface_index,
            used_labels,
            max_share=THEME_MAX_SHARE,
            fallback=UNCLASSIFIED_THEME,
        )
        used_labels.add(title.lower())

        pos = sum(1 for it in items if _resolve_sentiment(it) == "positive")
        neg = sum(1 for it in items if _resolve_sentiment(it) == "negative")
        neu = total - pos - neg
        sentiment_score = round((pos - neg) / total, 2) if total else 0.0

        category_counts = Counter(_resolve_category(it) for it in items)
        dominant_category = category_counts.most_common(1)[0][0] if category_counts else "general_feedback"

        keywords = group_keywords(
            title, phrase_freq, corpus_freq, surface_index, len(feedback_list), max_share=THEME_MAX_SHARE
        )
        match_phrases = [
            phrase for phrase in sorted(phrase_freq, key=lambda p: (-phrase_freq[p], p))
            if phrase_freq[phrase] > 0
        ][:8]

        themes.append({
            "id": f"theme_{len(themes) + 1}",
            "title": title,
            "description": (
                f"Discussed in {total} feedback records ({pos} positive, {neu} neutral, {neg} negative). "
                f"Most of these records are {dominant_category.replace('_', ' ')}."
            ),
            "category": dominant_category,
            "frequency": total,
            "sentiment_breakdown": {"positive": pos, "neutral": neu, "negative": neg},
            "sentiment_score": sentiment_score,
            "keywords": keywords,
            "match_phrases": match_phrases,
            "sample_quotes": _representative_quotes(items),
        })

    themes.sort(key=lambda theme: theme["frequency"], reverse=True)
    for index, theme in enumerate(themes, start=1):
        theme["id"] = f"theme_{index}"
    return themes


def assign_record_theme(text: str, themes: List[Dict[str, Any]]) -> str:
    """
    The theme a single feedback record belongs to, by longest matching mined phrase.

    Records that match no mined phrase are reported honestly as unclassified rather than
    being forced into a bucket that would misstate what they are about.
    """
    lowered = (text or "").lower()
    best_title, best_length = None, 0
    for theme in themes or []:
        for phrase in theme.get("match_phrases") or []:
            if phrase in lowered and len(phrase) > best_length:
                best_title, best_length = theme.get("title", UNCLASSIFIED_THEME), len(phrase)
    return best_title or UNCLASSIFIED_THEME


def _issue_candidates(feedback_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Records that report a problem: negative sentiment, an issue category, or a low rating."""
    candidates = []
    for item in feedback_list:
        sentiment = _resolve_sentiment(item)
        category = _resolve_category(item)
        rating = item.get("rating")
        is_pain = (
            sentiment == "negative"
            or category in ("bug_report", "performance_issue")
            or (rating is not None and rating <= 2)
        )
        if is_pain:
            candidates.append(item)
    return candidates


def measured_group_score(items: List[Dict[str, Any]], total_count: int) -> Dict[str, Any]:
    """
    Score a set of records from measurement alone.

    Volume (35) + rating penalty (25) + negative share (25) + bug share (15), clamped to
    20-98. Shared by the mined pain points and the AI-grounded ones so a model's own
    impact number can never outrank a measured one.
    """
    count = len(items)
    if count == 0:
        return {
            "count": 0,
            "avg_rating": None,
            "negative_count": 0,
            "negative_pct": 0.0,
            "bug_count": 0,
            "impact_score": 20.0,
            "severity": "low",
        }

    safe_total = max(int(total_count), 1)
    ratings = [item.get("rating") for item in items if item.get("rating") is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 2.0
    negative_count = sum(1 for item in items if _resolve_sentiment(item) == "negative")
    negative_pct = round((negative_count / count) * 100, 1)
    bug_count = sum(1 for item in items if _resolve_category(item) in ("bug_report", "performance_issue"))

    vol_factor = min(35.0, (count / safe_total) * 100.0 * 2.0)
    rating_penalty = max(0.0, (5.0 - avg_rating) * 5.0)
    neg_factor = (negative_count / count) * 25.0
    bug_factor = (bug_count / count) * 15.0
    impact_score = round(min(98.0, max(20.0, vol_factor + rating_penalty + neg_factor + bug_factor)), 1)

    if impact_score >= 60.0 or count >= 10 or (avg_rating <= 1.5 and negative_count > 5):
        severity = "high"
    elif impact_score >= 40.0 or count >= 3:
        severity = "medium"
    else:
        severity = "low"

    return {
        "count": count,
        "avg_rating": avg_rating,
        "negative_count": negative_count,
        "negative_pct": negative_pct,
        "bug_count": bug_count,
        "impact_score": impact_score,
        "severity": severity,
    }


def extract_pain_points_from_feedback(
    feedback_list: List[Dict[str, Any]],
    max_pain_points: int = 10,
) -> List[Dict[str, Any]]:
    """
    Identify and score customer pain points from the complaints themselves.

    Each pain point is a mined phrase from the complaint set; its impact score is a
    deterministic function of volume, rating, negative sentiment and bug ratio.
    """
    if not feedback_list:
        return []

    issue_candidates = _issue_candidates(feedback_list)
    if not issue_candidates:
        return []

    total_count = max(len(feedback_list), 1)
    groups, corpus_freq, phrases_per_item, surface_index = _group_members(
        issue_candidates,
        max_groups=max_pain_points,
        max_share=PAIN_POINT_MAX_SHARE,
        min_size=1,
    )

    pain_points = []
    used_labels: Set[str] = set()
    for seed, members in groups:
        items = [issue_candidates[index] for index in members]
        count = len(items)
        if count == 0:
            continue

        phrase_freq: Counter = Counter()
        for index in members:
            phrase_freq.update(phrases_per_item[index])

        title = label_group(
            seed,
            phrase_freq,
            corpus_freq,
            len(issue_candidates),
            surface_index,
            used_labels,
            max_share=PAIN_POINT_MAX_SHARE,
            fallback="Unclassified complaints",
        )
        used_labels.add(title.lower())

        measured = measured_group_score(items, total_count)
        avg_rating = measured["avg_rating"]
        neg_count = measured["negative_count"]
        negative_pct = measured["negative_pct"]
        bug_count = measured["bug_count"]
        impact_score = measured["impact_score"]
        severity = measured["severity"]

        terms = ", ".join(group_keywords(
            title, phrase_freq, corpus_freq, surface_index, len(issue_candidates), max_share=PAIN_POINT_MAX_SHARE
        )[1:4]) or title.lower()

        pain_points.append({
            "id": "",
            "title": title,
            "description": (
                f"{count} complaints mention {terms} (avg rating {avg_rating}/5.0, "
                f"{neg_count} negative, {bug_count} bug or performance reports)."
            ),
            "severity": severity,
            "impact_score": impact_score,
            "affected_users_count": count,
            "category": _dominant_category(items),
            "recommended_action": (
                f"Review the {count} reports mentioning {terms} and re-run this analysis after the "
                f"change to confirm the negative share ({negative_pct}%) falls."
            ),
            "keywords": group_keywords(
                title, phrase_freq, corpus_freq, surface_index, len(issue_candidates), max_share=PAIN_POINT_MAX_SHARE
            ),
            "match_phrases": [
                phrase for phrase in sorted(phrase_freq, key=lambda p: (-phrase_freq[p], p))
                if phrase_freq[phrase] > 0
            ][:8],
            "sample_quotes": _representative_quotes(items),
            "distinct_sample_quotes": _representative_quotes(items),
            "score_breakdown": {
                "frequency": count,
                "negative_sentiment_pct": negative_pct,
                "avg_rating": avg_rating,
                "bug_count": bug_count,
                "severity_level": severity,
                "formula_weights": "Volume (35%) + Low Rating (25%) + Negative % (25%) + Bug Ratio (15%)",
            },
        })

    # Ids are derived from the topic itself, not its rank. A rank-based id is renumbered
    # on every re-analysis, which silently repoints every PRD, user story, prioritization
    # item and roadmap entry that referenced it. `rank` still carries the ordering.
    pain_points.sort(key=lambda x: x["impact_score"], reverse=True)
    pain_points = pain_points[:max_pain_points]
    for rank, pain_point in enumerate(pain_points, start=1):
        pain_point["id"] = stable_topic_id("pain_point", pain_point.get("title", ""), pain_point.get("keywords"))
        pain_point["rank"] = rank
    return pain_points


def _dominant_category(items: List[Dict[str, Any]]) -> str:
    counts = Counter(_resolve_category(it) for it in items)
    return counts.most_common(1)[0][0] if counts else "general_feedback"
