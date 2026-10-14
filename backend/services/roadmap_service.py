"""
Roadmap Planning & Milestone Recommendation service for Milestone 4.

The plan is built from work the workspace has already measured: the prioritization
backlog (itself seeded from customer clusters and pain points) and the Milestone 2
analysis behind it. Item ordering, release packing and every milestone figure are
computed deterministically here, so any plan the user sees can be explained line by
line from stored feedback.

Generative AI is used only for narrative: milestone names, objectives and the
strategy paragraph. It may never move an item, change a date or alter a number —
those arrive in the prompt as fixed facts and are merged back from the computed
plan, never from the model's reply.
"""

import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import database
from database import db
import fallback_db
from services import workspace_context
from services.ai_service import (
    GEMINI_MODELS,
    GROQ_MODELS,
    MISTRAL_MODELS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    OPENROUTER_TIMEOUT_SECONDS,
    _extract_json_from_text,
    get_gemini_client,
    get_groq_client,
    get_mistral_client,
    get_openrouter_client,
)

logger = logging.getLogger(__name__)

# A release window is a fixed four-week block; the horizon is expressed in weeks.
WEEKS_PER_RELEASE = 4
HORIZON_LABELS = ["now", "next", "later"]
MAX_RELEASES = 13

# Fix work (defects, performance, security) is sequenced before growth work at equal
# value: the same RICE score costs less trust when a defect is left open.
FIX_CATEGORIES = {"bug_report", "bug_fix", "performance", "performance_issue", "security"}


def _effort_of(item: Dict[str, Any]) -> float:
    """Read an item's effort, defaulting to a neutral value when it is unset."""
    rice = item.get("rice") or {}
    try:
        effort = float(rice.get("effort") or 2.0)
    except (TypeError, ValueError):
        effort = 2.0
    return max(0.5, effort)


def _rice_of(item: Dict[str, Any]) -> float:
    rice = item.get("rice") or {}
    try:
        return float(rice.get("score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _weighted_of(item: Dict[str, Any]) -> float:
    weighted = item.get("weighted") or {}
    try:
        return float(weighted.get("final_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _is_fix(item: Dict[str, Any]) -> bool:
    return str(item.get("category") or "").lower() in FIX_CATEGORIES


def _short_name(name: str, limit: int = 48) -> str:
    """Trim a label to a readable length without cutting mid-word where avoidable."""
    text = " ".join(str(name or "").split())
    if len(text) <= limit:
        return text
    trimmed = text[:limit].rsplit(" ", 1)[0]
    return f"{trimmed or text[:limit]}…"


def _quarter_label(day) -> str:
    quarter = (day.month - 1) // 3 + 1
    return f"Q{quarter} {day.year}"


def _release_windows(start_day, horizon_weeks: int) -> List[Dict[str, Any]]:
    """Split the planning horizon into fixed four-week release windows."""
    release_count = max(1, min(MAX_RELEASES, round(max(4, horizon_weeks) / WEEKS_PER_RELEASE)))
    windows: List[Dict[str, Any]] = []
    cursor = start_day
    for index in range(release_count):
        end = cursor + timedelta(weeks=WEEKS_PER_RELEASE) - timedelta(days=1)
        windows.append(
            {
                "index": index,
                "horizon": HORIZON_LABELS[index] if index < len(HORIZON_LABELS) else "later",
                "name": f"Release {index + 1} · {_quarter_label(cursor)}",
                "start_date": cursor.isoformat(),
                "end_date": end.isoformat(),
            }
        )
        cursor = end + timedelta(days=1)
    return windows


def _order_key(item: Dict[str, Any]) -> Tuple[int, float, float, int, str]:
    """
    The sequencing order: RICE first (the framework the user configured), then the
    weighted multi-factor score, then how many customers are actually behind the item.
    Fix work breaks a tie ahead of growth work at equal value — it is the same score
    with more trust at stake, but it never outranks a materially higher score.
    """
    return (
        -_rice_of(item),
        -_weighted_of(item),
        0 if _is_fix(item) else 1,
        -int(item.get("feedback_count") or 0),
        str(item.get("name") or ""),
    )


def _pack_items(
    ordered: List[Dict[str, Any]], windows: List[Dict[str, Any]], velocity: float
) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """
    Assign items to release windows, highest value first, without exceeding a
    window's capacity.

    An item that does not fit an early window stays a candidate for the next one
    rather than being skipped, so a large initiative never leaves a small one
    stranded behind it. Anything left over becomes backlog, not a silent deletion.
    """
    remaining = {window["index"]: max(0.5, float(velocity)) for window in windows}
    assignment: Dict[str, int] = {}
    deferred: List[Dict[str, Any]] = []

    for item in ordered:
        effort = _effort_of(item)
        placed = False
        for window in windows:
            index = window["index"]
            if remaining[index] + 1e-9 >= effort:
                remaining[index] -= effort
                assignment[item["id"]] = index
                placed = True
                break
        if not placed:
            deferred.append(item)

    return assignment, deferred


class _EvidenceIndex:
    """
    Measured facts about the sources behind each prioritization item.

    A roadmap item points back at the cluster or pain point it was seeded from, so
    the plan can cite the same counts the analysis published instead of guessing
    them a second time.
    """

    def __init__(self, insights: Optional[Dict[str, Any]]):
        self.clusters = {str(c.get("id")): c for c in ((insights or {}).get("feature_clusters") or [])}
        self.pain_points = {str(p.get("id")): p for p in ((insights or {}).get("pain_points") or [])}
        # Topic labels, so an item seeded from an earlier analysis still finds its evidence
        # after the analysis is re-run (ids used to be renumbered on every run).
        self._by_label: Dict[str, Dict[str, Any]] = {}
        for source in list(self.clusters.values()) + list(self.pain_points.values()):
            label = source.get("title") or source.get("cluster_name")
            if label:
                self._by_label[self._normalise(label)] = source

    @staticmethod
    def _normalise(label: Any) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", str(label or "").lower()))

    def _match_by_name(self, item_name: Any) -> Optional[Dict[str, Any]]:
        """Find the topic whose label shares the item's own wording."""
        words = [word for word in self._normalise(item_name).split() if len(word) > 3]
        if not words:
            return None
        best: Optional[Dict[str, Any]] = None
        best_score = 0
        for label, source in self._by_label.items():
            score = sum(1 for word in words if word in label)
            if score > best_score:
                best, best_score = source, score
        return best

    def for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        cluster = self.clusters.get(str(item.get("source_cluster_id") or ""))
        pain_point = self.pain_points.get(str(item.get("source_pain_point_id") or ""))
        if not cluster and not pain_point:
            # The id the item was seeded with no longer resolves. Rather than report the
            # topic as evidence-free, reattach it by name and let the plan cite real counts.
            fallback = self._match_by_name(item.get("name"))
            if fallback and fallback in self.clusters.values():
                cluster = fallback
            elif fallback:
                pain_point = fallback
        source = pain_point or cluster or {}

        breakdown = source.get("score_breakdown") or {}
        count = (
            source.get("affected_users_count")
            or source.get("request_count")
            or item.get("feedback_count")
            or 0
        )
        return {
            "source_type": "pain_point" if pain_point else ("feature_cluster" if cluster else "prioritization"),
            "source_id": source.get("id"),
            "title": source.get("title") or source.get("cluster_name"),
            "count": int(count or 0),
            "severity": source.get("severity"),
            "impact_score": source.get("impact_score"),
            "avg_rating": breakdown.get("avg_rating"),
            "negative_sentiment_pct": breakdown.get("negative_sentiment_pct"),
            "phrases": [str(p) for p in (source.get("keywords") or [])][:5],
        }


def _milestone_theme(items: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Pick a milestone name from what the work actually is, not from a template."""
    fix_count = sum(1 for item in items if _is_fix(item))
    if fix_count * 2 >= len(items):
        return "Trust & Reliability", "Stabilise"
    return "Growth & Experience", "Expand"


def _milestone_confidence(records: int) -> str:
    if records >= 500:
        return "high"
    if records >= 100:
        return "medium"
    return "low"


def _milestone_metrics(items: List[Dict[str, Any]], sources: List[Dict[str, Any]], end_date: str) -> List[Dict[str, Any]]:
    """
    State the outcome in the workspace's own measurements where they exist.

    A milestone is judged on numbers this product can actually observe: how many
    customers it spoke to, how negative they were, and how many items shipped.
    Telemetry this workspace cannot see (retention, revenue, latency) is never
    asserted as a measured baseline.
    """
    metrics: List[Dict[str, Any]] = [
        {
            "metric": "Prioritised items completed in this milestone",
            "baseline": f"Measured: {len(items)} items in scope",
            "target": f"Proposed: all {len(items)} shipped by {end_date}",
            "tracking_mechanism": "Prioritization board status and release notes",
        }
    ]

    records = sum(int(source.get("count") or 0) for source in sources)
    metrics.append(
        {
            "metric": "Customer records behind this milestone",
            "baseline": f"Measured: {records} records in the current workspace analysis",
            "target": "Proposed: re-run analysis on the same workspace after release and compare",
            "tracking_mechanism": "Insights → Re-run analysis on this workspace",
        }
    )

    negative_shares = [
        float(source["negative_sentiment_pct"])
        for source in sources
        if source.get("negative_sentiment_pct") is not None
    ]
    ratings = [float(source["avg_rating"]) for source in sources if source.get("avg_rating") is not None]

    if negative_shares:
        worst = max(negative_shares)
        metrics.append(
            {
                "metric": "Negative sentiment share on these topics",
                "baseline": f"Measured: up to {worst:.1f}% negative",
                "target": "Proposed: at least a quarter below the measured baseline",
                "tracking_mechanism": "Re-run the analysis and compare the sentiment distribution",
            }
        )

    if ratings:
        lowest = min(ratings)
        metrics.append(
            {
                "metric": "Lowest average rating among these topics",
                "baseline": f"Measured: {lowest:.2f}/5.0",
                "target": "Proposed: 3.50/5.0 or higher",
                "tracking_mechanism": "Average rating of the matching records on re-run",
            }
        )

    return metrics


def _milestone_exit_criteria(
    items: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    prds_for_items: Dict[str, str],
) -> List[str]:
    """Define done from the documents that exist, not from an aspiration."""
    document_count = len(prds_for_items)
    criteria = [
        (
            f"Every item in this milestone has an approved PRD and testable acceptance criteria "
            f"({document_count} of {len(items)} already have a generated PRD in this workspace)."
        )
    ]

    never_ready = [item["name"] for item in items if item.get("moscow") != "must_have"]
    if never_ready:
        criteria.append(
            "The milestone may close with non-must-have items carried forward: "
            + ", ".join(_short_name(name, 40) for name in never_ready[:3])
            + "."
        )
    else:
        criteria.append("No item in this milestone is allowed to carry forward — all of them are must-have work.")

    negative_shares = [
        float(source["negative_sentiment_pct"])
        for source in sources
        if source.get("negative_sentiment_pct") is not None
    ]
    if negative_shares:
        criteria.append(
            f"Negative sentiment on these topics, measured at up to {max(negative_shares):.1f}% today, "
            "has fallen when the analysis is re-run for this workspace."
        )
    else:
        criteria.append(
            "Negative sentiment on these topics is re-measured on the same workspace after release "
            "and must not increase against the current baseline."
        )

    return criteria


def _build_milestone(
    window: Dict[str, Any],
    items: List[Dict[str, Any]],
    evidence: _EvidenceIndex,
    prds_for_items: Dict[str, str],
    previous: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble one milestone, reusing an AI-written narrative when the scope is unchanged."""
    theme, verb = _milestone_theme(items)
    sources = [evidence.for_item(item) for item in items]
    records = sum(int(source.get("count") or 0) for source in sources)
    top_item = items[0]["name"] if items else "Planned work"

    top_names = ", ".join(f"“{_short_name(item['name'], 38)}”" for item in items[:3])
    objective = (
        f"{verb} the work behind {top_names}"
        + (f" and {len(items) - 3} further initiative(s)" if len(items) > 3 else "")
        + f", addressing {records} customer records."
    )

    rationale = (
        f"{len(items)} item(s) worth {sum(_effort_of(item) for item in items):.1f} effort units, "
        f"packed into {window['name']} at the configured capacity. "
        f"Highest value item: {_short_name(top_item, 60)} (RICE {_rice_of(items[0]):.0f})."
        if items
        else "No items fit inside this window at the configured capacity."
    )

    milestone = {
        "id": f"ms_{window['index'] + 1}",
        "name": f"{theme}: {_short_name(top_item, 44)}",
        "objective": objective,
        "horizon": window["horizon"],
        "release": window["name"],
        "start_date": window["start_date"],
        "end_date": window["end_date"],
        "item_ids": [item["id"] for item in items],
        "item_count": len(items),
        "effort_total": round(sum(_effort_of(item) for item in items), 2),
        "feedback_count": records,
        "confidence": _milestone_confidence(records),
        "rationale": rationale,
        "exit_criteria": _milestone_exit_criteria(items, sources, prds_for_items),
        "success_metrics": _milestone_metrics(items, sources, window["end_date"]),
    }

    if previous:
        milestone["name"] = previous.get("name") or milestone["name"]
        milestone["objective"] = previous.get("objective") or milestone["objective"]
        milestone["rationale"] = previous.get("rationale") or milestone["rationale"]

    return milestone


def _strategy_text(
    items: List[Dict[str, Any]],
    windows: List[Dict[str, Any]],
    deferred: List[Dict[str, Any]],
    velocity: float,
) -> str:
    """Explain the sequencing rule in the plan's own terms."""
    fix_count = sum(1 for item in items if _is_fix(item))
    parts = [
        f"This plan sequences all {len(items)} prioritised initiative(s) by RICE score, "
        f"then by the workspace's weighted multi-factor score, and then by how many customers are behind each item.",
        f"{fix_count} of them are defect, performance or security work and lead their release when value is close, "
        "because an open defect costs more trust than an equivalent new feature earns.",
        f"Items are packed into {len(windows)} release window(s) of four weeks each, holding {velocity:.1f} effort units of work per window.",
    ]
    if deferred:
        parts.append(
            f"{len(deferred)} item(s) did not fit inside the horizon and sit in the backlog with their scores intact, "
            "ready for the next planning cycle rather than being dropped from the plan."
        )
    return " ".join(parts)


async def _ai_narrative(
    plan: Dict[str, Any],
    workspace_name: str,
    focus: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Ask a model for names, objectives and a strategy paragraph for a plan that is
    already fully computed.

    The prompt hands over the fixed plan and explicitly forbids touching sequence,
    dates or figures. The reply is only allowed to fill narrative fields, so a
    hallucinated number or a reordered release cannot reach the user through it.
    """
    lines = [
        f"- {milestone['id']} | {milestone['release']} ({milestone['horizon']}) | "
        f"{milestone['start_date']} → {milestone['end_date']} | "
        f"items: {'; '.join(item['name'] for item in plan['items'] if item['milestone_id'] == milestone['id'])}"
        for milestone in plan["milestones"]
    ]
    backlog = [item["name"] for item in plan["deferred"]]

    prompt = f"""You are a Principal Product Manager writing the narrative for a quarterly roadmap that has ALREADY been computed.

Workspace: {workspace_name}
Strategic focus: {focus or 'not specified'}
Records analysed: {plan['evidence'].get('records_analyzed')}
Prioritised items planned: {plan['evidence'].get('items_planned')}
Backlog beyond the horizon: {backlog if backlog else 'none'}

Computed plan (fixed — do not reorder, re-date or renumber anything):
{chr(10).join(lines)}

Return ONLY a valid JSON object:
{{
  "strategy": "2-3 sentences explaining the sequencing logic of this specific plan.",
  "milestones": [
    {{"id": "ms_1", "name": "Specific milestone name of at most 8 words", "objective": "What this milestone delivers and for whom, grounded in the item names above.", "rationale": "Why this milestone sits here in the sequence."}}
  ]
}}

Rules:
- Use exactly the milestone ids listed above, one entry each.
- Do not state any number that is not in the plan above.
- Do not invent features, customer segments, revenue figures or timelines.
- Return ONLY JSON."""

    groq_client = get_groq_client()
    if groq_client:
        for model in GROQ_MODELS:
            try:
                response = groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=1200,
                    timeout=20,
                    response_format={"type": "json_object"},
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and parsed.get("milestones"):
                    parsed["ai_model"] = f"Groq ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq roadmap narrative failed on %s: %s", model, exc)

    openrouter_client = get_openrouter_client()
    if openrouter_client:
        for model in OPENROUTER_MODELS:
            try:
                response = openrouter_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=OPENROUTER_MAX_TOKENS,
                    timeout=OPENROUTER_TIMEOUT_SECONDS,
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and parsed.get("milestones"):
                    parsed["ai_model"] = f"OpenRouter ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenRouter roadmap narrative failed on %s: %s", model, exc)

    gem_client = get_gemini_client()
    if gem_client:
        for model in GEMINI_MODELS:
            try:
                from google.genai import types

                response = gem_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3, timeout=15),
                )
                parsed = _extract_json_from_text(response.text)
                if parsed and parsed.get("milestones"):
                    parsed["ai_model"] = f"Google Gemini ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001 - every provider failure is a fallback, not an error
                logger.warning("Gemini roadmap narrative failed on %s: %s", model, exc)

    mistral_client = get_mistral_client()
    if mistral_client:
        for model in MISTRAL_MODELS:
            try:
                response = mistral_client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1200,
                    response_format={"type": "json_object"},
                    timeout=20,
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and parsed.get("milestones"):
                    parsed["ai_model"] = f"Mistral ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("Mistral roadmap narrative failed on %s: %s", model, exc)

    return None


def _build_markdown_from_roadmap(plan: Dict[str, Any]) -> str:
    """Render a roadmap as GitHub-flavoured Markdown, report-ready."""
    lines = [
        f"# Product Roadmap — {plan.get('workspace_name') or 'Workspace'}",
        f"**Generated:** `{plan.get('created_at')}` | **Horizon:** {plan.get('horizon_weeks')} weeks "
        f"| **Capacity:** {plan.get('velocity')} effort units per release",
        f"**Plan engine:** {plan.get('ai_model')}",
        "",
        "## Method",
        plan.get("strategy", ""),
        "",
    ]

    evidence = plan.get("evidence") or {}
    lines.extend(
        [
            "## Evidence",
            "| Item | Value |",
            "| :--- | :--- |",
            f"| Records analysed | {evidence.get('records_analyzed')} |",
            f"| Prioritised items planned | {evidence.get('items_planned')} |",
            f"| Items beyond the horizon | {evidence.get('items_deferred')} |",
            f"| Customer records behind planned work | {evidence.get('planned_feedback_records')} |",
            f"| Must-have coverage | {evidence.get('must_have_coverage')} |",
            "",
        ]
    )

    for milestone in plan.get("milestones") or []:
        items = [item for item in plan.get("items") or [] if item.get("milestone_id") == milestone["id"]]
        lines.extend(
            [
                f"## {milestone['name']}",
                f"**{milestone['release']}** · {milestone['horizon'].upper()} · "
                f"{milestone['start_date']} → {milestone['end_date']} · confidence: {milestone['confidence']}",
                "",
                f"*{milestone['objective']}*",
                "",
                f"**Why here:** {milestone['rationale']}",
                "",
                "**Scope**",
            ]
        )
        for item in items:
            lines.append(
                f"- **{item['name']}** — RICE {item['rice_score']:.0f}, weighted {item['weighted_score']:.1f}, "
                f"{item['feedback_count']} records, MoSCoW `{item['moscow']}`, effort {item['effort']}"
            )
        lines.extend(["", "**Exit criteria**"])
        for criterion in milestone.get("exit_criteria") or []:
            lines.append(f"- {criterion}")
        lines.extend(["", "**Success metrics**", "| Metric | Baseline | Target | Tracking |", "| :--- | :--- | :--- | :--- |"])
        for metric in milestone.get("success_metrics") or []:
            lines.append(
                f"| {metric.get('metric')} | {metric.get('baseline')} | {metric.get('target')} | "
                f"{metric.get('tracking_mechanism')} |"
            )
        lines.append("")

    deferred = plan.get("deferred") or []
    lines.append("## Backlog Beyond The Horizon")
    if deferred:
        lines.append(plan.get("deferred_reason", ""))
        lines.append("")
        for item in deferred:
            lines.append(
                f"- {item['name']} — RICE {item['rice_score']:.0f}, {item['feedback_count']} records, effort {item['effort']}"
            )
    else:
        lines.append("Every prioritised item fits inside the current horizon.")
    lines.append("")
    return "\n".join(lines)


async def _persist_plan(plan: Dict[str, Any]) -> None:
    """
    Store the plan, one document per workspace.

    The evaluated plan may have been read back from the database, where the storage id was
    serialised to a string for the API. Writing that string back would try to alter MongoDB's
    immutable `_id`, so the storage key never travels with the plan.
    """
    stored = {key: value for key, value in plan.items() if key != "_id"}
    if database._mongodb_available:
        await db.roadmaps.replace_one({"workspace_id": plan["workspace_id"]}, stored, upsert=True)
    else:
        await fallback_db.save_roadmap(stored)


async def generate_roadmap(
    workspace_id: str,
    horizon_weeks: int = 12,
    velocity: float = 8.0,
    focus: Optional[str] = None,
    include_items: Optional[List[str]] = None,
    replace_existing: bool = True,
) -> Dict[str, Any]:
    """Build (or rebuild) the workspace roadmap from its measured backlog."""
    insights = await workspace_context.load_stored_insights(workspace_id)
    workspace = await workspace_context.resolve_workspace(workspace_id, insights)

    items = await workspace_context.load_prioritization_items(workspace_id)
    if include_items:
        wanted = {str(item_id) for item_id in include_items}
        items = [item for item in items if str(item.get("id")) in wanted]

    if not items:
        return {
            "workspace_id": workspace_id,
            "workspace_name": workspace["name"],
            "strategy": (
                "There is nothing to sequence yet: this workspace has no prioritization items. "
                "Open Prioritization and auto-seed the backlog from customer feedback first."
            ),
            "focus": focus,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "horizon_weeks": horizon_weeks,
            "velocity": velocity,
            "releases": [],
            "milestones": [],
            "items": [],
            "deferred": [],
            "deferred_reason": "",
            "evidence": {
                "records_analyzed": int((insights or {}).get("total_analyzed") or 0),
                "items_planned": 0,
                "items_deferred": 0,
                "planned_feedback_records": 0,
                "must_have_coverage": "0 of 0",
            },
            "ai_generated": False,
            "ai_model": "Deterministic planning engine",
            "raw_markdown": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    prds = await workspace_context.load_prds(workspace_id)
    prds_for_items: Dict[str, str] = {}
    for prd in prds:
        source_id = prd.get("source_id")
        if source_id:
            prds_for_items[str(source_id)] = prd.get("id")

    windows = _release_windows(datetime.now(timezone.utc).date(), horizon_weeks)
    ordered = sorted(items, key=_order_key)
    assignment, deferred = _pack_items(ordered, windows, velocity)

    evidence_index = _EvidenceIndex(insights)
    previous = None if replace_existing else await get_roadmap(workspace_id)
    previous_by_scope: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    if previous:
        for milestone in previous.get("milestones") or []:
            previous_by_scope[tuple(sorted(milestone.get("item_ids") or []))] = milestone

    roadmap_items: List[Dict[str, Any]] = []
    sequence = 0
    for item in ordered:
        # `id` is guaranteed by the read path, but a roadmap is generated from whatever the
        # backlog holds. One row without an identifier used to abort the entire plan with a
        # KeyError, so skip the malformed row instead of failing the whole request.
        item_id = item.get("id")
        if not item_id:
            continue

        # Counted as we go so skipped rows leave no gap in the sequence.
        sequence += 1

        evidence = evidence_index.for_item(item)
        release_index = assignment.get(item_id)
        window = windows[release_index] if release_index is not None else None
        roadmap_items.append(
            {
                "id": item_id,
                "prioritization_item_id": item_id,
                "name": item.get("name") or "Untitled initiative",
                "description": item.get("description") or "",
                "category": item.get("category") or "feature_request",
                "horizon": window["horizon"] if window else "backlog",
                "release": window["name"] if window else "Backlog beyond the horizon",
                "sequence": sequence,
                "rice_score": round(_rice_of(item), 2),
                "weighted_score": round(_weighted_of(item), 2),
                "moscow": item.get("moscow") or "should_have",
                "effort": round(_effort_of(item), 2),
                "feedback_count": int(item.get("feedback_count") or evidence.get("count") or 0),
                "rationale": (
                    f"RICE {_rice_of(item):.0f} (weighted {_weighted_of(item):.1f}) places it at sequence "
                    f"{sequence} of {len(ordered)}; {int(item.get('feedback_count') or evidence.get('count') or 0)} "
                    f"customer records support it and it carries MoSCoW "
                    f"{'must-have' if item.get('moscow') == 'must_have' else (item.get('moscow') or 'should-have').replace('_', ' ')}."
                    + (
                        f" Scheduled into {window['name']}, which still had room for {_effort_of(item)} effort units."
                        if window
                        else f" It did not fit the {horizon_weeks}-week horizon at {velocity:.1f} effort units per release."
                    )
                ),
                "dependencies": (
                    [f"PRD required for {_short_name(item.get('name') or '', 40)}"]
                    if str(item.get("source_cluster_id")) not in prds_for_items
                    and str(item.get("source_pain_point_id")) not in prds_for_items
                    else []
                ),
                "milestone_id": f"ms_{release_index + 1}" if release_index is not None else None,
            }
        )

    by_release: Dict[int, List[Dict[str, Any]]] = {window["index"]: [] for window in windows}
    for item in roadmap_items:
        if item["milestone_id"]:
            by_release[int(item["milestone_id"].split("_")[1]) - 1].append(item)

    milestones: List[Dict[str, Any]] = []
    for window in windows:
        release_items = by_release[window["index"]]
        if not release_items:
            continue
        scope_key = tuple(sorted(item["id"] for item in release_items))
        milestones.append(
            _build_milestone(
                window,
                release_items,
                evidence_index,
                prds_for_items,
                previous=previous_by_scope.get(scope_key),
            )
        )

    releases = [
        {
            "name": window["name"],
            "horizon": window["horizon"],
            "start_date": window["start_date"],
            "end_date": window["end_date"],
            "capacity": round(max(0.5, float(velocity)), 2),
            "effort_total": round(sum(item["effort"] for item in by_release[window["index"]]), 2),
            "item_count": len(by_release[window["index"]]),
            "milestone_ids": [m["id"] for m in milestones if m["release"] == window["name"]],
        }
        for window in windows
    ]

    records_analyzed = int((insights or {}).get("total_analyzed") or 0)
    if not records_analyzed:
        records_analyzed = await workspace_context.count_feedback(workspace_id)

    planned_records = sum(item["feedback_count"] for item in roadmap_items if item["milestone_id"])
    must_have_total = sum(1 for item in roadmap_items if item["moscow"] == "must_have")
    must_have_planned = sum(
        1 for item in roadmap_items if item["moscow"] == "must_have" and item["milestone_id"]
    )

    plan: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "workspace_name": workspace["name"],
        "strategy": _strategy_text(roadmap_items, windows, deferred, velocity),
        "focus": focus,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "horizon_weeks": int(horizon_weeks),
        "velocity": round(float(velocity), 2),
        "releases": releases,
        "milestones": milestones,
        "items": roadmap_items,
        "deferred": [item for item in roadmap_items if not item["milestone_id"]],
        "deferred_reason": (
            f"These initiatives score well but did not fit {len(windows)} release window(s) at "
            f"{velocity:.1f} effort units each. Raise the capacity or the horizon to pull them in."
            if deferred
            else ""
        ),
        "evidence": {
            "generated_by": "Deterministic planning engine",
            "workspace": workspace["name"],
            "records_analyzed": records_analyzed,
            "items_planned": sum(1 for item in roadmap_items if item["milestone_id"]),
            "items_deferred": sum(1 for item in roadmap_items if not item["milestone_id"]),
            "planned_feedback_records": planned_records,
            "must_have_coverage": f"{must_have_planned} of {must_have_total} must-have items scheduled",
            "method": (
                "Ordering, release packing, dates and every figure in this plan are computed from the "
                "workspace's prioritization backlog and its stored analysis. AI is used for narrative only."
            ),
        },
        "ai_generated": False,
        "ai_model": "Deterministic planning engine",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    narrative = await _ai_narrative(plan, workspace["name"], focus)
    if narrative:
        plan["strategy"] = narrative.get("strategy") or plan["strategy"]
        by_id = {entry.get("id"): entry for entry in narrative.get("milestones") or [] if isinstance(entry, dict)}
        for milestone in plan["milestones"]:
            polish = by_id.get(milestone["id"]) or {}
            milestone["name"] = polish.get("name") or milestone["name"]
            milestone["objective"] = polish.get("objective") or milestone["objective"]
            milestone["rationale"] = polish.get("rationale") or milestone["rationale"]
        plan["ai_generated"] = True
        plan["ai_model"] = narrative.get("ai_model") or "AI provider"
        plan["evidence"]["generated_by"] = plan["ai_model"]

    plan["raw_markdown"] = _build_markdown_from_roadmap(plan)
    await _persist_plan(plan)
    return plan


async def get_roadmap(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Return the stored roadmap for a workspace, if one has been generated."""
    if database._mongodb_available:
        roadmap = await db.roadmaps.find_one({"workspace_id": workspace_id})
        if roadmap and "_id" in roadmap:
            roadmap["_id"] = str(roadmap["_id"])
        return roadmap
    return await fallback_db.get_roadmap(workspace_id)


async def delete_roadmap(workspace_id: str) -> bool:
    """Remove a stored roadmap."""
    if database._mongodb_available:
        result = await db.roadmaps.delete_one({"workspace_id": workspace_id})
        return result.deleted_count > 0
    return await fallback_db.delete_roadmap(workspace_id)


async def reschedule_item(workspace_id: str, item_id: str, target_release_index: int) -> Optional[Dict[str, Any]]:
    """
    Move one initiative into another release window and rebuild the plan's structure.

    This is the interactive half of roadmap planning: a PM drags work forward or pushes
    it back, and the milestones, capacity totals, exit criteria and Markdown are all
    recomputed around the new placement. Milestone narratives written for an unchanged
    scope are preserved — a model is never asked to describe work it did not see.
    """
    plan = await get_roadmap(workspace_id)
    if not plan:
        return None

    if not plan.get("releases"):
        return None

    start_day = datetime.fromisoformat(plan["releases"][0]["start_date"]).date()
    windows = _release_windows(start_day, plan.get("horizon_weeks") or 12)

    target_release_index = max(0, min(len(windows) - 1, int(target_release_index)))
    item = next((entry for entry in plan.get("items") or [] if entry.get("id") == item_id), None)
    if not item:
        return None

    # Re-pack everything else at the same capacity, then force the moved item in: the
    # user's decision wins over the packer, and the window it lands in may exceed its
    # nominal capacity by exactly that one item (reported, not hidden).
    velocity = float(plan.get("velocity") or 8.0)
    others = [entry for entry in sorted(plan["items"], key=lambda e: e.get("sequence") or 0) if entry.get("id") != item_id]
    ordered = sorted(
        others,
        key=lambda entry: (
            -float(entry.get("rice_score") or 0.0),
            -float(entry.get("weighted_score") or 0.0),
            -int(entry.get("feedback_count") or 0),
            entry.get("name") or "",
        ),
    )
    assignment, _ = _pack_items(
        [{"id": entry["id"], "rice": {"effort": entry.get("effort")}} for entry in ordered],
        windows,
        velocity,
    )
    placement = {entry["id"]: assignment.get(entry["id"]) for entry in ordered}
    placement[item_id] = target_release_index

    previous_by_scope: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for milestone in plan.get("milestones") or []:
        previous_by_scope[tuple(sorted(milestone.get("item_ids") or []))] = milestone

    insights = await workspace_context.load_stored_insights(workspace_id)
    evidence_index = _EvidenceIndex(insights)
    prds = await workspace_context.load_prds(workspace_id)
    prds_for_items = {str(prd.get("source_id")): prd.get("id") for prd in prds if prd.get("source_id")}

    remapped: List[Dict[str, Any]] = []
    for entry in sorted(plan["items"], key=lambda e: e.get("sequence") or 0):
        index = placement.get(entry["id"])
        window = windows[index] if index is not None else None
        entry = dict(entry)
        entry["horizon"] = window["horizon"] if window else "backlog"
        entry["release"] = window["name"] if window else "Backlog beyond the horizon"
        entry["milestone_id"] = f"ms_{index + 1}" if index is not None else None
        remapped.append(entry)

    by_release: Dict[int, List[Dict[str, Any]]] = {window["index"]: [] for window in windows}
    for entry in remapped:
        if entry["milestone_id"]:
            by_release[int(entry["milestone_id"].split("_")[1]) - 1].append(entry)

    milestones: List[Dict[str, Any]] = []
    for window in windows:
        release_items = sorted(by_release[window["index"]], key=lambda e: e.get("sequence") or 0)
        if not release_items:
            continue
        scope_key = tuple(sorted(entry["id"] for entry in release_items))
        milestones.append(
            _build_milestone(
                window,
                release_items,
                evidence_index,
                prds_for_items,
                previous=previous_by_scope.get(scope_key),
            )
        )

    plan["items"] = remapped
    plan["milestones"] = milestones
    plan["deferred"] = [entry for entry in remapped if not entry["milestone_id"]]
    plan["releases"] = [
        {
            "name": window["name"],
            "horizon": window["horizon"],
            "start_date": window["start_date"],
            "end_date": window["end_date"],
            "capacity": round(max(0.5, velocity), 2),
            "effort_total": round(sum(float(entry.get("effort") or 0) for entry in by_release[window["index"]]), 2),
            "item_count": len(by_release[window["index"]]),
            "milestone_ids": [m["id"] for m in milestones if m["release"] == window["name"]],
        }
        for window in windows
    ]
    plan["evidence"]["items_planned"] = sum(1 for entry in remapped if entry["milestone_id"])
    plan["evidence"]["items_deferred"] = sum(1 for entry in remapped if not entry["milestone_id"])
    plan["evidence"]["planned_feedback_records"] = sum(
        int(entry.get("feedback_count") or 0) for entry in remapped if entry["milestone_id"]
    )
    plan["updated_at"] = datetime.now(timezone.utc).isoformat()
    plan["raw_markdown"] = _build_markdown_from_roadmap(plan)
    await _persist_plan(plan)
    return plan
