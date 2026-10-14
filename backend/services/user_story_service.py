"""
Automatic User Story and Acceptance Criteria Generation Service for Milestone 3.
Transforms PRDs, feature clusters, or custom requirements into Agile User Stories
with Gherkin Acceptance Criteria, Fibonacci estimation, T-Shirt sizing, and Kanban status tracking.
"""

import os
import json
import re
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
from services.prd_service import build_document_evidence, get_prd_by_id
from services.text_mining import match_records_by_terms
from services.theme_extraction import _resolve_sentiment
import database
from database import db
import fallback_db

logger = logging.getLogger(__name__)

# The estimation scale this service documents. A model asked for Fibonacci points
# sometimes answers 11 or 12, and a board has no column for those — so the value is
# snapped to the nearest step instead of being passed through to the card.
STORY_POINT_SCALE = (1, 2, 3, 5, 8, 13)


def to_fibonacci_points(value: Any) -> int:
    """Snap a story's estimate onto the Fibonacci scale, defaulting when it is unusable."""
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return 3
    if raw != raw:  # NaN
        return 3
    return min(STORY_POINT_SCALE, key=lambda step: abs(step - raw))


def _normalise_phrase(text: str) -> str:
    """
    Make a model-written fragment read naturally inside the story sentence.

    Cards render "I want to {action}" and "so that {benefit}", but models often return
    sentence-style fragments ("Apply filters."). Leading capitals, a leading "to" and
    trailing periods are stripped; acronyms ("SSO ...") are left intact.
    """
    text = str(text or "").strip().rstrip(".")
    text = re.sub(r"^to\s+", "", text, flags=re.IGNORECASE).strip()
    if text[:1].isupper() and (len(text) < 2 or text[1:2].islower()):
        text = text[0].lower() + text[1:]
    return text


def _generate_fallback_stories(
    subject: str,
    prd_title: Optional[str] = None,
    count: int = 5,
    persona: Optional[str] = None,
    evidence: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Decompose a subject into stories using the workspace's own reports.

    Each story is one topic users actually wrote about, with acceptance criteria that can
    be checked against this workspace's feedback. Implementation details, technologies and
    effort estimates cannot be inferred from feedback, so they are marked as such rather
    than invented.
    """
    evidence = evidence or {}
    source_details = evidence.get("source_details") or {}
    records = evidence.get("records") or []
    stats = evidence.get("stats") or {}
    terms = [str(term) for term in (evidence.get("top_terms") or source_details.get("keywords") or []) if str(term).strip()]
    if not terms:
        terms = [subject]
    negative_count = int(evidence.get("negative_count") or 0)
    total_matched = int(stats.get("count") or 0)
    negative_share = (negative_count / total_matched) if total_matched else 0.0

    results = []
    for term in terms[:count]:
        term_records = match_records_by_terms(records, [term]) if records else []
        term_count = len(term_records)
        term_low = sum(1 for record in term_records if (record.get("rating") or 5) <= 2)
        term_negative = sum(1 for record in term_records if _resolve_sentiment(record) == "negative")
        share = (term_negative / term_count) if term_count else negative_share

        priority = "high" if share >= 0.5 else ("medium" if share >= 0.25 else "low")
        points = 8 if term_count >= 500 else (5 if term_count >= 100 else (3 if term_count >= 20 else 2))
        size = "L" if points >= 8 else ("M" if points >= 5 else ("S" if points >= 3 else "XS"))
        role = persona or "app user"
        action = f"see the {term} problems I reported resolved"
        benefit = "the app works the way I expect, without workarounds"

        results.append({
            "title": f"Resolve {term} friction",
            "role": role,
            "action": action,
            "benefit": benefit,
            "full_statement": f"As a {role}, I want {action}, so that {benefit}.",
            "acceptance_criteria": [
                {
                    "scenario": f"{term} reports stop recurring",
                    "given": f"this workspace holds {term_count} reports mentioning {term} ({term_negative} negative)",
                    "when": "the fix ships and the feedback is re-analysed",
                    "then": f"no new negative report mentioning {term} appears in the next analysis cycle",
                },
                {
                    "scenario": "Existing reports are accounted for",
                    "given": f"the {term_count} reports mentioning {term}",
                    "when": "the team closes this story",
                    "then": "each report is linked to the change that addressed it",
                },
            ],
            "story_points": points,
            "t_shirt_size": size,
            "priority": priority,
            "definition_of_done": [
                f"Reports mentioning {term} rated 2 or lower fall below the current {term_low}",
                "A workspace re-analysis shows the reported negative share has fallen",
                "No implementation detail is asserted here: effort and technology were not inferred from feedback",
            ],
            "technical_notes": (
                f"Not derivable from feedback: this workspace records {term_count} reports mentioning "
                f"{term} but no implementation detail. Story points and size are placeholders "
                f"pending engineering estimation."
            ),
        })

    if len(results) < count:
        # Topics beyond the ones users actually wrote about are filled with structural
        # stories (workflow, recovery, visibility) rather than fabricated capabilities.
        results.extend(_template_stories(subject, count - len(results), persona))
    return results[:count]


def _template_stories(subject: str, count: int = 5, persona: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Minimal starting point when a subject has no supporting feedback at all.

    Deliberately structural: it states the workflow the subject needs to support and
    leaves technology, effort and metrics open instead of inventing them.
    """
    target_role = persona or "app user"
    templates = [{
        "title": f"{subject}: primary flow",
        "action": f"complete the {subject} flow without hitting the friction reported in this workspace",
        "benefit": "I finish the task I came for",
        "priority": "high",
    }, {
        "title": f"{subject}: failure handling",
        "action": f"see what went wrong when the {subject} flow fails and retry it",
        "benefit": "I am not left without a recovery path",
        "priority": "medium",
    }, {
        "title": f"{subject}: progress visibility",
        "action": f"see whether the {subject} work I asked for is being handled",
        "benefit": "I know whether to wait or try something else",
        "priority": "medium",
    }]

    return [{
        "title": template["title"],
        "role": target_role,
        "action": template["action"],
        "benefit": template["benefit"],
        "full_statement": f"As a {target_role}, I want to {template['action']}, so that {template['benefit']}.",
        "acceptance_criteria": [{
            "scenario": "Primary flow verified against feedback",
            "given": f"a user attempts the {subject} flow",
            "when": "the change ships and this workspace is re-analysed",
            "then": "no new negative report about this flow appears in the next analysis cycle",
        }],
        "story_points": 3,
        "t_shirt_size": "S",
        "priority": template["priority"],
        "definition_of_done": [
            "A workspace re-analysis shows no new negative report for this flow",
            "No implementation detail is asserted: none is recorded in the feedback",
        ],
        "technical_notes": "Not derivable from feedback; to be estimated by the team.",
    } for template in templates[: max(1, min(count, len(templates)))]]




async def generate_user_stories_with_ai(
    workspace_id: str,
    prd_id: Optional[str] = None,
    feature_cluster_id: Optional[str] = None,
    custom_prompt: Optional[str] = None,
    count: int = 5,
    persona: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Generate Agile user stories with Gherkin acceptance criteria
    using Google Gemini with Groq and heuristic fallback.
    """
    count = max(1, min(count, 10))
    subject = custom_prompt or "Product Feature Enhancement"
    context_notes = []

    # 1. Gather context from PRD if provided
    prd_doc = None
    cluster_details: Optional[Dict[str, Any]] = None
    cached_insights = None
    if database._mongodb_available:
        cached_insights = await db.workspace_insights.find_one({"workspace_id": workspace_id})
    else:
        cached_insights = await fallback_db.get_workspace_insights(workspace_id)

    if prd_id:
        prd_doc = await get_prd_by_id(prd_id)
        if prd_doc:
            subject = prd_doc.get("title", subject)
            frs = prd_doc.get("functional_requirements", [])
            for fr in frs:
                context_notes.append(f"- Requirement {fr.get('id')}: {fr.get('title')} ({fr.get('description')})")
            if prd_doc.get("problem_statement"):
                context_notes.append(f"Problem Statement: {prd_doc.get('problem_statement')}")

    # 2. Gather context from Feature Cluster if provided
    if feature_cluster_id:
        for cluster in ((cached_insights or {}).get("feature_clusters") or []):
            if cluster.get("id") == feature_cluster_id:
                cluster_details = cluster
                subject = cluster.get("cluster_name", subject)
                context_notes.append(f"Feature Cluster Demand: {cluster.get('summary')}")
                sample_reqs = cluster.get("sample_requests", []) or cluster.get("distinct_sample_quotes", [])
                if sample_reqs:
                    context_notes.append("Customer Wishes: " + "; ".join(sample_reqs[:3]))
                break

    # A story request must say what to ground on. Without a resolved source the model
    # would invent a generic product backlog unrelated to this workspace's feedback.
    if prd_id and not prd_doc:
        raise ValueError(f"PRD {prd_id} was not found in this workspace.")
    if feature_cluster_id and not cluster_details:
        raise ValueError("That feature cluster was not found in this workspace's current analysis.")
    if not prd_doc and not cluster_details and not (custom_prompt or "").strip():
        raise ValueError("Choose a PRD or a feature cluster, or describe a custom topic.")

    evidence = await build_document_evidence(
        workspace_id,
        cached_insights if feature_cluster_id else None,
        subject,
        {"keywords": [str(term) for term in (cluster_details.get("keywords") or [])]} if cluster_details else {},
        [quote for quote in (cluster_details or {}).get("sample_requests", [])][:10],
        generation_method="AI provider",
    )

    context_str = "\n".join(context_notes) if context_notes else f"Decompose capability '{subject}' into sprint-ready stories."
    stats = evidence.get("stats") or {}
    measured_evidence = (
        f"- Records analysed in this workspace: {evidence.get('total_analyzed')}\n"
        f"- Records matching this topic: {stats.get('count')}\n"
        f"- Average rating of those records: {stats.get('avg_rating')}\n"
        f"- Negative reports among them: {evidence.get('negative_count')}\n"
        f"- Phrases users actually wrote: {', '.join(evidence.get('top_terms') or [])}"
    )

    prompt = f"""You are a Principal Agile Product Owner and Scrum Master.
Generate exactly {count} production-ready, vertical Agile User Stories for:
Topic / Subject: {subject}
Target Persona: {persona or 'End User / Product Practitioner'}

Measured evidence from this workspace (computed, do not contradict it):
{measured_evidence}

Context & Functional Requirements:
{context_str}

Return ONLY a valid JSON object matching this schema:
{{
  "stories": [
    {{
      "title": "Short punchy story title",
      "role": "Specific User Persona Role",
      "action": "bare lowercase verb phrase that follows 'I want to', e.g. 'apply multiple filters to my results'",
      "benefit": "clause that follows 'so that', e.g. 'I can find what I need without scrolling'",
      "acceptance_criteria": [
        {{
          "scenario": "Descriptive scenario name",
          "given": "precondition statement",
          "when": "user action or system trigger",
          "then": "observable verifiable outcome"
        }},
        {{
          "scenario": "Alternative or error flow",
          "given": "precondition statement",
          "when": "action occurs",
          "then": "observable verifiable outcome"
        }}
      ],
      "story_points": 3,
      "t_shirt_size": "S",
      "priority": "high",
      "definition_of_done": [
        "Unit test coverage >= 85%",
        "Accessibility checks passed",
        "API contract reviewed"
      ],
      "technical_notes": "Key backend endpoints, database schema changes, or UI state considerations"
    }}
  ]
}}

Rules:
- Provide exactly {count} distinct vertical user stories.
- 'action' must be a bare lowercase verb phrase with no leading 'to' and no trailing period.
- 'benefit' must be a full clause starting with 'I can' or similar, not a bare verb.
- Phrase 'action' as something the user wants to do or get (e.g. 'see at most one paywall per hour', 'play a specific song on demand'), never as something done to the user (e.g. 'receive pop-ups', 'be shown ads').
- Every story MUST have 2-3 Gherkin scenarios with 'given', 'when', 'then'.
- Story points MUST be Fibonacci: 1, 2, 3, 5, 8, or 13.
- T-shirt size MUST be: 'XS', 'S', 'M', 'L', or 'XL'.
- Priority MUST be: 'high', 'medium', or 'low'.
- Output strictly valid JSON.
"""

    parsed_stories = None
    ai_model_used = None

    # 1. Attempt Groq AI (Fastest, verified working)
    groq_client = get_groq_client()
    if groq_client:
        for m_name in GROQ_MODELS:
            try:
                logger.info(f"Attempting Groq story generation with {m_name}...")
                supports_json = m_name in ["allam-2-7b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
                response = groq_client.chat.completions.create(
                    model=m_name,
                    messages=[
                        {"role": "system", "content": "You are a Principal Agile Product Owner. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2500,
                    timeout=20,
                    response_format={"type": "json_object"} if supports_json else None
                )
                content = response.choices[0].message.content
                parsed = _extract_json_from_text(content)
                if parsed and "stories" in parsed and isinstance(parsed["stories"], list):
                    parsed_stories = parsed["stories"]
                    ai_model_used = f"Groq ({m_name})"
                    logger.info(f"Generated {len(parsed_stories)} user stories via Groq!")
                    break
            except Exception as e:
                logger.warning(f"Groq story error on {m_name}: {e}...")

    # 2. Attempt OpenRouter Free AI Fallback
    if not parsed_stories:
        openrouter_client = get_openrouter_client()
        if openrouter_client:
            for m_name in OPENROUTER_MODELS:
                try:
                    logger.info(f"Attempting OpenRouter story generation with {m_name}...")
                    response = openrouter_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are a Principal Agile Product Owner. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=OPENROUTER_MAX_TOKENS,
                        timeout=OPENROUTER_TIMEOUT_SECONDS,
                    )
                    content = response.choices[0].message.content
                    parsed = _extract_json_from_text(content)
                    if parsed and "stories" in parsed and isinstance(parsed["stories"], list):
                        parsed_stories = parsed["stories"]
                        ai_model_used = f"OpenRouter ({m_name})"
                        logger.info(f"Generated {len(parsed_stories)} user stories via OpenRouter!")
                        break
                except Exception as e:
                    logger.warning(f"OpenRouter story error on {m_name}: {e}...")

    # 3. Attempt Google Gemini Backup
    if not parsed_stories:
        gem_client = get_gemini_client()
        if gem_client:
            for g_model in GEMINI_MODELS:
                try:
                    from google.genai import types
                    logger.info(f"Generating user stories with Google Gemini model {g_model}...")
                    response = gem_client.models.generate_content(
                        model=g_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.25,
                            timeout=15,
                        ),
                    )
                    parsed = _extract_json_from_text(response.text)
                    if parsed and "stories" in parsed and isinstance(parsed["stories"], list):
                        parsed_stories = parsed["stories"]
                        ai_model_used = f"Google Gemini ({g_model})"
                        logger.info(f"Generated {len(parsed_stories)} user stories via Gemini!")
                        break
                except Exception as e:
                    logger.warning(f"Gemini story generation error on {g_model}: {e}. Retrying next...")

    # 4. Attempt Mistral AI Fallback (free Experiment tier, OpenAI-compatible)
    if not parsed_stories:
        mistral_client = get_mistral_client()
        if mistral_client:
            for m_name in MISTRAL_MODELS:
                try:
                    logger.info(f"Attempting Mistral story generation with {m_name}...")
                    response = mistral_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are a Principal Agile Product Owner. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=2500,
                        response_format={"type": "json_object"},
                        timeout=20,
                    )
                    content = response.choices[0].message.content
                    parsed = _extract_json_from_text(content)
                    if parsed and "stories" in parsed and isinstance(parsed["stories"], list):
                        parsed_stories = parsed["stories"]
                        ai_model_used = f"Mistral ({m_name})"
                        logger.info(f"Generated {len(parsed_stories)} user stories via Mistral!")
                        break
                except Exception as e:
                    logger.warning(f"Mistral story error on {m_name}: {e}...")

    # 3. Fallback Deterministic Engine
    if not parsed_stories:
        logger.info("Using fallback Agile story generator...")
        parsed_stories = _generate_fallback_stories(
            subject=subject,
            prd_title=prd_doc.get("title") if prd_doc else None,
            count=count,
            persona=persona,
            evidence=evidence,
        )

    # 4. Drop non-object entries, then top up from the deterministic engine so
    #    the caller always receives the requested number of usable stories.
    parsed_stories = [s for s in parsed_stories if isinstance(s, dict)]
    ai_story_count = len(parsed_stories)
    if len(parsed_stories) < count:
        logger.info(f"AI returned {len(parsed_stories)} of {count} stories; topping up deterministically.")
        parsed_stories.extend(_generate_fallback_stories(
            subject=subject,
            prd_title=prd_doc.get("title") if prd_doc else None,
            count=count,
            persona=persona,
            evidence=evidence,
        )[: count - len(parsed_stories)])

    # Save stories to Database
    now = datetime.now(timezone.utc)
    created_items = []
    
    for idx, s in enumerate(parsed_stories[:count]):
        story_id = f"us_{uuid.uuid4().hex[:10]}"
        # Stories after the AI batch were topped up by the deterministic engine, so each
        # story records its own provenance instead of inheriting the batch's model.
        story_is_ai = bool(ai_model_used) and idx < ai_story_count
        role = s.get("role", persona or "User")
        action = _normalise_phrase(s.get("action") or f"use {subject}")
        benefit = _normalise_phrase(s.get("benefit") or "I can improve my product experience")
        full_stmt = s.get("full_statement") or f"As a {role}, I want to {action}, so that {benefit}."

        doc: Dict[str, Any] = {
            "id": story_id,
            "workspace_id": workspace_id,
            "prd_id": prd_id,
            "feature_cluster_id": feature_cluster_id,
            "title": s.get("title", f"Story #{idx+1}: {subject}"),
            "role": role,
            "action": action,
            "benefit": benefit,
            "full_statement": full_stmt,
            "acceptance_criteria": s.get("acceptance_criteria", []),
            "story_points": to_fibonacci_points(s.get("story_points", 3)),
            "t_shirt_size": s.get("t_shirt_size", "M"),
            "priority": s.get("priority", "medium"),
            "status": "backlog",
            "definition_of_done": s.get("definition_of_done", ["Unit tests written", "Code reviewed"]),
            "technical_notes": s.get("technical_notes", ""),
            # True only when a model actually wrote this story; the deterministic engine
            # must not claim AI authorship.
            "ai_generated": story_is_ai,
            "ai_model": ai_model_used if story_is_ai else "Deterministic evidence engine",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        created_items.append(doc)

    if database._mongodb_available:
        if created_items:
            await db.user_stories.insert_many([dict(item) for item in created_items])
    else:
        await fallback_db.bulk_save_stories([dict(item) for item in created_items])

    return created_items


async def get_stories_for_workspace(
    workspace_id: str,
    prd_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve user stories belonging to a workspace with optional PRD filter."""
    if database._mongodb_available:
        query: Dict[str, Any] = {"workspace_id": workspace_id}
        if prd_id:
            query["prd_id"] = prd_id
        cursor = db.user_stories.find(query).sort("created_at", -1)
        records = await cursor.to_list(length=None)
        for r in records:
            if "_id" in r:
                r["_id"] = str(r["_id"])
        return records
    else:
        return await fallback_db.find_stories_by_workspace(workspace_id, prd_id=prd_id)


async def get_story_by_id(story_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve single user story by ID."""
    if database._mongodb_available:
        story = await db.user_stories.find_one({"id": story_id})
        if story and "_id" in story:
            story["_id"] = str(story["_id"])
        return story
    else:
        return await fallback_db.find_story_by_id(story_id)


async def update_story(story_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update user story fields."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    if database._mongodb_available:
        await db.user_stories.update_one({"id": story_id}, {"$set": updates})
        return await get_story_by_id(story_id)
    else:
        return await fallback_db.update_story(story_id, updates)


async def update_story_status(story_id: str, status: str) -> Optional[Dict[str, Any]]:
    """Quick update of Kanban status (backlog, in_progress, in_review, done)."""
    return await update_story(story_id, {"status": status})


async def delete_story(story_id: str) -> bool:
    """Delete a user story."""
    if database._mongodb_available:
        res = await db.user_stories.delete_one({"id": story_id})
        return res.deleted_count > 0
    else:
        return await fallback_db.delete_story(story_id)
