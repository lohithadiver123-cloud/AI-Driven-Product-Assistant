"""
Executive Summary & Product Strategy Report service for Milestone 4.

A report is an argument made from measurements, not a description of the app. Every
figure below is read from the workspace's stored analysis, its prioritization backlog,
its roadmap and the documents already generated from it. Where a report would normally
claim a business outcome (revenue, retention, conversion) this service states the
measured customer evidence instead and labels any target as a proposal.

AI writes only the prose the numbers cannot: the headline read and the strategy
narrative. Positions, pillars, roadmap windows and every value stay computed.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import database
from database import db
import fallback_db
from services import roadmap_service, workspace_context
from services.ai_service import (
    GEMINI_MODELS,
    GROQ_MODELS,
    MISTRAL_MODELS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    _extract_json_from_text,
    get_gemini_client,
    get_groq_client,
    get_mistral_client,
    get_openrouter_client,
)

logger = logging.getLogger(__name__)

REPORT_TYPES = {"executive_summary", "product_strategy"}

CATEGORY_LABELS = {
    "bug_report": "Defects",
    "feature_request": "Feature demand",
    "performance_issue": "Performance",
    "general_feedback": "General feedback",
    "security": "Security",
}


def _pct(part: float, whole: float) -> float:
    if not whole:
        return 0.0
    return round(100.0 * float(part) / float(whole), 1)


def _health_snapshot(insights: Dict[str, Any], stored_records: int) -> Dict[str, Any]:
    """Read the measured product-health numbers out of the stored analysis."""
    total = int(insights.get("total_analyzed") or 0)
    sentiment = insights.get("sentiment_distribution") or insights.get("by_sentiment") or {}
    categories = insights.get("category_distribution") or insights.get("by_category") or {}
    negative = int(sentiment.get("negative") or 0)
    positive = int(sentiment.get("positive") or 0)
    neutral = int(sentiment.get("neutral") or 0)

    return {
        "health_score": float(insights.get("health_score") or 0.0),
        "records_analyzed": total,
        "records_stored": stored_records,
        "coverage_note": (
            "Analysis and stored feedback agree."
            if stored_records in (0, total)
            else f"{abs(stored_records - total)} record(s) were imported after the last analysis and are not reflected in these figures."
        ),
        "sentiment_distribution": sentiment,
        "category_distribution": categories,
        "positive_share": _pct(positive, positive + neutral + negative),
        "negative_share": _pct(negative, positive + neutral + negative),
        "themes_count": len(insights.get("themes") or []),
        "pain_points_count": len(insights.get("pain_points") or []),
        "clusters_count": len(insights.get("feature_clusters") or []),
        "trend_periods": len(insights.get("trends") or []),
        "analyzed_at": insights.get("analyzed_at"),
        "analyzed_by": insights.get("ai_model") or "Deterministic analysis engine",
    }


def _key_findings(insights: Dict[str, Any], health: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Turn the highest-impact measured results into findings an executive can act on."""
    findings: List[Dict[str, Any]] = []

    pain_points = sorted(
        insights.get("pain_points") or [],
        key=lambda point: float(point.get("impact_score") or 0),
        reverse=True,
    )
    for point in pain_points[:4]:
        count = int(point.get("affected_users_count") or 0)
        findings.append(
            {
                "title": str(point.get("title") or "Recurring customer friction"),
                "detail": (
                    f"{count} customer record(s) describe this issue; severity is rated "
                    f"{point.get('severity') or 'unknown'} on an impact score of "
                    f"{float(point.get('impact_score') or 0):.1f}/100."
                ),
                "evidence": f"affected_users_count={count}, impact_score={float(point.get('impact_score') or 0):.1f}, severity={point.get('severity')}",
                "severity": str(point.get("severity") or "medium"),
                "source": "Insights → Pain points",
            }
        )

    clusters = sorted(
        insights.get("feature_clusters") or [],
        key=lambda cluster: float(cluster.get("priority_score") or 0),
        reverse=True,
    )
    for cluster in clusters[:2]:
        count = int(cluster.get("request_count") or 0)
        findings.append(
            {
                "title": f"Demand for {cluster.get('cluster_name') or 'an unscheduled capability'}",
                "detail": (
                    f"{count} customer request(s) cluster here at {cluster.get('demand_level') or 'unknown'} demand "
                    f"(priority {float(cluster.get('priority_score') or 0):.1f}/100)."
                ),
                "evidence": f"request_count={count}, demand_level={cluster.get('demand_level')}, priority_score={float(cluster.get('priority_score') or 0):.1f}",
                "severity": "medium",
                "source": "Insights → Feature clusters",
            }
        )

    categories = health.get("category_distribution") or {}
    if categories:
        top_category, top_count = max(categories.items(), key=lambda pair: pair[1])
        findings.append(
            {
                "title": f"Most feedback is {CATEGORY_LABELS.get(top_category, top_category).lower()}",
                "detail": (
                    f"{top_count} of {health.get('records_analyzed')} analysed records fall in this category "
                    f"({_pct(top_count, health.get('records_analyzed') or 0)}%), which sets what the team spends its time on."
                ),
                "evidence": f"category={top_category}, count={top_count}",
                "severity": "low",
                "source": "Insights → Category distribution",
            }
        )

    return findings


def _pillars(
    insights: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]],
    health: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Build strategy pillars from the plan that exists.

    With a roadmap, each milestone is a pillar — that is the strategy actually being
    executed. Without one, pillars are derived from the highest-demand measured
    clusters and the most severe pain points.
    """
    pillars: List[Dict[str, Any]] = []

    if roadmap and roadmap.get("milestones"):
        for milestone in roadmap["milestones"]:
            items = [
                item
                for item in roadmap.get("items") or []
                if item.get("milestone_id") == milestone.get("id")
            ]
            pillars.append(
                {
                    "name": milestone.get("name"),
                    "objective": milestone.get("objective"),
                    "rationale": milestone.get("rationale"),
                    "linked_items": [str(item.get("name")) for item in items][:8],
                    "evidence": (
                        f"{milestone.get('item_count')} roadmap item(s), {milestone.get('feedback_count')} customer "
                        f"record(s) behind them, {milestone.get('release')} ({milestone.get('horizon')}), "
                        f"evidence confidence {milestone.get('confidence')}."
                    ),
                }
            )
        return pillars

    for point in sorted(
        insights.get("pain_points") or [],
        key=lambda point: float(point.get("impact_score") or 0),
        reverse=True,
    )[:3]:
        pillars.append(
            {
                "name": f"Reduce: {point.get('title')}",
                "objective": str(point.get("recommended_action") or "Remove the friction customers report most."),
                "rationale": (
                    f"{int(point.get('affected_users_count') or 0)} records with severity {point.get('severity')} "
                    f"and an impact score of {float(point.get('impact_score') or 0):.1f}/100."
                ),
                "linked_items": [],
                "evidence": str(point.get("root_cause") or "Root cause stated in the analysis."),
            }
        )

    for cluster in sorted(
        insights.get("feature_clusters") or [],
        key=lambda cluster: float(cluster.get("priority_score") or 0),
        reverse=True,
    )[:2]:
        pillars.append(
            {
                "name": f"Deliver: {cluster.get('cluster_name')}",
                "objective": str(cluster.get("summary") or "Serve the most requested capability."),
                "rationale": (
                    f"{int(cluster.get('request_count') or 0)} requests at {cluster.get('demand_level')} demand "
                    f"(priority {float(cluster.get('priority_score') or 0):.1f}/100)."
                ),
                "linked_items": [],
                "evidence": f"demand_level={cluster.get('demand_level')}",
            }
        )

    if not pillars:
        pillars.append(
            {
                "name": "Establish a measured baseline",
                "objective": "Run the workspace analysis so strategy can be grounded in evidence.",
                "rationale": "This workspace has no stored analysis yet, so no pillar can cite customer evidence.",
                "linked_items": [],
                "evidence": f"records_analyzed={health.get('records_analyzed')}",
            }
        )
    return pillars


def _roadmap_outlook(roadmap: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Summarise what ships when, from the stored roadmap."""
    if not roadmap or not roadmap.get("releases"):
        return []
    outlook: List[Dict[str, Any]] = []
    for release in roadmap.get("releases") or []:
        items = [
            item
            for item in roadmap.get("items") or []
            if item.get("release") == release.get("name")
        ]
        outlook.append(
            {
                "release": release.get("name"),
                "horizon": release.get("horizon"),
                "start_date": release.get("start_date"),
                "end_date": release.get("end_date"),
                "item_count": release.get("item_count"),
                "effort_total": release.get("effort_total"),
                "capacity": release.get("capacity"),
                "highlights": [str(item.get("name")) for item in items[:4]],
                "customer_records": sum(int(item.get("feedback_count") or 0) for item in items),
            }
        )
    return outlook


def _kpis(health: Dict[str, Any], roadmap: Optional[Dict[str, Any]], items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """State the product indicators this workspace can actually measure."""
    negative_share = float(health.get("negative_share") or 0.0)
    kpis = [
        {
            "metric": "Product health score",
            "value": f"{float(health.get('health_score') or 0):.1f}/100",
            "interpretation": (
                "Derived from rating distribution, sentiment balance and how concentrated the "
                "reported problems are across the analysed feedback."
            ),
            "trend": "flat",
        },
        {
            "metric": "Negative feedback share",
            "value": f"{negative_share:.1f}%",
            "interpretation": f"{int(((health.get('sentiment_distribution') or {}).get('negative')) or 0)} of "
            f"{health.get('records_analyzed')} analysed records are negative.",
            "trend": "up" if negative_share >= 25 else "flat",
        },
        {
            "metric": "Distinct pain points identified",
            "value": str(health.get("pain_points_count") or 0),
            "interpretation": "Recurring, evidence-backed issues the analysis isolated from the corpus.",
            "trend": "flat",
        },
        {
            "metric": "Open prioritised initiatives",
            "value": str(len(items)),
            "interpretation": "Backlog width the team is choosing a sequence from.",
            "trend": "flat",
        },
    ]

    if roadmap:
        evidence = roadmap.get("evidence") or {}
        kpis.append(
            {
                "metric": "Must-have items scheduled",
                "value": str(evidence.get("must_have_coverage") or "0 of 0"),
                "interpretation": "Coverage of must-have work inside the current planning horizon.",
                "trend": "flat",
            }
        )
    return kpis


def _risks(
    health: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]],
    items: List[Dict[str, Any]],
    prd_count: int,
) -> List[Dict[str, Any]]:
    """Name what could go wrong, using the plan's own weak points."""
    risks: List[Dict[str, Any]] = []

    coverage_note = str(health.get("coverage_note") or "")
    if coverage_note and "not reflected" in coverage_note:
        risks.append(
            {
                "risk": "The analysis is behind the stored feedback, so every figure in this report describes an older snapshot.",
                "severity": "high",
                "mitigation": coverage_note + " Re-run the workspace analysis before circulating the report.",
            }
        )

    if roadmap and roadmap.get("deferred"):
        risks.append(
            {
                "risk": f"{len(roadmap['deferred'])} prioritised initiative(s) did not fit the current horizon.",
                "severity": "medium",
                "mitigation": str(roadmap.get("deferred_reason") or "Raise capacity or extend the horizon at the next planning cycle."),
            }
        )
    elif roadmap:
        risks.append(
            {
                "risk": "The plan commits every prioritised initiative, so any new emergency displaces measured customer work.",
                "severity": "low",
                "mitigation": "Keep one release window's worth of capacity unallocated in the next planning cycle.",
            }
        )

    if items and prd_count == 0:
        risks.append(
            {
                "risk": "No initiative in the backlog has a PRD yet, so scope is not defined beyond its score.",
                "severity": "medium",
                "mitigation": "Generate the PRD for the top-ranked item before its milestone starts.",
            }
        )

    low_sample = [
        point for point in (roadmap or {}).get("milestones") or [] if point.get("confidence") == "low"
    ]
    if low_sample:
        risks.append(
            {
                "risk": f"{len(low_sample)} milestone(s) rest on fewer than 100 customer records.",
                "severity": "medium",
                "mitigation": "Treat those milestones as evidence-gathering: validate the problem before committing the whole scope.",
            }
        )

    if not risks:
        risks.append(
            {
                "risk": "This workspace has no stored analysis, so nothing in the report is evidence-backed yet.",
                "severity": "high",
                "mitigation": "Import feedback and run the workspace analysis.",
            }
        )
    return risks


def _recommendations(
    insights: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]],
    health: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Recommend the next moves in the order the evidence supports them."""
    recommendations: List[Dict[str, Any]] = []

    if roadmap and roadmap.get("items"):
        for item in (roadmap.get("items") or [])[:3]:
            recommendations.append(
                {
                    "action": f"Deliver “{item.get('name')}”",
                    "owner": "Product & Engineering",
                    "rationale": (
                        f"RICE {float(item.get('rice_score') or 0):.0f}, {item.get('feedback_count')} supporting "
                        f"records, scheduled in {item.get('release')} ({item.get('horizon')})."
                    ),
                    "horizon": str(item.get("horizon") or "now"),
                }
            )

    top_pain = sorted(
        insights.get("pain_points") or [],
        key=lambda point: float(point.get("impact_score") or 0),
        reverse=True,
    )
    if top_pain:
        point = top_pain[0]
        recommendations.append(
            {
                "action": f"Assign an owner to “{point.get('title')}”",
                "owner": "Product",
                "rationale": (
                    f"Highest measured impact in the workspace ({float(point.get('impact_score') or 0):.1f}/100) "
                    f"across {int(point.get('affected_users_count') or 0)} records."
                ),
                "horizon": "now",
            }
        )

    if "not reflected" in str(health.get("coverage_note") or ""):
        recommendations.append(
            {
                "action": "Re-run the workspace analysis before this report is circulated",
                "owner": "Product Ops",
                "rationale": str(health.get("coverage_note")),
                "horizon": "now",
            }
        )

    if not roadmap:
        recommendations.append(
            {
                "action": "Generate a roadmap from the prioritised backlog",
                "owner": "Product",
                "rationale": "Priorities exist but are not yet sequenced into releases, so there is no committed plan to report against.",
                "horizon": "now",
            }
        )

    return recommendations


def _deterministic_summary(
    workspace_name: str,
    report_type: str,
    health: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]],
    insights: Dict[str, Any],
) -> str:
    """Write the executive read from measured facts alone."""
    total = int(health.get("records_analyzed") or 0)
    negative_share = float(health.get("negative_share") or 0.0)
    top_pain = sorted(
        insights.get("pain_points") or [],
        key=lambda point: float(point.get("impact_score") or 0),
        reverse=True,
    )
    pain_text = (
        f"The single largest measured problem is “{top_pain[0].get('title')}”, reported by "
        f"{int(top_pain[0].get('affected_users_count') or 0)} customers at impact "
        f"{float(top_pain[0].get('impact_score') or 0):.1f}/100."
        if top_pain
        else "No recurring pain point has been isolated yet."
    )

    plan_text = ""
    if roadmap and roadmap.get("releases"):
        first = roadmap["releases"][0]
        plan_text = (
            f" The plan commits {roadmap.get('evidence', {}).get('items_planned')} prioritised initiative(s) across "
            f"{len(roadmap['releases'])} release window(s); {first.get('name')} opens on {first.get('start_date')} with "
            f"{first.get('item_count')} item(s) and {first.get('effort_total')} effort units committed."
        )
    elif report_type == "product_strategy":
        plan_text = " No roadmap has been generated from the backlog yet, so this strategy states priorities without a committed sequence."

    return (
        f"{workspace_name} is measured at a product health score of {float(health.get('health_score') or 0):.1f}/100 "
        f"across {total} analysed customer records, {negative_share:.1f}% of which are negative. "
        f"{pain_text}"
        f" The analysis identifies {health.get('pain_points_count')} pain point(s), "
        f"{health.get('clusters_count')} feature cluster(s) and {health.get('themes_count')} theme(s).{plan_text}"
    )


async def _ai_summary(
    report_type: str,
    audience: str,
    focus: Optional[str],
    health: Dict[str, Any],
    insights: Dict[str, Any],
    roadmap: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Let a model write the executive prose, on numbers it is not allowed to change."""
    pain_lines = [
        f"- {point.get('title')} | affected={point.get('affected_users_count')} | impact={point.get('impact_score')} | severity={point.get('severity')}"
        for point in (insights.get("pain_points") or [])[:5]
    ]
    cluster_lines = [
        f"- {cluster.get('cluster_name')} | requests={cluster.get('request_count')} | demand={cluster.get('demand_level')} | priority={cluster.get('priority_score')}"
        for cluster in (insights.get("feature_clusters") or [])[:5]
    ]
    plan_lines = [
        f"- {release.get('name')} ({release.get('horizon')}) {release.get('start_date')}→{release.get('end_date')}: "
        f"{release.get('item_count')} items, {release.get('effort_total')} effort units"
        for release in (roadmap or {}).get("releases") or []
    ]

    prompt = f"""You are a Principal Product Manager writing for {audience}.

Report type: {report_type}
Strategic focus: {focus or 'not specified'}

Measured facts (do not contradict, extend or restate with different numbers):
- Records analysed: {health.get('records_analyzed')}
- Health score: {health.get('health_score')}/100
- Negative share: {health.get('negative_share')}%
- Pain points: {health.get('pain_points_count')}, feature clusters: {health.get('clusters_count')}, themes: {health.get('themes_count')}
- Analysis produced by: {health.get('analyzed_by')} at {health.get('analyzed_at')}
- Data coverage: {health.get('coverage_note')}

Pain points:
{chr(10).join(pain_lines) if pain_lines else '- none isolated'}

Feature demand:
{chr(10).join(cluster_lines) if cluster_lines else '- none isolated'}

Roadmap:
{chr(10).join(plan_lines) if plan_lines else '- no roadmap generated yet'}

Return ONLY a valid JSON object:
{{
  "headline": "One sentence a busy executive can repeat, using only the facts above.",
  "executive_summary": "Two short paragraphs: what the evidence shows and what the plan does about it.",
  "pillars": [{{"name": "Existing pillar or milestone name", "objective": "What it delivers", "rationale": "Why it is prioritised, from the facts above"}}]
}}

Rules:
- Never invent revenue, retention, conversion, churn or cohort figures.
- Do not state any number that is not in the facts above.
- Keep the tone analytical and specific; no marketing language.
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
                    max_tokens=1400,
                    timeout=20,
                    response_format={"type": "json_object"},
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and parsed.get("executive_summary"):
                    parsed["ai_model"] = f"Groq ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("Groq report summary failed on %s: %s", model, exc)

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
                if parsed and parsed.get("executive_summary"):
                    parsed["ai_model"] = f"OpenRouter ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("OpenRouter report summary failed on %s: %s", model, exc)

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
                if parsed and parsed.get("executive_summary"):
                    parsed["ai_model"] = f"Google Gemini ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini report summary failed on %s: %s", model, exc)

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
                    max_tokens=1400,
                    response_format={"type": "json_object"},
                    timeout=20,
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and parsed.get("executive_summary"):
                    parsed["ai_model"] = f"Mistral ({model})"
                    return parsed
            except Exception as exc:  # noqa: BLE001
                logger.warning("Mistral report summary failed on %s: %s", model, exc)

    return None


def _build_markdown_from_report(report: Dict[str, Any]) -> str:
    """Render a report as GitHub-flavoured Markdown for export or printing."""
    health = report.get("product_health") or {}
    evidence = report.get("evidence") or {}
    lines = [
        f"# {report.get('title')}",
        f"**Type:** {report.get('report_type')} | **Audience:** {report.get('audience')} | "
        f"**Status:** `{str(report.get('status', 'draft')).upper()}` | **Version:** {report.get('version')}"
        + (f" | **Period:** {report.get('period')}" if report.get("period") else ""),
        f"**Generated:** `{report.get('created_at')}` · **Written by:** {report.get('ai_model')}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        f"**{report.get('headline')}**",
        "",
        report.get("executive_summary", ""),
        "",
        "## 2. Product Health Snapshot",
        "| Indicator | Measured value |",
        "| :--- | :--- |",
        f"| Health score | {health.get('health_score')}/100 |",
        f"| Records analysed | {health.get('records_analyzed')} |",
        f"| Records stored in workspace | {health.get('records_stored')} |",
        f"| Negative share | {health.get('negative_share')}% |",
        f"| Positive share | {health.get('positive_share')}% |",
        f"| Themes / pain points / clusters | {health.get('themes_count')} / {health.get('pain_points_count')} / {health.get('clusters_count')} |",
        f"| Analysis produced by | {health.get('analyzed_by')} at {health.get('analyzed_at')} |",
        f"| Coverage | {health.get('coverage_note')} |",
        "",
        "## 3. Key Findings",
    ]
    for index, finding in enumerate(report.get("key_findings") or [], start=1):
        lines.append(f"### 3.{index} {finding.get('title')} ({finding.get('severity')})")
        lines.append(str(finding.get("detail")))
        if finding.get("evidence"):
            lines.append(f"> Evidence: `{finding.get('evidence')}` — {finding.get('source')}")
        lines.append("")

    lines.append("## 4. Strategic Pillars")
    for pillar in report.get("strategic_pillars") or []:
        lines.append(f"### {pillar.get('name')}")
        lines.append(f"**Objective:** {pillar.get('objective')}")
        lines.append(f"**Why:** {pillar.get('rationale')}")
        if pillar.get("linked_items"):
            lines.append("**Scope:** " + ", ".join(str(item) for item in pillar["linked_items"]))
        if pillar.get("evidence"):
            lines.append(f"> Evidence: {pillar.get('evidence')}")
        lines.append("")

    outlook = report.get("roadmap_outlook") or []
    if outlook:
        lines.extend(["## 5. Roadmap Outlook", "| Release | Horizon | Window | Items | Effort | Customers |", "| :--- | :--- | :--- | :--- | :--- | :--- |"])
        for release in outlook:
            lines.append(
                f"| {release.get('release')} | {release.get('horizon')} | {release.get('start_date')} → {release.get('end_date')} "
                f"| {release.get('item_count')} | {release.get('effort_total')}/{release.get('capacity')} | {release.get('customer_records')} |"
            )
        lines.append("")

    lines.extend(["## 6. Product Indicators", "| Indicator | Value | Interpretation |", "| :--- | :--- | :--- |"])
    for kpi in report.get("kpis") or []:
        lines.append(f"| {kpi.get('metric')} | {kpi.get('value')} | {kpi.get('interpretation')} |")
    lines.append("")

    lines.append("## 7. Risks & Mitigations")
    for risk in report.get("risks") or []:
        lines.append(f"- **{risk.get('severity').upper()}** — {risk.get('risk')}")
        lines.append(f"  - *Mitigation:* {risk.get('mitigation')}")
    lines.append("")

    lines.append("## 8. Recommendations")
    for index, rec in enumerate(report.get("recommendations") or [], start=1):
        lines.append(f"{index}. **{rec.get('action')}** ({rec.get('owner')}, {rec.get('horizon')})")
        lines.append(f"   - {rec.get('rationale')}")
    lines.append("")

    lines.extend(
        [
            "## 9. Evidence & Method",
            "| Item | Value |",
            "| :--- | :--- |",
            f"| Written by | {report.get('ai_model')} |",
            f"| Workspace | {report.get('workspace_name')} |",
            f"| Records analysed | {evidence.get('records_analyzed')} |",
            f"| Prioritised items | {evidence.get('items_planned')} |",
            f"| Roadmap releases | {evidence.get('releases')} |",
            f"| PRDs / user stories behind the plan | {evidence.get('prds')} / {evidence.get('user_stories')} |",
            "",
            f"*Method:* {evidence.get('method')}",
            "",
        ]
    )
    return "\n".join(lines)


async def generate_report(
    workspace_id: str,
    report_type: str = "executive_summary",
    audience: Optional[str] = "executive_leadership",
    period: Optional[str] = None,
    focus: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an executive summary or product strategy report for a workspace."""
    report_type = report_type if report_type in REPORT_TYPES else "executive_summary"

    insights = await workspace_context.load_stored_insights(workspace_id)
    workspace = await workspace_context.resolve_workspace(workspace_id, insights)
    items = await workspace_context.load_prioritization_items(workspace_id)
    prds = await workspace_context.load_prds(workspace_id)
    stories = await workspace_context.load_user_stories(workspace_id)
    roadmap = await roadmap_service.get_roadmap(workspace_id)

    stored_records = await workspace_context.count_feedback(workspace_id)
    insights = insights or {}
    health = _health_snapshot(insights, stored_records)

    title = (
        f"{workspace['name']} — Product Health & Executive Summary"
        if report_type == "executive_summary"
        else f"{workspace['name']} — Product Strategy & Roadmap"
    )
    if period:
        title = f"{title} ({period})"

    summary = _deterministic_summary(workspace["name"], report_type, health, roadmap, insights)
    headline = (
        f"{health.get('records_analyzed')} customer records place {workspace['name']} at "
        f"{float(health.get('health_score') or 0):.1f}/100 health with {health.get('negative_share')}% negative."
    )

    pillars = _pillars(insights, roadmap, health)
    ai_model = "Deterministic reporting engine"

    narrative = await _ai_summary(report_type, audience or "executive leadership", focus, health, insights, roadmap)
    if narrative:
        summary = narrative.get("executive_summary") or summary
        headline = narrative.get("headline") or headline
        ai_model = narrative.get("ai_model") or "AI provider"
        written = narrative.get("pillars") or []
        for pillar, polish in zip(pillars, written):
            if not isinstance(polish, dict):
                continue
            # Names, scope and evidence stay computed; only the prose is the model's.
            pillar["objective"] = polish.get("objective") or pillar["objective"]
            pillar["rationale"] = polish.get("rationale") or pillar["rationale"]

    findings = _key_findings(insights, health)
    risks = _risks(health, roadmap, items, len(prds))
    recommendations = _recommendations(insights, roadmap, health)
    kpis = _kpis(health, roadmap, items)
    outlook = _roadmap_outlook(roadmap)

    now = datetime.now(timezone.utc)
    report: Dict[str, Any] = {
        "id": f"rep_{uuid.uuid4().hex[:12]}",
        "workspace_id": workspace_id,
        "workspace_name": workspace["name"],
        "title": title,
        "report_type": report_type,
        "audience": audience or "executive_leadership",
        "period": period,
        "status": "draft",
        "version": "1.0",
        "executive_summary": summary,
        "headline": headline,
        "product_health": health,
        "key_findings": findings,
        "strategic_pillars": pillars,
        "roadmap_outlook": outlook,
        "kpis": kpis,
        "risks": risks,
        "recommendations": recommendations,
        "evidence": {
            "generated_by": ai_model,
            "workspace": workspace["name"],
            "records_analyzed": health.get("records_analyzed"),
            "records_stored": stored_records,
            "items_planned": len(items),
            "releases": len(roadmap.get("releases") or []) if roadmap else 0,
            "prds": len(prds),
            "user_stories": len(stories),
            "focus": focus,
            "method": (
                "Every figure in this report is read from this workspace's stored analysis, prioritization "
                "backlog and roadmap. Business outcomes this workspace cannot observe are not asserted."
            ),
        },
        "ai_generated": bool(narrative),
        "ai_model": ai_model,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    report["raw_markdown"] = _build_markdown_from_report(report)

    if database._mongodb_available:
        await db.reports.insert_one(dict(report))
    else:
        await fallback_db.save_report(dict(report))

    return report


async def get_reports_for_workspace(workspace_id: str) -> List[Dict[str, Any]]:
    """List every report generated for a workspace, newest first."""
    if database._mongodb_available:
        cursor = db.reports.find({"workspace_id": workspace_id}).sort("created_at", -1)
        records = await cursor.to_list(length=None)
        for record in records:
            if "_id" in record:
                record["_id"] = str(record["_id"])
        return records
    return await fallback_db.find_reports_by_workspace(workspace_id)


async def get_report_by_id(report_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single report."""
    if database._mongodb_available:
        report = await db.reports.find_one({"id": report_id})
        if report and "_id" in report:
            report["_id"] = str(report["_id"])
        return report
    return await fallback_db.find_report_by_id(report_id)


async def update_report(report_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update editable report fields and re-render the Markdown."""
    existing = await get_report_by_id(report_id)
    if not existing:
        return None

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    merged = {**existing, **updates}
    if "raw_markdown" not in updates:
        updates["raw_markdown"] = _build_markdown_from_report(merged)

    if database._mongodb_available:
        await db.reports.update_one({"id": report_id}, {"$set": updates})
        return await get_report_by_id(report_id)
    return await fallback_db.save_report({**existing, **updates})


async def delete_report(report_id: str) -> bool:
    """Delete a report."""
    if database._mongodb_available:
        result = await db.reports.delete_one({"id": report_id})
        return result.deleted_count > 0
    return await fallback_db.delete_report(report_id)
