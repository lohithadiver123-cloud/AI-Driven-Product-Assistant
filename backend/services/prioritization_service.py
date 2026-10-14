"""
Feature Prioritization and Impact Analysis Service for Milestone 3.
Implements:
1. RICE Framework (Reach * Impact * Confidence / Effort)
2. Value vs Effort (2x2 Matrix Quadrants)
3. MoSCoW Categorization (Must, Should, Could, Won't have)
4. Configurable Multi-Factor Weighted Scoring Framework
5. AI-Assisted Auto-Scoring from Customer Feedback
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
import database
from database import db
import fallback_db

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {
    "customer_demand_weight": 0.35,
    "business_impact_weight": 0.30,
    "feasibility_weight": 0.20,
    "risk_mitigation_weight": 0.15,
}


def _determine_quadrant(value: float, effort: float) -> str:
    """Determine the 2x2 Value vs Effort matrix quadrant."""
    if value >= 5.0:
        return "quick_win" if effort < 5.0 else "major_project"
    else:
        return "fill_in" if effort < 5.0 else "thankless_task"


def _calculate_rice(reach: float, impact: float, confidence: float, effort: float) -> float:
    """Calculate RICE score: (Reach * Impact * Confidence) / Effort."""
    safe_effort = max(0.5, effort)
    safe_confidence = min(1.0, max(0.1, confidence))
    return round((reach * impact * safe_confidence) / safe_effort, 1)


def _calculate_weighted_score(
    demand: float,
    impact: float,
    feasibility: float,
    risk: float,
    weights: Dict[str, float],
) -> float:
    """Calculate aggregate normalized score (0-100) using configurable weights."""
    w_dem = weights.get("customer_demand_weight", 0.35)
    w_imp = weights.get("business_impact_weight", 0.30)
    w_fea = weights.get("feasibility_weight", 0.20)
    w_rsk = weights.get("risk_mitigation_weight", 0.15)

    total_w = w_dem + w_imp + w_fea + w_rsk
    if total_w <= 0:
        total_w = 1.0

    score = (demand * w_dem + impact * w_imp + feasibility * w_fea + risk * w_rsk) / total_w
    return round(min(100.0, max(0.0, score)), 1)


def compute_all_scores_for_item(item: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """Recalculate RICE, Value vs Effort, and Weighted aggregate for an item."""
    rice = item.get("rice", {})
    reach = float(rice.get("reach", 500.0))
    impact = float(rice.get("impact", 1.0))
    confidence = float(rice.get("confidence", 0.8))
    effort = float(rice.get("effort", 2.0))
    rice_score = _calculate_rice(reach, impact, confidence, effort)

    v_vs_e = item.get("value_vs_effort", {})
    val = float(v_vs_e.get("value", 7.0))
    eff = float(v_vs_e.get("effort", 4.0))
    quadrant = _determine_quadrant(val, eff)

    weighted = item.get("weighted", {})
    dem_score = float(weighted.get("customer_demand_score", 70.0))
    imp_score = float(weighted.get("business_impact_score", 75.0))
    fea_score = float(weighted.get("feasibility_score", 65.0))
    rsk_score = float(weighted.get("risk_mitigation_score", 60.0))
    final_weighted = _calculate_weighted_score(dem_score, imp_score, fea_score, rsk_score, weights)

    item["rice"] = {
        "reach": reach,
        "impact": impact,
        "confidence": confidence,
        "effort": effort,
        "score": rice_score,
    }
    item["value_vs_effort"] = {
        "value": val,
        "effort": eff,
        "quadrant": quadrant,
    }
    item["weighted"] = {
        "customer_demand_score": dem_score,
        "business_impact_score": imp_score,
        "feasibility_score": fea_score,
        "risk_mitigation_score": rsk_score,
        "final_score": final_weighted,
    }
    return item


async def get_or_create_workspace_weights(workspace_id: str) -> Dict[str, Any]:
    """Retrieve custom framework weights for a workspace, initializing defaults if absent."""
    if database._mongodb_available:
        rec = await db.prioritization_weights.find_one({"workspace_id": workspace_id})
        if rec:
            if "_id" in rec:
                rec["_id"] = str(rec["_id"])
            return rec
    else:
        rec = await fallback_db.get_workspace_weights(workspace_id)
        if rec:
            return rec

    doc = {
        "workspace_id": workspace_id,
        **DEFAULT_WEIGHTS,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if database._mongodb_available:
        await db.prioritization_weights.insert_one(dict(doc))
    else:
        await fallback_db.save_workspace_weights(dict(doc))
    return doc


async def save_workspace_weights(workspace_id: str, new_weights: Dict[str, float]) -> Dict[str, Any]:
    """Update workspace custom prioritization weights and re-rank items."""
    clean_weights = {
        "customer_demand_weight": float(new_weights.get("customer_demand_weight", 0.35)),
        "business_impact_weight": float(new_weights.get("business_impact_weight", 0.30)),
        "feasibility_weight": float(new_weights.get("feasibility_weight", 0.20)),
        "risk_mitigation_weight": float(new_weights.get("risk_mitigation_weight", 0.15)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if database._mongodb_available:
        await db.prioritization_weights.update_one(
            {"workspace_id": workspace_id},
            {"$set": clean_weights},
            upsert=True
        )
    else:
        await fallback_db.save_workspace_weights({"workspace_id": workspace_id, **clean_weights})

    # Recalculate all items for this workspace
    items = await get_prioritization_items(workspace_id)
    for it in items:
        compute_all_scores_for_item(it, clean_weights)
        await update_prioritization_item(it["id"], it)

    return await get_or_create_workspace_weights(workspace_id)


# Effort is the one RICE input customer feedback cannot supply. Seeded items carry an
# explicit placeholder until a person (or engineering) replaces it, and they say so.
DEFAULT_SEED_EFFORT = 2.0


def measured_priority_inputs(count: int, urgency: str) -> Dict[str, Any]:
    """
    RICE inputs derived from what the workspace measured.

    Reach is the number of customers the analysis actually attributed to the topic. The
    earlier version multiplied a sample count by 45-50, which invented the reach and made
    the RICE score a restatement of volume — a number a reviewer can neither verify nor
    defend. Impact and confidence are also differentiated from measured volume and severity
    instead of being pinned at 3.0 and 0.85 for every item in the backlog.
    """
    count = max(int(count or 0), 0)
    urgency = str(urgency or "").lower()
    if urgency not in ("high", "medium", "low"):
        urgency = "medium"

    if urgency == "high" and count >= 200:
        impact = 3.0
    elif urgency == "high" and count >= 50:
        impact = 2.0
    elif urgency == "high":
        impact = 1.0
    elif urgency == "medium":
        impact = 1.0
    else:
        impact = 0.5

    if count >= 500:
        confidence = 0.9
    elif count >= 200:
        confidence = 0.85
    elif count >= 50:
        confidence = 0.8
    else:
        confidence = 0.7

    if urgency == "high" and count >= 100:
        moscow = "must_have"
    elif urgency == "high" or count >= 100:
        moscow = "should_have"
    else:
        moscow = "could_have"

    return {
        "reach": float(count),
        "impact": impact,
        "confidence": confidence,
        "effort": DEFAULT_SEED_EFFORT,
        "moscow": moscow,
    }


async def auto_seed_prioritization_from_insights(workspace_id: str) -> List[Dict[str, Any]]:
    """
    Auto-seed prioritization items directly from Milestone 2 Feature Clusters and Pain Points.
    Uses authentic customer volume, sentiment severity, and reach metrics to initialize RICE,
    Value vs Effort, MoSCoW, and Weighted scores.
    """
    weights = await get_or_create_workspace_weights(workspace_id)
    
    # 1. Fetch workspace insights
    cached_insights = None
    if database._mongodb_available:
        cached_insights = await db.workspace_insights.find_one({"workspace_id": workspace_id})
    else:
        cached_insights = await fallback_db.get_workspace_insights(workspace_id)

    seeded_items = []
    now = datetime.utcnow()

    clusters = cached_insights.get("feature_clusters", []) if cached_insights else []
    pain_points = cached_insights.get("pain_points", []) if cached_insights else []

    # Map Clusters
    for idx, c in enumerate(clusters[:6]):
        count = int(c.get("request_count", 25))
        priority_raw = float(c.get("priority_score", 70.0))
        demand_level = c.get("demand_level", "medium")

        inputs = measured_priority_inputs(count, demand_level)
        reach = inputs["reach"]
        impact = inputs["impact"]
        confidence = inputs["confidence"]
        effort = inputs["effort"]
        moscow = inputs["moscow"]
        val = round(min(9.5, max(4.0, (priority_raw / 10.0))), 1)
        eff = round(min(8.5, max(2.0, effort * 1.5)), 1)

        item_doc = {
            "id": f"prio_{uuid.uuid4().hex[:10]}",
            "workspace_id": workspace_id,
            "name": c.get("cluster_name", f"Feature Opportunity #{idx+1}"),
            "description": c.get("summary", ""),
            "category": "feature_request",
            "source_cluster_id": c.get("id"),
            "source_pain_point_id": None,
            "rice": {
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "score": _calculate_rice(reach, impact, confidence, effort),
            },
            "value_vs_effort": {
                "value": val,
                "effort": eff,
                "quadrant": _determine_quadrant(val, eff),
            },
            "moscow": moscow,
            "weighted": {
                "customer_demand_score": round(min(98.0, priority_raw + 5), 1),
                "business_impact_score": round(min(95.0, priority_raw), 1),
                # Feasibility and delivery risk cannot be derived from customer feedback, so
                # they start neutral instead of inheriting an invented score.
                "feasibility_score": 50.0,
                "risk_mitigation_score": 50.0,
                "final_score": 0.0,
            },
            "ai_rationale": (
                f"Measured: {count} requests mention this topic ({demand_level} demand tier). "
                f"Reach is that count; impact {impact} and confidence {confidence} are derived from "
                f"volume and demand tier. Assumed until a person sets them: effort {effort:.1f}, "
                f"feasibility and risk."
            ),
            "feedback_count": count,
            "rank": idx + 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        compute_all_scores_for_item(item_doc, weights)
        seeded_items.append(item_doc)

    # Map Pain Points
    for idx, pp in enumerate(pain_points[:4]):
        affected = int(pp.get("affected_users_count", 30))
        impact_raw = float(pp.get("impact_score", 75.0))
        severity = pp.get("severity", "medium")

        inputs = measured_priority_inputs(affected, severity)
        reach = inputs["reach"]
        impact = inputs["impact"]
        confidence = inputs["confidence"]
        effort = inputs["effort"]
        moscow = inputs["moscow"]
        val = round(min(9.8, max(5.0, (impact_raw / 10.0))), 1)
        eff = round(min(7.0, max(1.5, effort * 1.5)), 1)

        item_doc = {
            "id": f"prio_{uuid.uuid4().hex[:10]}",
            "workspace_id": workspace_id,
            "name": f"Resolve: {pp.get('title', 'System Friction')}",
            "description": f"Root Cause: {pp.get('root_cause', pp.get('description', ''))}. Recommended: {pp.get('recommended_action', '')}",
            "category": pp.get("category", "bug_report"),
            "source_cluster_id": None,
            "source_pain_point_id": pp.get("id"),
            "rice": {
                "reach": reach,
                "impact": impact,
                "confidence": confidence,
                "effort": effort,
                "score": _calculate_rice(reach, impact, confidence, effort),
            },
            "value_vs_effort": {
                "value": val,
                "effort": eff,
                "quadrant": _determine_quadrant(val, eff),
            },
            "moscow": moscow,
            "weighted": {
                "customer_demand_score": round(min(98.0, impact_raw), 1),
                "business_impact_score": round(min(96.0, impact_raw + 2), 1),
                # Neutral placeholders, as above: not derivable from feedback.
                "feasibility_score": 50.0,
                "risk_mitigation_score": 50.0,
                "final_score": 0.0,
            },
            "ai_rationale": (
                f"Measured: {affected} reports about this pain point (severity {severity}, "
                f"impact {impact_raw}/100). Reach is that count; impact {impact} and confidence "
                f"{confidence} are derived from volume and severity. Assumed until a person sets "
                f"them: effort {effort:.1f}, feasibility and risk."
            ),
            "feedback_count": affected,
            "rank": len(seeded_items) + 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        compute_all_scores_for_item(item_doc, weights)
        seeded_items.append(item_doc)

    # Sort seeded items by RICE score descending
    seeded_items.sort(key=lambda x: x["rice"]["score"], reverse=True)
    for r_idx, it in enumerate(seeded_items):
        it["rank"] = r_idx + 1

    # Persist
    if database._mongodb_available:
        # Clear existing items for clean re-seed
        await db.prioritization_items.delete_many({"workspace_id": workspace_id})
        if seeded_items:
            await db.prioritization_items.insert_many([dict(i) for i in seeded_items])
    else:
        await fallback_db.bulk_save_prioritization_items([dict(i) for i in seeded_items])

    return seeded_items


def normalise_prioritization_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Guarantee the fields every consumer of a prioritization item indexes.

    `prioritization_items` has carried two document shapes over its life: an older flat
    one identified only by `_id` with `title`/`rice_score`, and the canonical one
    identified by `id` with `name`/`rice{}`. Readers assume the canonical shape, so a
    single stale row used to take down a whole endpoint with `KeyError: 'id'` — the AI
    evaluation and roadmap generation both died this way, and the Prioritization table
    rendered the row with no title and no scores.

    Filling the gaps at the read boundary means a malformed row degrades into an
    ordinary-looking row instead of a 500 for the entire screen.
    """
    if not item.get("id"):
        item["id"] = str(item.get("_id") or f"prio_{uuid.uuid4().hex[:10]}")
    if not item.get("name"):
        item["name"] = item.get("title") or "Untitled initiative"
    if not item.get("description"):
        item["description"] = ""
    if not item.get("category"):
        item["category"] = "feature_request"
    if not item.get("moscow"):
        item["moscow"] = "should_have"
    if item.get("rank") is None:
        item["rank"] = 999
    if item.get("feedback_count") is None:
        item["feedback_count"] = 0

    # The nested score blocks are read as dictionaries (item.rice.score), so a legacy
    # flat row would otherwise raise on every render.
    rice = item.get("rice")
    if not isinstance(rice, dict):
        legacy_confidence = float(item.get("confidence") or 0.8)
        # Legacy rows stored confidence as a percentage (90); the canonical field is a
        # fraction (0.9). Detect which one we were handed rather than assuming.
        if legacy_confidence > 1.0:
            legacy_confidence = legacy_confidence / 100.0
        rice = {
            "reach": float(item.get("reach") or 500.0),
            "impact": float(item.get("impact") or 1.0),
            "confidence": min(1.0, max(0.1, legacy_confidence)),
            "effort": float(item.get("effort") or 2.0),
        }
    item["rice"] = rice
    if not isinstance(item.get("value_vs_effort"), dict):
        item["value_vs_effort"] = {
            "value": min(10.0, max(1.0, float(item.get("value_effort_score") or 70.0) / 10.0)),
            "effort": float(item.get("effort") or 2.0),
        }
    if not isinstance(item.get("weighted"), dict):
        item["weighted"] = {}

    return item


async def get_prioritization_items(workspace_id: str) -> List[Dict[str, Any]]:
    """Retrieve all prioritization items for a workspace, normalised to the canonical shape."""
    if database._mongodb_available:
        cursor = db.prioritization_items.find({"workspace_id": workspace_id}).sort("rank", 1)
        records = await cursor.to_list(length=None)
        for r in records:
            if "_id" in r:
                r["_id"] = str(r["_id"])
            normalise_prioritization_item(r)
        return records
    else:
        items = await fallback_db.find_prioritization_items_by_workspace(workspace_id)
        for item in items:
            normalise_prioritization_item(item)
        items.sort(key=lambda x: x.get("rank") or 999)
        return items


async def get_prioritization_item(item_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a single prioritization item by its own id."""
    if database._mongodb_available:
        return await db.prioritization_items.find_one({"id": item_id})
    return await fallback_db.find_prioritization_item_by_id(item_id)


async def create_prioritization_item(item_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new custom prioritization item and assign rank."""
    workspace_id = item_data["workspace_id"]
    weights = await get_or_create_workspace_weights(workspace_id)
    
    item_id = f"prio_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)

    reach = float(item_data.get("reach", 500.0))
    impact = float(item_data.get("impact", 1.0))
    confidence = float(item_data.get("confidence", 0.8))
    effort = float(item_data.get("effort", 2.0))
    val = float(item_data.get("value", 7.0))
    eff = float(item_data.get("effort_score", effort * 1.5))
    moscow = item_data.get("moscow", "should_have")

    doc: Dict[str, Any] = {
        "id": item_id,
        "workspace_id": workspace_id,
        "name": item_data.get("name", "New Initiative"),
        "description": item_data.get("description", ""),
        "category": item_data.get("category", "feature_request"),
        "source_cluster_id": item_data.get("source_cluster_id"),
        "source_pain_point_id": item_data.get("source_pain_point_id"),
        "rice": {
            "reach": reach,
            "impact": impact,
            "confidence": confidence,
            "effort": effort,
            "score": _calculate_rice(reach, impact, confidence, effort),
        },
        "value_vs_effort": {
            "value": val,
            "effort": eff,
            "quadrant": _determine_quadrant(val, eff),
        },
        "moscow": moscow,
        "weighted": {
            "customer_demand_score": float(item_data.get("customer_demand_score", 70.0)),
            "business_impact_score": float(item_data.get("business_impact_score", 75.0)),
            "feasibility_score": float(item_data.get("feasibility_score", 65.0)),
            "risk_mitigation_score": float(item_data.get("risk_mitigation_score", 60.0)),
            "final_score": 0.0,
        },
        "ai_rationale": item_data.get("ai_rationale", "User added custom initiative."),
        "feedback_count": int(item_data.get("feedback_count", 0)),
        "rank": 999,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    compute_all_scores_for_item(doc, weights)

    existing = await get_prioritization_items(workspace_id)
    doc["rank"] = len(existing) + 1

    if database._mongodb_available:
        await db.prioritization_items.insert_one(dict(doc))
    else:
        await fallback_db.save_prioritization_item(dict(doc))

    return doc


async def update_prioritization_item(item_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update item scores and recalculate outputs."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    existing = await get_prioritization_item(item_id)

    if not existing:
        return None

    workspace_id = existing["workspace_id"]
    weights = await get_or_create_workspace_weights(workspace_id)
    
    # Merge updates
    merged = {**existing, **updates}
    compute_all_scores_for_item(merged, weights)

    if database._mongodb_available:
        # `existing` comes back from Mongo with `_id` stringified, and `$set` cannot touch
        # the immutable `_id` field — it raises WriteError code 66 and the whole save fails.
        # The write path must send the mutable fields only.
        mutable = {key: value for key, value in merged.items() if key != "_id"}
        await db.prioritization_items.update_one({"id": item_id}, {"$set": mutable})
        updated = await db.prioritization_items.find_one({"id": item_id})
        if updated and "_id" in updated:
            updated["_id"] = str(updated["_id"])
        return updated
    else:
        return await fallback_db.update_prioritization_item(item_id, merged)


async def delete_prioritization_item(item_id: str) -> bool:
    """Delete a prioritization item."""
    if database._mongodb_available:
        res = await db.prioritization_items.delete_one({"id": item_id})
        return res.deleted_count > 0
    else:
        return await fallback_db.delete_prioritization_item(item_id)


async def ai_evaluate_all_priorities(workspace_id: str) -> List[Dict[str, Any]]:
    """
    Use Google Gemini (Pure AI) to evaluate and recommend priority parameters
    for all features in the workspace based on ingested customer sentiment and volume.
    """
    items = await get_prioritization_items(workspace_id)
    if not items:
        # Seed first if empty
        items = await auto_seed_prioritization_from_insights(workspace_id)
    
    if not items:
        return []

    item_summaries = []
    for it in items:
        # Reached defensively: an un-migrated row must not be able to 500 this endpoint.
        item_summaries.append(
            f"ID: {it.get('id')} | Name: {it.get('name') or 'Untitled initiative'} | "
            f"Category: {it.get('category') or 'feature_request'} | "
            f"Feedback Count: {it.get('feedback_count', 0)}"
        )

    prompt = f"""You are a Principal Product Operations and Prioritization Specialist.
Review the following product initiatives derived from user feedback:

{chr(10).join(item_summaries)}

Evaluate each item across standard prioritization frameworks:
- RICE: reach (users/mo, e.g. 100-10000), impact (0.25 to 3.0), confidence (0.2 to 1.0), effort (0.5 to 10.0 sprints)
- Value vs Effort: value (1-10), effort (1-10)
- MoSCoW: must_have, should_have, could_have, wont_have
- Strategic Rationale: 1-2 sentence evidence-based justification

Return ONLY a valid JSON object matching this schema:
{{
  "evaluations": [
    {{
      "id": "item_id",
      "reach": 2500,
      "impact": 2.0,
      "confidence": 0.85,
      "effort": 2.0,
      "value": 8.5,
      "effort_score": 3.5,
      "moscow": "must_have",
      "demand_score": 85.0,
      "impact_score": 88.0,
      "feasibility_score": 75.0,
      "risk_mitigation_score": 70.0,
      "rationale": "High volume customer friction with direct retention impact."
    }}
  ]
}}
"""

    parsed_evals = None

    # 1. Attempt Groq AI (Fastest, verified working)
    groq_client = get_groq_client()
    if groq_client:
        for m_name in GROQ_MODELS:
            try:
                logger.info(f"Running AI prioritization evaluation with Groq {m_name}...")
                supports_json = m_name in ["allam-2-7b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b", "openai/gpt-oss-120b"]
                response = groq_client.chat.completions.create(
                    model=m_name,
                    messages=[
                        {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2500,
                    timeout=20,
                    response_format={"type": "json_object"} if supports_json else None,
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and "evaluations" in parsed:
                    parsed_evals = parsed["evaluations"]
                    break
            except Exception as e:
                logger.warning(f"Groq prioritization error on {m_name}: {e}...")

    # 2. Attempt OpenRouter Free AI Fallback
    if not parsed_evals:
        openrouter_client = get_openrouter_client()
        if openrouter_client:
            for m_name in OPENROUTER_MODELS:
                try:
                    logger.info(f"Running AI prioritization evaluation with OpenRouter {m_name}...")
                    response = openrouter_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=OPENROUTER_MAX_TOKENS,
                        timeout=OPENROUTER_TIMEOUT_SECONDS,
                    )
                    parsed = _extract_json_from_text(response.choices[0].message.content)
                    if parsed and "evaluations" in parsed:
                        parsed_evals = parsed["evaluations"]
                        break
                except Exception as e:
                    logger.warning(f"OpenRouter prioritization error on {m_name}: {e}...")

    # 3. Attempt Google Gemini Backup
    if not parsed_evals:
        gem_client = get_gemini_client()
        if gem_client:
            for g_model in GEMINI_MODELS:
                try:
                    from google.genai import types
                    logger.info(f"Running AI prioritization evaluation with {g_model}...")
                    response = gem_client.models.generate_content(
                        model=g_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.2,
                            timeout=15,
                        ),
                    )
                    parsed = _extract_json_from_text(response.text)
                    if parsed and "evaluations" in parsed:
                        parsed_evals = parsed["evaluations"]
                        break
                except Exception as e:
                    logger.warning(f"AI prioritization evaluation error on {g_model}: {e}...")

    # 4. Attempt Mistral AI Fallback (free Experiment tier, OpenAI-compatible)
    if not parsed_evals:
        mistral_client = get_mistral_client()
        if mistral_client:
            for m_name in MISTRAL_MODELS:
                try:
                    logger.info(f"Running AI prioritization evaluation with Mistral {m_name}...")
                    response = mistral_client.chat.completions.create(
                        model=m_name,
                        messages=[
                            {"role": "system", "content": "You are a Principal Product Manager. Respond ONLY in valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=2500,
                        response_format={"type": "json_object"},
                        timeout=20,
                    )
                    parsed = _extract_json_from_text(response.choices[0].message.content)
                    if parsed and "evaluations" in parsed:
                        parsed_evals = parsed["evaluations"]
                        break
                except Exception as e:
                    logger.warning(f"Mistral prioritization error on {m_name}: {e}...")

    # Apply updates if evaluations succeeded
    if parsed_evals:
        eval_map = {e["id"]: e for e in parsed_evals if "id" in e}
        weights = await get_or_create_workspace_weights(workspace_id)
        
        for it in items:
            if it["id"] in eval_map:
                ev = eval_map[it["id"]]
                it["rice"]["reach"] = float(ev.get("reach", it["rice"]["reach"]))
                it["rice"]["impact"] = float(ev.get("impact", it["rice"]["impact"]))
                it["rice"]["confidence"] = float(ev.get("confidence", it["rice"]["confidence"]))
                it["rice"]["effort"] = float(ev.get("effort", it["rice"]["effort"]))
                it["value_vs_effort"]["value"] = float(ev.get("value", it["value_vs_effort"]["value"]))
                it["value_vs_effort"]["effort"] = float(ev.get("effort_score", it["value_vs_effort"]["effort"]))
                it["moscow"] = ev.get("moscow", it["moscow"])
                it["weighted"]["customer_demand_score"] = float(ev.get("demand_score", it["weighted"]["customer_demand_score"]))
                it["weighted"]["business_impact_score"] = float(ev.get("impact_score", it["weighted"]["business_impact_score"]))
                it["weighted"]["feasibility_score"] = float(ev.get("feasibility_score", it["weighted"]["feasibility_score"]))
                it["weighted"]["risk_mitigation_score"] = float(ev.get("risk_mitigation_score", it["weighted"]["risk_mitigation_score"]))
                it["ai_rationale"] = ev.get("rationale", it.get("ai_rationale"))
                compute_all_scores_for_item(it, weights)
                await update_prioritization_item(it["id"], it)

    # Re-sort by RICE and update ranks
    updated_items = await get_prioritization_items(workspace_id)
    updated_items.sort(key=lambda x: x["rice"]["score"], reverse=True)
    for r_idx, it in enumerate(updated_items):
        it["rank"] = r_idx + 1
        await update_prioritization_item(it["id"], {"rank": r_idx + 1})

    return updated_items
