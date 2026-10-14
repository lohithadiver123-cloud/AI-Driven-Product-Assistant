"""
Conversational Product Intelligence Assistant (PM Copilot) Service for Milestone 3.
Provides grounded, multi-turn AI chat answering complex product management questions
by dynamically retrieving context from ingested customer feedback, themes, pain points,
PRDs, and feature prioritization rankings.
"""

import os
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from config import settings
from services.ai_service import (
    get_gemini_client,
    get_groq_client,
    get_mistral_client,
    get_openrouter_client,
    _extract_json_from_text,
    GEMINI_MODELS,
    GROQ_MODELS,
    MISTRAL_MODELS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    OPENROUTER_TIMEOUT_SECONDS,
)
from services.prd_service import get_prds_for_workspace
from services.user_story_service import get_stories_for_workspace
import database
from database import db
import fallback_db

logger = logging.getLogger(__name__)


import time
import asyncio

_copilot_context_cache: dict = {}  # ws_id -> (context_dict, expires_at)


async def build_workspace_pm_context(workspace_id: str) -> Dict[str, Any]:
    """
    Assemble complete product knowledge base for the workspace:
    - Feedback count & sentiment breakdown
    - Top Themes
    - Customer Pain Points with root causes
    - Feature Clusters with priority scores
    - Existing PRD titles
    - High-frequency customer quotes
    Cached in-memory for 60s and fetched concurrently via asyncio.gather.
    """
    now = time.time()
    cached_entry = _copilot_context_cache.get(workspace_id)
    if cached_entry and cached_entry[1] > now:
        return cached_entry[0]

    context: Dict[str, Any] = {
        "workspace_id": workspace_id,
        "total_feedback": 0,
        "themes": [],
        "pain_points": [],
        "feature_clusters": [],
        "sample_quotes": [],
        "existing_prds": [],
        "user_stories_count": 0,
    }

    async def _fetch_insights():
        if database._mongodb_available:
            return await db.workspace_insights.find_one({"workspace_id": workspace_id})
        return await fallback_db.get_workspace_insights(workspace_id)

    async def _fetch_feedback_quotes():
        if database._mongodb_available:
            cursor = db.feedback.find({"workspace_id": workspace_id}).sort("created_at", -1).limit(12)
            return await cursor.to_list(length=12)
        records = await fallback_db.find_all_feedback_by_workspace(workspace_id)
        return records[:12]

    async def _fetch_prioritization():
        try:
            from services.prioritization_service import get_prioritization_items
            return await get_prioritization_items(workspace_id)
        except Exception:
            return []

    async def _fetch_roadmap():
        try:
            from services.roadmap_service import get_roadmap
            return await get_roadmap(workspace_id)
        except Exception:
            return None

    # Run queries concurrently in parallel
    cached_insights, records, prds, stories, p_items, roadmap = await asyncio.gather(
        _fetch_insights(),
        _fetch_feedback_quotes(),
        get_prds_for_workspace(workspace_id),
        get_stories_for_workspace(workspace_id),
        _fetch_prioritization(),
        _fetch_roadmap(),
        return_exceptions=True,
    )

    # 1. Insights
    if isinstance(cached_insights, dict) and cached_insights:
        context["total_feedback"] = cached_insights.get("total_analyzed", 0)
        context["health_score"] = cached_insights.get("health_score", 65.0)
        context["sentiment_distribution"] = cached_insights.get("sentiment_distribution", {})
        
        for t in cached_insights.get("themes", [])[:5]:
            context["themes"].append(f"{t.get('title')} ({t.get('frequency', 0)} mentions, {t.get('category')})")
            
        for pp in cached_insights.get("pain_points", [])[:5]:
            context["pain_points"].append({
                "id": pp.get("id"),
                "title": pp.get("title"),
                "severity": pp.get("severity"),
                "impact_score": pp.get("impact_score"),
                "root_cause": pp.get("root_cause"),
                "action": pp.get("recommended_action"),
                "sample_quote": (pp.get("sample_quotes") or [""])[0][:120]
            })
            
        for fc in cached_insights.get("feature_clusters", [])[:5]:
            context["feature_clusters"].append({
                "id": fc.get("id"),
                "name": fc.get("cluster_name"),
                "demand": fc.get("demand_level"),
                "priority_score": fc.get("priority_score"),
                "summary": fc.get("summary")
            })

    # 2. Feedback Quotes
    if isinstance(records, list):
        for r in records:
            txt = r.get("content", "")
            if txt and len(txt) > 15:
                rating = f"[{r.get('rating')}★] " if r.get("rating") else ""
                context["sample_quotes"].append(f"{rating}\"{txt[:140]}\"")

    # 3. Existing PRDs & Stories
    if isinstance(prds, list):
        context["existing_prds"] = [p.get("title") for p in prds]
    if isinstance(stories, list):
        context["user_stories_count"] = len(stories)

    # 4. Prioritization
    if isinstance(p_items, list):
        context["prioritization_items"] = [
            {
                "name": p.get("name"),
                "category": p.get("category"),
                "rice_score": p.get("rice", {}).get("score", 0),
                "quadrant": p.get("value_vs_effort", {}).get("quadrant", "quick_win"),
                "moscow": p.get("moscow", "should_have"),
                "rank": p.get("rank", 1),
            }
            for p in p_items[:8]
        ]
    else:
        context["prioritization_items"] = []

    # 5. Roadmap Releases
    if isinstance(roadmap, dict) and "releases" in roadmap:
        context["roadmap_releases"] = [
            {
                "name": r.get("name"),
                "horizon": r.get("horizon", "next"),
                "items": [it.get("name") for it in r.get("items", [])[:3]],
            }
            for r in roadmap.get("releases", [])[:4]
        ]
    else:
        context["roadmap_releases"] = []

    if len(_copilot_context_cache) > 200:
        _copilot_context_cache.clear()
    _copilot_context_cache[workspace_id] = (context, now + 60.0)

    return context


# Displayed whenever the deterministic engine answers instead of an AI model, so the
# user always knows whether they are reading model output or the workspace's own data.
FALLBACK_DISCLOSURE = (
    "Answered by the deterministic engine (no AI provider reachable): every number above "
    "comes from this workspace's stored analysis."
)


def _generate_fallback_chat_reply(message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Context-aware PM assistance built from the workspace's own analysis when AI is down."""
    msg_lower = message.lower()
    total_fb = context.get("total_feedback", 0)
    pain_points = context.get("pain_points", [])
    clusters = context.get("feature_clusters", [])
    themes = context.get("themes", [])

    sources = []
    followups = [
        "What are our highest severity pain points?",
        "Which feature has the highest priority score?",
        "Draft a PRD for the most requested feature",
        "Summarize recent negative customer feedback",
    ][: (2 if not pain_points and not clusters else 4)]
    action = None

    if any(k in msg_lower for k in ["pain", "complain", "issue", "bug", "crash", "problem", "frustrat", "friction"]):
        pp_list = "\n".join([f"- **{p['title']}** (Severity: `{p['severity'].upper()}`, Impact: `{p['impact_score']}`)\n  *Root Cause:* {p.get('root_cause', 'N/A')}\n  *Action:* {p.get('action', 'N/A')}" for p in pain_points[:3]]) if pain_points else "No active pain points recorded."
        reply = (
            f"### Top Customer Pain Points & Friction Analysis\n\n"
            f"From **{total_fb:,} analysed feedback records** in this workspace, ranked by measured impact:\n\n"
            f"{pp_list}\n\n"
            f"> {FALLBACK_DISCLOSURE}"
        )
        top_p = pain_points[0] if pain_points else {}
        for p in pain_points[:2]:
            sources.append({"type": "pain_point", "title": p["title"], "detail": f"Impact Score: {p.get('impact_score')}"})
        action = {
            "action_type": "add_to_backlog",
            "label": f"Add to Backlog: Fix {top_p.get('title', 'Top Issue')[:30]}",
            "payload": {
                "name": f"Fix: {top_p.get('title', 'Top Issue')}",
                "description": top_p.get("root_cause") or f"Resolve customer friction in {top_p.get('title')}",
                "category": "bug_fix",
                "reach": 850.0,
                "impact": 2.0,
                "confidence": 0.8,
                "effort": 2.0,
                "moscow": "must_have",
                "pain_point_id": top_p.get("id"),
                "prompt": f"Resolve friction in {top_p.get('title')}: {top_p.get('root_cause', '')}",
            },
        }

    elif any(k in msg_lower for k in ["story", "stories", "agile", "sprint"]):
        top_c = clusters[0] if clusters else {}
        reply = (
            f"### Agile User Story Breakdown Readiness\n\n"
            f"Based on customer demand clusters, the most requested feature to break down into sprint stories is **{top_c.get('name', 'Top Requested Feature')}**.\n\n"
            f"> {FALLBACK_DISCLOSURE}"
        )
        action = {
            "action_type": "generate_stories",
            "label": f"Generate User Stories for {top_c.get('name', 'Top Feature')[:30]}",
            "payload": {
                "prompt": f"User stories with Gherkin criteria for: {top_c.get('name', 'Top Feature')}. Context: {top_c.get('summary', '')}",
                "persona": "End User",
                "count": 5,
                "cluster_id": top_c.get("id"),
            },
        }

    elif any(k in msg_lower for k in ["feature", "request", "cluster", "build", "opportunity", "want", "wish"]):
        fc_list = "\n".join([f"- **{c['name']}** (Demand: `{c['demand'].upper()}`, Priority Score: `{c['priority_score']}`)\n  *{c.get('summary', '')}*" for c in clusters[:3]]) if clusters else "No feature clusters recorded."
        reply = (
            f"### Top Requested Features & Product Opportunities\n\n"
            f"The **{total_fb:,} analysed records** in this workspace group into these demand areas:\n\n"
            f"{fc_list}\n\n"
            f"> {FALLBACK_DISCLOSURE}"
        )
        top_c = clusters[0] if clusters else {}
        for c in clusters[:2]:
            sources.append({"type": "feature_cluster", "title": c["name"], "detail": f"Priority Score: {c.get('priority_score')}"})
        action = {
            "action_type": "add_to_backlog",
            "label": f"Add to Backlog: {top_c.get('name', 'Top Feature')[:30]}",
            "payload": {
                "name": top_c.get("name", "Top Feature"),
                "description": top_c.get("summary") or top_c.get("name", ""),
                "category": "feature_request",
                "reach": 1200.0,
                "impact": 2.0,
                "confidence": 0.8,
                "effort": 3.0,
                "moscow": "should_have",
                "feature_cluster_id": top_c.get("id"),
                "prompt": f"Implement {top_c.get('name')}: {top_c.get('summary', '')}",
            },
        }

    elif any(k in msg_lower for k in ["priority", "prioritiz", "rice", "backlog", "score", "rank"]):
        p_items = context.get("prioritization_items", [])
        if p_items:
            ranked_list = "\n".join([
                f"- **#{p.get('rank', i+1)} {p['name']}** — RICE: `{p.get('rice_score', 0)}`, MoSCoW: `{str(p.get('moscow', '')).upper()}`, Quadrant: `{str(p.get('quadrant', '')).replace('_', ' ').capitalize()}`"
                for i, p in enumerate(p_items[:5])
            ])
            top_p = p_items[0]
            reply = (
                f"### Prioritized Feature Backlog (Ranked by Measured Impact)\n\n"
                f"Based on customer reach, severity, and confidence weighting, here are the top initiatives in your backlog:\n\n"
                f"{ranked_list}\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )
            for p in p_items[:2]:
                sources.append({"type": "prioritization", "title": p["name"], "detail": f"RICE: {p.get('rice_score')} · {p.get('moscow')}"})
            action = {
                "action_type": "generate_stories",
                "label": f"Break #{top_p.get('rank', 1)} into Stories: {top_p['name'][:28]}",
                "payload": {
                    "prompt": f"User stories and Gherkin acceptance criteria for highest-priority initiative: {top_p['name']}",
                    "persona": "Product User",
                    "count": 5,
                },
            }
        else:
            reply = (
                f"### Prioritization Readiness\n\n"
                f"No items have been seeded into the backlog yet. Go to **Prioritization Hub** to auto-seed from customer demand clusters.\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )

    elif any(k in msg_lower for k in ["roadmap", "horizon", "release", "milestone", "schedule", "when"]):
        releases = context.get("roadmap_releases", [])
        if releases:
            rel_str = "\n".join([
                f"- **{r['name']}** (`{r.get('horizon', 'next').upper()}` horizon): {', '.join(r.get('items', [])) if r.get('items') else 'Unscheduled'}"
                for r in releases
            ])
            reply = (
                f"### Sequenced Product Roadmap\n\n"
                f"Here is how your backlog is currently staged across release windows:\n\n"
                f"{rel_str}\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )
            for r in releases[:2]:
                sources.append({"type": "roadmap", "title": r["name"], "detail": f"Horizon: {r.get('horizon')}"})
        else:
            reply = (
                f"### Roadmap Status\n\n"
                f"A sequenced roadmap has not been generated for this workspace yet. You can plan one in **Roadmap Planner** based on team velocity.\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )

    elif any(k in msg_lower for k in ["quote", "harsh", "verbatim", "customer say", "what users say"]):
        quotes = context.get("sample_quotes", [])
        if quotes:
            q_list = "\n".join([f"- {q}" for q in quotes[:5]])
            reply = (
                f"### Direct Customer Voice (Verbatim Feedback Excerpts)\n\n"
                f"Here are recent customer quotes extracted from your imported records:\n\n"
                f"{q_list}\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )
            for q in quotes[:3]:
                sources.append({"type": "feedback_quote", "title": q[:50] + "...", "detail": "Customer review"})
            top_p = pain_points[0] if pain_points else {}
            if top_p:
                action = {
                    "action_type": "add_to_backlog",
                    "label": f"Add fix to Backlog: {top_p.get('title', 'Top Pain Point')[:28]}",
                    "payload": {
                        "name": f"Resolve: {top_p.get('title')}",
                        "description": top_p.get("root_cause") or "Fix customer friction",
                        "category": "bug_fix",
                        "reach": 900.0,
                        "impact": 2.5,
                        "effort": 2.0,
                        "moscow": "must_have",
                    },
                }
        else:
            reply = (
                f"### Customer Quotes\n\n"
                f"No feedback records found to extract quotes from in this workspace.\n\n"
                f"> {FALLBACK_DISCLOSURE}"
            )

    elif any(k in msg_lower for k in ["prd", "requirement", "spec", "document"]):
        top_c = clusters[0] if clusters else {}
        reply = (
            f"### PRD Generation Readiness\n\n"
            f"This workspace has **{len(clusters)} demand clusters** and **{len(pain_points)} ranked "
            f"pain points** that a document can be grounded on.\n\n"
            f"Click below to generate a comprehensive PRD for **{top_c.get('name', 'our top feature opportunity')}**.\n\n"
            f"> {FALLBACK_DISCLOSURE}"
        )
        action = {
            "action_type": "create_prd",
            "label": f"Generate PRD: {top_c.get('name', 'Top Opportunity')[:30]}",
            "payload": {
                "title": f"PRD: {top_c.get('name', 'Top Opportunity')}",
                "prompt": f"Write a comprehensive PRD for {top_c.get('name', 'Top Opportunity')}. Context: {top_c.get('summary', '')}",
                "feature_cluster_id": top_c.get("id"),
                "sourceType": "feature_cluster" if top_c else "custom",
            },
        }

    else:
        top_th = ", ".join(themes[:3]) if themes else "none yet — run the analysis on this workspace"
        p_items = context.get("prioritization_items", [])
        top_backlog_name = p_items[0]["name"] if p_items else (clusters[0]["name"] if clusters else None)
        reply = (
            f"### Workspace Overview & Product Intelligence\n\n"
            f"This workspace holds **{total_fb:,} analysed feedback records**.\n\n"
            f"- **Themes:** {top_th}\n"
            f"- **Pain points:** {len(pain_points)} ranked by measured impact\n"
            f"- **Demand clusters:** {len(clusters)} grouped from customer needs\n"
            f"- **Backlog items:** {len(p_items)} scored across RICE & MoSCoW\n"
            f"- **PRDs:** {len(context.get('existing_prds', []))} authored in this workspace\n\n"
            f"Ask me about sentiment, prioritisation, roadmap releases, user stories, or direct quotes.\n\n"
            f"> {FALLBACK_DISCLOSURE}"
        )
        if top_backlog_name:
            action = {
                "action_type": "add_to_backlog",
                "label": f"Add to Backlog: {top_backlog_name[:30]}",
                "payload": {
                    "name": top_backlog_name,
                    "description": "Customer demand initiative",
                    "category": "feature_request",
                    "reach": 1000.0,
                    "impact": 2.0,
                    "confidence": 0.8,
                    "effort": 2.0,
                    "moscow": "should_have",
                },
            }

    return {
        "reply": reply,
        "sources_cited": sources,
        "suggested_followups": followups,
        "action_suggested": action,
        "ai_model": "PM Copilot Intelligence Engine"
    }


async def chat_with_pm_copilot(
    workspace_id: str,
    message: str,
    session_id: str = "default",
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Execute conversational product intelligence using Google Gemini (Pure AI)
    grounded in workspace customer feedback and requirements context.
    """
    context = await build_workspace_pm_context(workspace_id)
    history = conversation_history or []

    # Format history turns
    history_formatted = ""
    for h in history[-6:]:
        role = "User" if h.get("sender") == "user" or h.get("role") == "user" else "Copilot"
        history_formatted += f"{role}: {h.get('content') or h.get('text', '')}\n"

    prompt = f"""You are the PM Copilot — a Principal AI Product Manager and Intelligence Assistant.
You have real-time access to customer feedback data, issue tickets, feature requests, and PRDs for this product workspace.

WORKSPACE KNOWLEDGE BASE:
- Total Analyzed Customer Feedback Items: {context.get('total_feedback', 0):,}
- Sentiment Health Score: {context.get('health_score', 65.0)}/100
- Dominant Themes: {'; '.join(context.get('themes', []))}
- Critical Customer Pain Points: {json.dumps(context.get('pain_points', []), indent=1)}
- Clustered Feature Opportunities: {json.dumps(context.get('feature_clusters', []), indent=1)}
- Prioritized Backlog (RICE & MoSCoW): {json.dumps(context.get('prioritization_items', []), indent=1)}
- Sequenced Roadmap Releases: {json.dumps(context.get('roadmap_releases', []), indent=1)}
- Real Customer Quotes:
{chr(10).join(context.get('sample_quotes', [])[:8])}
- Existing Workspace PRDs: {', '.join(context.get('existing_prds', [])) or 'None created yet'}

RECENT CONVERSATION:
{history_formatted}

CURRENT USER QUERY:
"{message}"

INSTRUCTIONS:
1. Respond as an insightful, data-driven Principal Product Manager.
2. Ground all answers 100% in the real customer data, pain points, quotes, and metrics above.
3. Structure your answer using clear Markdown (headings, bullet points, callout blocks).
4. Identify which pain points, feature clusters, or customer quotes you cited.
5. Provide 3-4 natural follow-up prompt questions the user might ask next.

Return ONLY a valid JSON object matching this schema:
{{
  "reply": "Rich markdown text response...",
  "sources_cited": [
    {{"type": "pain_point", "title": "Pain point name", "detail": "Impact Score: 88"}},
    {{"type": "feature_cluster", "title": "Feature cluster name", "detail": "Priority Score: 92"}},
    {{"type": "feedback_quote", "title": "Customer quote excerpt", "detail": "Rating / source"}}
  ],
  "suggested_followups": [
    "Suggested question 1?",
    "Suggested question 2?",
    "Suggested question 3?"
  ],
  "action_suggested": {{
    "action_type": "add_to_backlog | create_prd | generate_stories",
    "label": "Button label e.g. 'Add to Backlog' or 'Generate PRD'",
    "payload": {{
      "name": "Feature or Initiative Title",
      "title": "PRD Title",
      "description": "Brief summary",
      "prompt": "Detailed prompt for generator",
      "category": "feature_request | bug_fix | performance | security",
      "reach": 1000,
      "impact": 2.0,
      "effort": 2.0,
      "moscow": "should_have"
    }}
  }}
}}
"""

    parsed_res = None
    ai_model_name = "AI Provider"

    # 1. Attempt Groq AI (Fastest, verified working)
    groq_client = get_groq_client()
    if groq_client:
        for m_name in GROQ_MODELS:
            try:
                logger.info(f"Attempting Groq PM Copilot chat using {m_name}...")
                supports_json = m_name in ["allam-2-7b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
                response = groq_client.chat.completions.create(
                    model=m_name,
                    messages=[
                        {"role": "system", "content": "You are the PM Copilot. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2200,
                    timeout=20,
                    response_format={"type": "json_object"} if supports_json else None
                )
                content = response.choices[0].message.content
                parsed = _extract_json_from_text(content)
                if parsed and "reply" in parsed:
                    parsed_res = parsed
                    ai_model_name = f"Groq ({m_name})"
                    break
            except Exception as e:
                logger.warning(f"Groq Copilot chat error on {m_name}: {e}...")

    # 2. Attempt OpenRouter Free AI Fallback
    if not parsed_res:
        openrouter_client = get_openrouter_client()
        if openrouter_client:
            for m_name in OPENROUTER_MODELS:
                try:
                    logger.info(f"Attempting OpenRouter PM Copilot chat using {m_name}...")
                    response = openrouter_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are the PM Copilot. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=OPENROUTER_MAX_TOKENS,
                        timeout=OPENROUTER_TIMEOUT_SECONDS,
                    )
                    content = response.choices[0].message.content
                    parsed = _extract_json_from_text(content)
                    if parsed and "reply" in parsed:
                        parsed_res = parsed
                        ai_model_name = f"OpenRouter ({m_name})"
                        break
                except Exception as e:
                    logger.warning(f"OpenRouter Copilot chat error on {m_name}: {e}...")

    # 3. Attempt Google Gemini Backup
    if not parsed_res:
        gem_client = get_gemini_client()
        if gem_client:
            for g_model in GEMINI_MODELS:
                try:
                    from google.genai import types
                    logger.info(f"Querying PM Copilot with Google Gemini model {g_model}...")
                    response = gem_client.models.generate_content(
                        model=g_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.3,
                            timeout=15,
                        ),
                    )
                    parsed = _extract_json_from_text(response.text)
                    if parsed and "reply" in parsed:
                        parsed_res = parsed
                        ai_model_name = f"Google Gemini ({g_model})"
                        break
                except Exception as e:
                    logger.warning(f"Gemini Copilot chat error on {g_model}: {e}. Retrying next...")

    # 4. Fallback to Mistral (free Experiment tier, OpenAI-compatible) if others fail
    if not parsed_res:
        mistral_client = get_mistral_client()
        if mistral_client:
            for m_name in MISTRAL_MODELS:
                try:
                    logger.info(f"Attempting Mistral PM Copilot chat using {m_name}...")
                    response = mistral_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are the PM Copilot. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.3,
                        max_tokens=2200,
                        response_format={"type": "json_object"},
                        timeout=20,
                    )
                    content = response.choices[0].message.content
                    parsed = _extract_json_from_text(content)
                    if parsed and "reply" in parsed:
                        parsed_res = parsed
                        ai_model_name = f"Mistral ({m_name})"
                        break
                except Exception as e:
                    logger.warning(f"Mistral Copilot chat error on {m_name}: {e}...")

    # Fallback to deterministic response
    if not parsed_res:
        logger.info("Using fallback PM Copilot response generator...")
        parsed_res = _generate_fallback_chat_reply(message, context)
        ai_model_name = parsed_res.get("ai_model", "PM Copilot Intelligence")

    # Save to Chat History
    now = datetime.now(timezone.utc)
    user_msg_doc = {
        "id": f"msg_{uuid.uuid4().hex[:10]}",
        "workspace_id": workspace_id,
        "session_id": session_id,
        "sender": "user",
        "content": message,
        "created_at": now.isoformat(),
    }
    copilot_msg_doc = {
        "id": f"msg_{uuid.uuid4().hex[:10]}",
        "workspace_id": workspace_id,
        "session_id": session_id,
        "sender": "assistant",
        "content": parsed_res.get("reply", ""),
        "sources_cited": parsed_res.get("sources_cited", []),
        "suggested_followups": parsed_res.get("suggested_followups", []),
        "action_suggested": parsed_res.get("action_suggested"),
        "created_at": now.isoformat(),
    }

    if database._mongodb_available:
        await db.copilot_messages.insert_many([user_msg_doc, copilot_msg_doc])
    else:
        await fallback_db.save_copilot_message(user_msg_doc)
        await fallback_db.save_copilot_message(copilot_msg_doc)

    return {
        "reply": parsed_res.get("reply", ""),
        "session_id": session_id,
        "sources_cited": parsed_res.get("sources_cited", []),
        "suggested_followups": parsed_res.get("suggested_followups", []),
        "action_suggested": parsed_res.get("action_suggested"),
        "context_summary": {
            "total_feedback": context.get("total_feedback", 0),
            "themes_count": len(context.get("themes", [])),
            "pain_points_count": len(context.get("pain_points", [])),
            "clusters_count": len(context.get("feature_clusters", [])),
        },
        "ai_model": ai_model_name,
        "timestamp": now.isoformat(),
    }


async def get_copilot_history(workspace_id: str, session_id: str = "default") -> List[Dict[str, Any]]:
    """Retrieve chat message history for a workspace session."""
    if database._mongodb_available:
        cursor = db.copilot_messages.find({"workspace_id": workspace_id, "session_id": session_id}).sort("created_at", 1)
        records = await cursor.to_list(length=100)
        for r in records:
            if "_id" in r:
                r["_id"] = str(r["_id"])
        return records
    else:
        return await fallback_db.get_copilot_history(workspace_id, session_id)


async def clear_copilot_history(workspace_id: str, session_id: str = "default") -> bool:
    """Clear chat history for a workspace session."""
    if database._mongodb_available:
        res = await db.copilot_messages.delete_many({"workspace_id": workspace_id, "session_id": session_id})
        return res.deleted_count > 0
    else:
        return await fallback_db.clear_copilot_history(workspace_id, session_id)
