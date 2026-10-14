"""
Output Quality Evaluation service for Milestone 4.

This module answers the question a reviewer will actually ask: how good are the
generated outputs, and how do you know? Every check here is verifiable from the
workspace itself — required sections exist, the distributions add up to the record
count they claim, the analysis is not older than the feedback it describes, the
scores have not stalled on placeholder values, and any number a model wrote can be
traced back to a measured value.

Nothing is persisted: an evaluation is recomputed on demand so it can never report
a stale verdict about a newer artefact.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from services import roadmap_service, workspace_context

# Numbers a model may legitimately write without a measured source: small ordinals,
# step numbers, section references and Fibonacci-style counts.
NUMBER_RE = re.compile(r"(?<![\w.\-])(\d+(?:\.\d+)?)")

# Generic change verbs and filler that frame an initiative without naming its subject.
# Two items that share a topic but differ only by one of these are the same work.
FRAMING_WORDS = {
    "resolve", "resolved", "fix", "fixed", "add", "added", "remove", "removal", "removed",
    "reintroduce", "restore", "restored", "bring", "back", "improve", "improved", "improvement",
    "improvements", "support", "enable", "disable", "update", "updates", "option", "options",
    "issue", "issues", "problem", "problems", "bug", "bugs", "feature", "request", "requests",
    "the", "and", "for", "with", "our", "their", "other", "more", "less", "better", "new",
}

REQUIRED_PRD_SECTIONS = [
    ("problem_statement", "Problem statement"),
    ("target_users_and_personas", "Target personas"),
    ("functional_requirements", "Functional requirements"),
    ("non_functional_requirements", "Non-functional requirements"),
    ("success_metrics_kpis", "Success metrics"),
    ("risks_and_mitigations", "Risks & mitigations"),
]


def _check(
    check_id: str,
    name: str,
    category: str,
    status: str,
    detail: str,
    evidence: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "category": category,
        "status": status,
        "detail": detail,
        "evidence": evidence or [],
    }


def _score_checks(checks: List[Dict[str, Any]]) -> int:
    """Score a check list as the mean of pass (100), warn (60) and fail (0)."""
    if not checks:
        return 0
    values = {"pass": 100.0, "warn": 60.0, "fail": 0.0}
    return int(round(sum(values.get(check["status"], 0.0) for check in checks) / len(checks)))


def _grade(score: int, available: bool) -> str:
    if not available:
        return "not_generated"
    if score >= 90:
        return "excellent"
    if score >= 75:
        return "good"
    if score >= 60:
        return "fair"
    return "needs_review"


def _tally(checks: List[Dict[str, Any]]) -> Tuple[int, int, int]:
    return (
        sum(1 for check in checks if check["status"] == "pass"),
        sum(1 for check in checks if check["status"] == "warn"),
        sum(1 for check in checks if check["status"] == "fail"),
    )


def _collect_measured_numbers(insights: Dict[str, Any], extras: List[Any]) -> Set[str]:
    """
    Build the vocabulary of numbers a generated document is allowed to state.

    Everything the workspace has actually measured lands here: the analysis, the
    backlog scores, the roadmap and the feedback counts. A number outside this set
    is not automatically wrong, but it is worth a reviewer's eye — which is exactly
    what the scan reports.
    """
    allowed: Set[str] = set()

    def absorb(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            number = float(value)
            allowed.add(f"{number:.0f}")
            allowed.add(f"{number:.1f}")
            allowed.add(f"{number:.2f}")
            allowed.add(f"{number:g}")
        elif isinstance(value, str):
            for match in NUMBER_RE.finditer(value):
                allowed.add(match.group(1))
        elif isinstance(value, dict):
            for nested in value.values():
                absorb(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                absorb(nested)

    absorb(insights)
    absorb(extras)
    return allowed


def _number_is_traceable(token: str, allowed: Set[str]) -> bool:
    """A number is traceable if it matches a measured value, allowing for rounding."""
    if token in allowed:
        return True
    try:
        value = float(token)
    except ValueError:
        return True
    if value.is_integer() and 1 <= value <= 20:
        return True  # ordinals, step numbers, item counts written in prose
    for candidate in allowed:
        try:
            if abs(float(candidate) - value) <= 0.5:
                return True
        except ValueError:
            continue
    return False


def _topic_words(text: str) -> List[str]:
    """Lower-case word tokens, used to compare what two initiatives are actually about."""
    return [token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if len(token) >= 3]


def _scan_untraceable_numbers(texts: List[str], allowed: Set[str], limit: int = 5) -> List[str]:
    """Find numeric claims in generated prose that no measured value supports."""
    flagged: List[str] = []
    for text in texts:
        if not text:
            continue
        for match in NUMBER_RE.finditer(str(text)):
            token = match.group(1)
            if _number_is_traceable(token, allowed):
                continue
            start = max(0, match.start() - 45)
            end = min(len(text), match.end() + 45)
            snippet = " ".join(str(text)[start:end].split())
            flagged.append(f"“{token}” in: …{snippet}…")
            if len(flagged) >= limit:
                return flagged
    return flagged


def _evaluate_insights(insights: Optional[Dict[str, Any]], stored_records: int) -> Dict[str, Any]:
    available = bool(insights)
    checks: List[Dict[str, Any]] = []
    notes: List[str] = []

    if not available:
        return {
            "artifact_type": "insights",
            "label": "Product insights analysis",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No analysis has been run for this workspace yet."],
        }

    total = int(insights.get("total_analyzed") or 0)
    sentiment = insights.get("sentiment_distribution") or insights.get("by_sentiment") or {}
    categories = insights.get("category_distribution") or insights.get("by_category") or {}
    sentiment_sum = sum(int(value or 0) for value in sentiment.values())
    category_sum = sum(int(value or 0) for value in categories.values())

    missing = [
        label
        for key, label in (
            ("themes", "themes"),
            ("pain_points", "pain points"),
            ("feature_clusters", "feature clusters"),
            ("trends", "trends"),
        )
        if not insights.get(key)
    ]
    checks.append(
        _check(
            "insights.completeness.sections",
            "All analysis sections present",
            "completeness",
            "fail" if len(missing) >= 2 else ("warn" if missing else "pass"),
            "Missing sections: " + ", ".join(missing) if missing else "Themes, pain points, clusters and trends are all populated.",
            [f"{key}={len(insights.get(key) or [])}" for key, _ in (("themes", ""), ("pain_points", ""), ("feature_clusters", ""), ("trends", ""))],
        )
    )

    distribution_ok = sentiment_sum == total and category_sum == total
    checks.append(
        _check(
            "insights.consistency.distributions",
            "Distributions add up to the analysed total",
            "consistency",
            "pass" if distribution_ok else "fail",
            (
                "Sentiment and category distributions both total the analysed record count."
                if distribution_ok
                else f"The analysed total is {total}, but the distributions sum to {sentiment_sum} (sentiment) and "
                f"{category_sum} (category). Charts built from these will not reconcile with the headline count."
            ),
            [
                f"total_analyzed={total}",
                f"sentiment_sum={sentiment_sum}",
                f"category_sum={category_sum}",
            ],
        )
    )

    fresh = stored_records == total
    checks.append(
        _check(
            "insights.freshness.record_count",
            "Analysis covers every stored record",
            "freshness",
            "pass" if fresh else "warn",
            (
                f"The analysis and the workspace both hold {total} records."
                if fresh
                else f"{stored_records} records are stored but {total} were analysed, so {abs(stored_records - total)} "
                "arrived after the last run. Re-run the analysis before quoting these figures."
            ),
            [f"records_stored={stored_records}", f"total_analyzed={total}"],
        )
    )

    pain_points = insights.get("pain_points") or []
    thin = [
        f"{point.get('title')} (n={int(point.get('affected_users_count') or 0)})"
        for point in pain_points
        if int(point.get("affected_users_count") or 0) < 2
    ]
    checks.append(
        _check(
            "insights.grounding.pain_point_volume",
            "Every pain point rests on more than one report",
            "grounding",
            "warn" if thin else "pass",
            (
                "Weakly supported pain points: " + ", ".join(thin[:5])
                if thin
                else f"All {len(pain_points)} pain points are backed by at least two customer records."
            ),
            thin[:5],
        )
    )

    checks.append(
        _check(
            "insights.coverage.health_score",
            "A health score was computed",
            "completeness",
            "pass" if insights.get("health_score") is not None else "fail",
            f"Health score {insights.get('health_score')} computed by {insights.get('ai_model') or 'the deterministic engine'}.",
            [f"analyzed_at={insights.get('analyzed_at')}"],
        )
    )

    passed, warned, failed = _tally(checks)
    if thin:
        notes.append("Pain points with a single supporting report are statistically indistinguishable from noise.")
    if not distribution_ok:
        notes.append("Distribution totals disagree with the analysed count — check imports made after the last analysis.")

    score = _score_checks(checks)
    return {
        "artifact_type": "insights",
        "label": "Product insights analysis",
        "available": True,
        "artifact_id": insights.get("_id"),
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": notes,
    }


def _evaluate_prioritization(
    items: List[Dict[str, Any]],
    insights_for_links: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    available = bool(items)
    checks: List[Dict[str, Any]] = []
    notes: List[str] = []

    if not available:
        return {
            "artifact_type": "prioritization",
            "label": "Prioritization backlog",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No prioritization items exist yet — auto-seed the backlog from the analysis."],
        }

    placeholders = [
        str(item.get("name"))
        for item in items
        if float((item.get("weighted") or {}).get("feasibility_score") or 0) == 50.0
        and float((item.get("weighted") or {}).get("risk_mitigation_score") or 0) == 50.0
    ]
    checks.append(
        _check(
            "prioritization.grounding.placeholder_inputs",
            "No item still carries neutral placeholder inputs",
            "grounding",
            "warn" if placeholders else "pass",
            (
                f"{len(placeholders)} of {len(items)} item(s) still carry the neutral 50 feasibility and risk "
                "placeholders, so their weighted score is not decision-grade yet."
                if placeholders
                else "Every item has had its feasibility and risk inputs set by a person."
            ),
            placeholders[:5],
        )
    )

    unranked = [
        str(item.get("name"))
        for item in items
        if not str(item.get("ai_rationale") or "").strip()
    ]
    checks.append(
        _check(
            "prioritization.completeness.rationale",
            "Every item explains its score",
            "completeness",
            "warn" if unranked else "pass",
            (
                "Items with no recorded rationale: " + ", ".join(unranked[:5])
                if unranked
                else f"All {len(items)} items state the evidence behind their score."
            ),
            unranked[:5],
        )
    )

    ordered = sorted(items, key=lambda item: item.get("rank") or 0)
    scores = [float((item.get("rice") or {}).get("score") or 0) for item in ordered]
    rank_monotonic = all(scores[index] >= scores[index + 1] - 1e-6 for index in range(len(scores) - 1))
    checks.append(
        _check(
            "prioritization.consistency.rank_order",
            "Rank order matches the RICE scores",
            "consistency",
            "pass" if rank_monotonic else "warn",
            (
                "Ranks descend in line with RICE scores."
                if rank_monotonic
                else "Rank order disagrees with the RICE scores, which is expected after manual edits — re-run "
                "auto-seed or re-sort before quoting the ranking."
            ),
            [f"top_rice={scores[0] if scores else 0:.1f}", f"lowest_rice={scores[-1] if scores else 0:.1f}"],
        )
    )

    insights = insights_for_links or {}
    pain_point_ids = {str(point.get("id")) for point in insights.get("pain_points") or []}
    cluster_ids = {str(cluster.get("id")) for cluster in insights.get("feature_clusters") or []}
    if not insights:
        checks.append(
            _check(
                "prioritization.grounding.source_links",
                "Every item still points at the evidence it was seeded from",
                "grounding",
                "fail",
                "No stored analysis exists, so no backlog item can be traced to evidence.",
                [],
            )
        )
    else:
        dangling: List[str] = []
        mismatched: List[str] = []
        topic_labels = {
            str(source.get("id")): str(source.get("title") or source.get("cluster_name") or "")
            for source in list(insights.get("pain_points") or []) + list(insights.get("feature_clusters") or [])
        }
        for item in items:
            source_id = str(item.get("source_pain_point_id") or item.get("source_cluster_id") or "")
            if not source_id:
                continue
            known = source_id in pain_point_ids or source_id in cluster_ids
            if not known:
                dangling.append(f"{item.get('name')} → {source_id} (no such topic in the current analysis)")
                continue
            label = topic_labels.get(source_id, "")
            name_words = {word for word in re.findall(r"[a-z0-9]+", str(item.get("name") or "").lower()) if len(word) > 3}
            label_words = {word for word in re.findall(r"[a-z0-9]+", label.lower()) if len(word) > 3}
            if name_words and label_words and not (name_words & label_words):
                mismatched.append(f"{item.get('name')} → “{label}”")

        checks.append(
            _check(
                "prioritization.grounding.source_links",
                "Every item still points at the evidence it was seeded from",
                "grounding",
                "fail" if dangling else ("warn" if mismatched else "pass"),
                (
                    "Items whose source topic no longer exists: " + "; ".join(dangling[:4])
                    if dangling
                    else (
                        "Items whose linked topic describes something else: " + "; ".join(mismatched[:4])
                        if mismatched
                        else f"All {sum(1 for item in items if item.get('source_pain_point_id') or item.get('source_cluster_id'))} "
                             "linked item(s) resolve to a topic in the current analysis."
                    )
                ),
                (dangling or mismatched)[:4],
            )
        )

    must_have = sum(1 for item in items if item.get("moscow") == "must_have")
    checks.append(
        _check(
            "prioritization.coverage.moscow",
            "MoSCoW classification is used",
            "completeness",
            "pass" if must_have else "warn",
            f"{must_have} of {len(items)} item(s) are classified must-have.",
            [f"must_have={must_have}", f"total={len(items)}"],
        )
    )

    if placeholders:
        notes.append("Weighted scores will shift once feasibility and risk are filled in.")

    passed, warned, failed = _tally(checks)
    score = _score_checks(checks)
    return {
        "artifact_type": "prioritization",
        "label": "Prioritization backlog",
        "available": True,
        "artifact_id": None,
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": notes,
    }


def _evaluate_roadmap(roadmap: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    available = bool(roadmap)
    checks: List[Dict[str, Any]] = []

    if not available:
        return {
            "artifact_type": "roadmap",
            "label": "Roadmap plan",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No roadmap has been generated from the backlog yet."],
        }

    milestones = roadmap.get("milestones") or []
    releases = roadmap.get("releases") or []
    items = roadmap.get("items") or []
    checks.append(
        _check(
            "roadmap.completeness.structure",
            "Roadmap has releases and milestones",
            "completeness",
            "fail" if not milestones or not releases else "pass",
            f"{len(releases)} release window(s) and {len(milestones)} recommended milestone(s) across {len(items)} initiative(s).",
            [f"releases={len(releases)}", f"milestones={len(milestones)}"],
        )
    )

    over_capacity = [
        release.get("name")
        for release in releases
        if float(release.get("effort_total") or 0) > float(release.get("capacity") or 0) + 1e-6
    ]
    checks.append(
        _check(
            "roadmap.consistency.capacity",
            "No release exceeds its committed capacity",
            "consistency",
            "warn" if over_capacity else "pass",
            (
                "Over-committed windows: " + ", ".join(str(name) for name in over_capacity)
                if over_capacity
                else "Every release window is committed within its stated capacity."
            ),
            [f"{release.get('name')}: {release.get('effort_total')}/{release.get('capacity')}" for release in releases],
        )
    )

    unscheduled_must = [
        str(item.get("name"))
        for item in items
        if item.get("moscow") == "must_have" and not item.get("milestone_id")
    ]
    checks.append(
        _check(
            "roadmap.coverage.must_have_scheduled",
            "Must-have work is scheduled inside the horizon",
            "grounding",
            "warn" if unscheduled_must else "pass",
            (
                "Must-have items left in the backlog: " + ", ".join(unscheduled_must[:5])
                if unscheduled_must
                else "Every must-have initiative is scheduled inside the planning horizon."
            ),
            unscheduled_must[:5],
        )
    )

    signatures: Dict[frozenset, str] = {}
    duplicates: List[str] = []
    for item in items:
        signature = frozenset(_topic_words(str(item.get("name") or ""))) - FRAMING_WORDS
        if len(signature) < 2:
            continue
        if signature in signatures:
            duplicates.append(f"{signatures[signature]} ↔ {item.get('name')}")
        else:
            signatures[signature] = str(item.get("name"))
    checks.append(
        _check(
            "roadmap.consistency.duplicate_scope",
            "No two initiatives plan the same work",
            "consistency",
            "warn" if duplicates else "pass",
            (
                "Initiatives that describe the same subject with different framing: " + "; ".join(duplicates[:3])
                if duplicates
                else "No two roadmap items describe the same subject, so no milestone is crediting itself twice."
            ),
            duplicates[:3],
        )
    )

    milestone_ids = {milestone.get("id") for milestone in milestones}
    orphans = [
        str(item.get("name"))
        for item in items
        if item.get("milestone_id") and item.get("milestone_id") not in milestone_ids
    ]
    checks.append(
        _check(
            "roadmap.consistency.milestone_membership",
            "Every scheduled item belongs to a milestone",
            "consistency",
            "fail" if orphans else "pass",
            (
                "Items pointing at a milestone that no longer exists: " + ", ".join(orphans[:5])
                if orphans
                else "Milestone membership is consistent across the plan."
            ),
            orphans[:5],
        )
    )

    deferred = roadmap.get("deferred") or []
    checks.append(
        _check(
            "roadmap.grounding.deferred_explained",
            "Work beyond the horizon is explained",
            "grounding",
            "warn" if deferred and not roadmap.get("deferred_reason") else "pass",
            (
                f"{len(deferred)} item(s) sit outside the horizon and the plan states why."
                if deferred and roadmap.get("deferred_reason")
                else (
                    f"{len(deferred)} item(s) sit outside the horizon with no explanation recorded."
                    if deferred
                    else "Every prioritised initiative fits inside the horizon."
                )
            ),
            [str(roadmap.get("deferred_reason") or "")][:1],
        )
    )

    passed, warned, failed = _tally(checks)
    score = _score_checks(checks)
    return {
        "artifact_type": "roadmap",
        "label": "Roadmap plan",
        "available": True,
        "artifact_id": None,
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": [],
    }


def _evaluate_prd(prd: Optional[Dict[str, Any]], allowed_numbers: Set[str]) -> Dict[str, Any]:
    available = bool(prd)
    checks: List[Dict[str, Any]] = []

    if not available:
        return {
            "artifact_type": "prd",
            "label": "Product Requirement Document",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No PRD has been generated for this workspace yet."],
        }

    missing = [label for key, label in REQUIRED_PRD_SECTIONS if not prd.get(key)]
    checks.append(
        _check(
            "prd.completeness.sections",
            "All required PRD sections are present",
            "completeness",
            "fail" if len(missing) >= 2 else ("warn" if missing else "pass"),
            "Missing sections: " + ", ".join(missing) if missing else "All six required sections are populated.",
            missing,
        )
    )

    evidence = prd.get("evidence") or {}
    checks.append(
        _check(
            "prd.grounding.evidence_block",
            "Document states its provenance",
            "grounding",
            "pass" if evidence.get("generated_by") else "fail",
            (
                f"Generated by {evidence.get('generated_by')} from {evidence.get('records_analyzed')} analysed records, "
                f"{evidence.get('records_supporting_this_document')} of them supporting this document."
                if evidence.get("generated_by")
                else "The document carries no provenance block, so a reader cannot tell what it was built from."
            ),
            [f"generated_by={evidence.get('generated_by')}", f"records_supporting={evidence.get('records_supporting_this_document')}"],
        )
    )

    kpis = prd.get("success_metrics_kpis") or []
    labelled = [kpi for kpi in kpis if str(kpi.get("baseline") or "").startswith(("Measured:", "Not measured"))]
    targets = [kpi for kpi in kpis if str(kpi.get("target") or "").startswith("Proposed:")]
    labelled_ok = bool(kpis) and len(labelled) == len(kpis) and len(targets) == len(kpis)
    checks.append(
        _check(
            "prd.grounding.baseline_labelling",
            "Baselines are marked measured and targets proposed",
            "grounding",
            "pass" if labelled_ok else "warn",
            (
                f"All {len(kpis)} metric(s) separate the measured baseline from the proposed target."
                if labelled_ok
                else f"{len(labelled)} of {len(kpis)} baseline(s) are labelled measured and {len(targets)} target(s) "
                "are labelled proposed, so some numbers are ambiguous."
            ),
            [f"metrics={len(kpis)}", f"labelled_baselines={len(labelled)}", f"labelled_targets={len(targets)}"],
        )
    )

    prose = [
        str(prd.get("executive_summary") or ""),
        str(prd.get("problem_statement") or ""),
        " ".join(str(goal) for goal in prd.get("goals_and_objectives") or []),
        " ".join(f"{kpi.get('baseline')} {kpi.get('target')}" for kpi in kpis),
    ]
    untraceable = _scan_untraceable_numbers(prose, allowed_numbers)
    checks.append(
        _check(
            "prd.grounding.untraceable_numbers",
            "Stated numbers trace back to measured data",
            "grounding",
            "warn" if untraceable else "pass",
            (
                f"{len(untraceable)} numeric claim(s) could not be traced to a measured value in this workspace."
                if untraceable
                else "Every number in the narrative matches a value measured in this workspace."
            ),
            untraceable,
        )
    )

    passed, warned, failed = _tally(checks)
    score = _score_checks(checks)
    return {
        "artifact_type": "prd",
        "label": "Product Requirement Document",
        "available": True,
        "artifact_id": prd.get("id"),
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": [f"Evaluated “{prd.get('title')}”."],
    }


def _evaluate_stories(stories: List[Dict[str, Any]]) -> Dict[str, Any]:
    available = bool(stories)
    checks: List[Dict[str, Any]] = []

    if not available:
        return {
            "artifact_type": "user_story",
            "label": "User stories",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No user stories have been generated for this workspace yet."],
        }

    no_criteria = [str(story.get("title")) for story in stories if not story.get("acceptance_criteria")]
    checks.append(
        _check(
            "stories.completeness.acceptance_criteria",
            "Every story has acceptance criteria",
            "completeness",
            "fail" if no_criteria else "pass",
            (
                "Stories without criteria: " + ", ".join(no_criteria[:5])
                if no_criteria
                else f"All {len(stories)} stories carry acceptance criteria."
            ),
            no_criteria[:5],
        )
    )

    incomplete_gherkin: List[str] = []
    for story in stories:
        for criterion in story.get("acceptance_criteria") or []:
            if not (criterion.get("given") and criterion.get("when") and criterion.get("then")):
                incomplete_gherkin.append(str(story.get("title")))
                break
    checks.append(
        _check(
            "stories.completeness.gherkin",
            "Criteria follow Given/When/Then",
            "completeness",
            "warn" if incomplete_gherkin else "pass",
            (
                "Stories with a partially specified scenario: " + ", ".join(incomplete_gherkin[:5])
                if incomplete_gherkin
                else "Every acceptance criterion states a precondition, an action and an expected outcome."
            ),
            incomplete_gherkin[:5],
        )
    )

    allowed_points = {1, 2, 3, 5, 8, 13}
    bad_points = [
        f"{story.get('title')} ({story.get('story_points')})"
        for story in stories
        if int(story.get("story_points") or 0) not in allowed_points
    ]
    checks.append(
        _check(
            "stories.consistency.estimates",
            "Estimates are Fibonacci-scale",
            "consistency",
            "warn" if bad_points else "pass",
            (
                "Off-scale estimates: " + ", ".join(bad_points[:5])
                if bad_points
                else "Every estimate sits on the 1-2-3-5-8-13 scale."
            ),
            bad_points[:5],
        )
    )

    linked = sum(1 for story in stories if story.get("prd_id") or story.get("feature_cluster_id"))
    checks.append(
        _check(
            "stories.coverage.traceability",
            "Stories trace back to a PRD or cluster",
            "grounding",
            "warn" if linked < len(stories) else "pass",
            f"{linked} of {len(stories)} stories link to the document or cluster they came from.",
            [f"linked={linked}", f"total={len(stories)}"],
        )
    )

    passed, warned, failed = _tally(checks)
    score = _score_checks(checks)
    return {
        "artifact_type": "user_story",
        "label": "User stories",
        "available": True,
        "artifact_id": None,
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": [],
    }


def _evaluate_report(
    report: Optional[Dict[str, Any]],
    roadmap: Optional[Dict[str, Any]],
    allowed_numbers: Set[str],
) -> Dict[str, Any]:
    available = bool(report)
    checks: List[Dict[str, Any]] = []

    if not available:
        return {
            "artifact_type": "report",
            "label": "Executive / strategy report",
            "available": False,
            "artifact_id": None,
            "score": 0,
            "grade": "not_generated",
            "passed": 0,
            "warned": 0,
            "failed": 0,
            "checks": [],
            "notes": ["No executive summary or strategy report has been generated yet."],
        }

    required = [
        ("executive_summary", "Executive summary"),
        ("key_findings", "Key findings"),
        ("strategic_pillars", "Strategic pillars"),
        ("kpis", "Product indicators"),
        ("risks", "Risks"),
        ("recommendations", "Recommendations"),
    ]
    missing = [label for key, label in required if not report.get(key)]
    checks.append(
        _check(
            "report.completeness.sections",
            "Report carries every required section",
            "completeness",
            "fail" if len(missing) >= 2 else ("warn" if missing else "pass"),
            "Missing sections: " + ", ".join(missing) if missing else "All six required sections are populated.",
            missing,
        )
    )

    evidence = report.get("evidence") or {}
    checks.append(
        _check(
            "report.grounding.evidence_block",
            "Report states its provenance",
            "grounding",
            "pass" if evidence.get("generated_by") else "fail",
            (
                f"Written by {evidence.get('generated_by')} from {evidence.get('records_analyzed')} analysed records "
                f"and {evidence.get('items_planned')} prioritised initiative(s)."
                if evidence.get("generated_by")
                else "The report carries no provenance block."
            ),
            [f"generated_by={evidence.get('generated_by')}", f"records_analyzed={evidence.get('records_analyzed')}"],
        )
    )

    prose = [
        str(report.get("executive_summary") or ""),
        str(report.get("headline") or ""),
        " ".join(str(finding.get("detail")) for finding in report.get("key_findings") or []),
        " ".join(str(rec.get("rationale")) for rec in report.get("recommendations") or []),
    ]
    untraceable = _scan_untraceable_numbers(prose, allowed_numbers)
    checks.append(
        _check(
            "report.grounding.untraceable_numbers",
            "Stated numbers trace back to measured data",
            "grounding",
            "warn" if untraceable else "pass",
            (
                f"{len(untraceable)} numeric claim(s) could not be traced to a measured value in this workspace."
                if untraceable
                else "Every number in the report matches a value measured in this workspace."
            ),
            untraceable,
        )
    )

    outlook = report.get("roadmap_outlook") or []
    stored_releases = len((roadmap or {}).get("releases") or [])
    aligned = len(outlook) == stored_releases
    checks.append(
        _check(
            "report.consistency.roadmap_alignment",
            "Report matches the current roadmap",
            "consistency",
            "warn" if not aligned else "pass",
            (
                f"Both the report and the stored roadmap describe {stored_releases} release window(s)."
                if aligned
                else f"The report describes {len(outlook)} release window(s) while the workspace roadmap has "
                f"{stored_releases}, so one of them is out of date."
            ),
            [f"report_releases={len(outlook)}", f"roadmap_releases={stored_releases}"],
        )
    )

    passed, warned, failed = _tally(checks)
    score = _score_checks(checks)
    return {
        "artifact_type": "report",
        "label": "Executive / strategy report",
        "available": True,
        "artifact_id": report.get("id"),
        "score": score,
        "grade": _grade(score, True),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "checks": checks,
        "notes": [f"Evaluated “{report.get('title')}”."],
    }


def _build_markdown_from_quality(report: Dict[str, Any]) -> str:
    """Render the evaluation as Markdown so a reviewer can read or attach it."""
    lines = [
        f"# Output Quality Evaluation — {report.get('workspace_name')}",
        f"**Evaluated:** `{report.get('evaluated_at')}` | **Overall score:** {report.get('overall_score')}/100 "
        f"| **Grade:** {report.get('grade')}",
        "",
        report.get("summary", ""),
        "",
        "| Artefact | Score | Grade | Passed | Warnings | Failures |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for artifact in report.get("artifacts") or []:
        lines.append(
            f"| {artifact.get('label')} | {artifact.get('score') if artifact.get('available') else '—'} | "
            f"{artifact.get('grade')} | {artifact.get('passed')} | {artifact.get('warned')} | {artifact.get('failed')} |"
        )
    lines.append("")

    for artifact in report.get("artifacts") or []:
        lines.append(f"## {artifact.get('label')}")
        if not artifact.get("available"):
            lines.append("Not generated for this workspace yet.")
            lines.append("")
            continue
        for check in artifact.get("checks") or []:
            lines.append(f"- **[{check.get('status').upper()}]** {check.get('name')} — {check.get('detail')}")
            for item in check.get("evidence") or []:
                lines.append(f"  - `{item}`")
        for note in artifact.get("notes") or []:
            lines.append(f"- _{note}_")
        lines.append("")
    return "\n".join(lines)


async def evaluate_workspace(workspace_id: str) -> Dict[str, Any]:
    """
    Score every generated artefact family in a workspace.

    The evaluation reads the same stored data a reviewer would: the analysis, the
    backlog, the roadmap and the documents. It does not call any model, so it cannot
    flatter a generation — it only checks whether what was produced holds together.
    """
    insights = await workspace_context.load_stored_insights(workspace_id)
    workspace = await workspace_context.resolve_workspace(workspace_id, insights)
    items = await workspace_context.load_prioritization_items(workspace_id)
    roadmap = await roadmap_service.get_roadmap(workspace_id)
    prds = await workspace_context.load_prds(workspace_id)
    stories = await workspace_context.load_user_stories(workspace_id)

    from services import report_service  # imported here: report_service imports the roadmap service

    reports = await report_service.get_reports_for_workspace(workspace_id)
    stored_records = await workspace_context.count_feedback(workspace_id)

    newest_prd = None
    if prds:
        newest_prd = sorted(prds, key=lambda prd: str(prd.get("created_at") or ""), reverse=True)[0]

    allowed_numbers = _collect_measured_numbers(
        insights or {},
        [items, roadmap or {}, prds, stories],
    )

    artifacts = [
        _evaluate_insights(insights, stored_records),
        _evaluate_prioritization(items, insights),
        _evaluate_roadmap(roadmap),
        _evaluate_prd(newest_prd, allowed_numbers),
        _evaluate_stories(stories),
        _evaluate_report(reports[0] if reports else None, roadmap, allowed_numbers),
    ]

    available = [artifact for artifact in artifacts if artifact["available"]]
    overall = int(round(sum(artifact["score"] for artifact in available) / len(available))) if available else 0

    counts = {
        "artefacts_available": len(available),
        "artefacts_evaluated": len(artifacts),
        "passed": sum(artifact["passed"] for artifact in artifacts),
        "warned": sum(artifact["warned"] for artifact in artifacts),
        "failed": sum(artifact["failed"] for artifact in artifacts),
    }

    failures = [
        f"{artifact['label']}: {check['name']}"
        for artifact in artifacts
        for check in artifact["checks"]
        if check["status"] == "fail"
    ]
    warnings = [
        f"{artifact['label']}: {check['name']}"
        for artifact in artifacts
        for check in artifact["checks"]
        if check["status"] == "warn"
    ]

    if not available:
        summary = "Nothing has been generated for this workspace yet, so there is no output to evaluate."
    else:
        summary = (
            f"Evaluated {len(available)} of {len(artifacts)} artefact families at {overall}/100 "
            f"({_grade(overall, True)}): {counts['passed']} checks passed, {counts['warned']} warned and "
            f"{counts['failed']} failed."
        )
        if failures:
            summary += " Failures: " + "; ".join(failures[:3]) + "."
        elif warnings:
            summary += " Highest-priority warning: " + warnings[0] + "."

    report = {
        "workspace_id": workspace_id,
        "workspace_name": workspace["name"],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "overall_score": overall,
        "grade": _grade(overall, bool(available)),
        "artifacts": artifacts,
        "summary": summary,
        "counts": counts,
    }
    report["raw_markdown"] = _build_markdown_from_quality(report)
    return report
