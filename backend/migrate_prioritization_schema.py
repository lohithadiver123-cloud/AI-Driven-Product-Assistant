"""
Migrate legacy-shaped prioritization items into the canonical schema.

Background
----------
`prioritization_items` holds two incompatible document shapes. The newer one — the
one the API and the React app both read — carries `id`, `name`, `rice{}`,
`value_vs_effort{}`, `weighted{}`, `moscow` and `rank`. An older seeding pass wrote
flat documents instead: `_id` only, `title`, `rice_score`, `wsjf_score`,
`value_effort_score`, `quadrant`, `type`.

Those stale rows are not cosmetic. Every consumer indexes `item["id"]`, so a single
legacy row takes down a whole endpoint:

    prioritization_service.ai_evaluate_all_priorities  -> KeyError: 'id'
    roadmap_service.generate_roadmap                   -> KeyError: 'id'

and on the Prioritization screen they render as a row with no title and no scores,
because the frontend reads `item.name` and `item.rice.score`.

What this does
--------------
Rewrites every document that has no `id` into the canonical shape. It is additive:
legacy keys are preserved, so nothing that still reads them breaks. Measured values
are carried across; anything the old row never recorded is set to the codebase's own
default and *said so* in `ai_rationale`, rather than being invented silently.

Usage
-----
    cd backend
    ./.venv/Scripts/python.exe migrate_prioritization_schema.py            # dry run, prints the plan
    ./.venv/Scripts/python.exe migrate_prioritization_schema.py --apply    # writes, after backing up

A timestamped backup of every document it is about to change is written to
`backend/.migrations/` before anything is modified.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import database
from services.prioritization_service import compute_all_scores_for_item

BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".migrations")

# The old rows stored `type` as a loose word; the canonical field is one of the
# categories the rest of the app already uses.
# The impact multiplier the RICE framework and the Prioritization screen both use. A
# value outside it renders as a dropdown that silently falls back to its first option, so
# the row shows one impact while its score was computed from another.
IMPACT_SCALE = [0.25, 0.5, 1.0, 2.0, 3.0]

# The confidence values the same screen offers.
CONFIDENCE_SCALE = [0.5, 0.7, 0.8, 0.9, 1.0]

CATEGORY_MAP = {
    "feature": "feature_request",
    "feature_request": "feature_request",
    "bug": "bug_report",
    "bug_report": "bug_report",
    "performance": "performance_issue",
    "performance_issue": "performance_issue",
    "general": "general_feedback",
    "general_feedback": "general_feedback",
}


def _as_float(value, default):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _nearest_allowed(value, allowed, default):
    """Snap a value onto the nearest option the UI actually offers."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number in allowed:
        return number
    return min(allowed, key=lambda option: abs(option - number))


def _normalise_confidence(value) -> float:
    """
    The legacy rows stored confidence as a percentage (90) while the canonical field
    is a fraction (0.9). Detect which one we were handed instead of guessing.
    """
    confidence = _as_float(value, 0.8)
    if confidence > 1.0:
        confidence = confidence / 100.0
    return min(1.0, max(0.1, confidence))


def convert_legacy_item(doc: dict, rank: int, weights: dict) -> dict:
    """Build the canonical fields for one legacy document, preserving what was there."""
    reach = _as_float(doc.get("reach"), 500.0)
    # Snapped onto the offered scale: the legacy rows used impact 5.0, which the input
    # cannot represent, so the screen showed 0.25 while the score used 5.0.
    impact = _nearest_allowed(doc.get("impact"), IMPACT_SCALE, 1.0)
    confidence = _nearest_allowed(
        _normalise_confidence(doc.get("confidence")), CONFIDENCE_SCALE, 0.8
    )
    effort = _as_float(doc.get("effort"), 2.0)

    # The old value/effort score was published on a 0-10 scale for `value`.
    legacy_value_score = _as_float(doc.get("value_effort_score"), None)
    if legacy_value_score is None:
        value = min(10.0, max(1.0, round(impact * 2, 1)))
        value_basis = "derived from impact"
    else:
        value = min(10.0, max(1.0, round(legacy_value_score / 10.0, 1)))
        value_basis = "measured (value_effort_score)"

    item_id = doc.get("id") or f"prio_{uuid.uuid4().hex[:10]}"
    title = doc.get("name") or doc.get("title") or "Untitled initiative"
    category = CATEGORY_MAP.get(str(doc.get("category") or doc.get("type") or "").lower(), "feature_request")
    created_at = doc.get("created_at") or datetime.now(timezone.utc).isoformat()

    source_type = doc.get("source_type")
    source_id = doc.get("source_id")

    canonical = {
        "id": item_id,
        "name": title,
        "description": doc.get("description") or "",
        "category": category,
        "source_cluster_id": source_id if source_type == "cluster" else doc.get("source_cluster_id"),
        "source_pain_point_id": source_id if source_type == "pain_point" else doc.get("source_pain_point_id"),
        "rice": {
            "reach": reach,
            "impact": impact,
            "confidence": confidence,
            "effort": effort,
        },
        "value_vs_effort": {
            "value": value,
            "effort": effort,
        },
        # The old schema never recorded the four weighted sub-scores. They stay on the
        # application defaults and are called out in the rationale instead of guessed.
        "weighted": {
            "customer_demand_score": _as_float(doc.get("customer_demand_score"), 70.0),
            "business_impact_score": _as_float(doc.get("business_impact_score"), 75.0),
            "feasibility_score": _as_float(doc.get("feasibility_score"), 65.0),
            "risk_mitigation_score": _as_float(doc.get("risk_mitigation_score"), 60.0),
        },
        "moscow": doc.get("moscow") or "should_have",
        "feedback_count": int(_as_float(doc.get("feedback_count"), 0)),
        "rank": rank,
        "created_at": created_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "ai_rationale": (
            f"Converted from the legacy prioritization schema. Measured and carried over: "
            f"reach {reach:.0f}, impact {impact}, confidence {confidence}, effort {effort:.1f}, "
            f"value {value:.1f} ({value_basis}). Assumed on the application defaults because the "
            f"old row never recorded them: feasibility, risk mitigation, customer demand and "
            f"MoSCoW. Set them to re-rank this initiative."
        ),
    }

    # Carry the old fields forward so any reader still on the previous shape keeps working.
    merged = {**doc, **canonical}
    for discarded in ("id", "name", "rice", "value_vs_effort", "weighted", "moscow", "rank",
                      "category", "feedback_count", "source_cluster_id", "source_pain_point_id"):
        merged[discarded] = canonical[discarded]

    compute_all_scores_for_item(merged, weights)
    return merged


async def repair(workspace_id, collection, weights, write: bool) -> int:
    """
    Snap already-canonical rows whose impact sits off the offered scale.

    `write` must be False for a dry run: this function changes documents, so calling it
    from the dry-run path would mutate data the caller was only asking about.
    """
    off_scale = await collection.find({
        "workspace_id": workspace_id,
        "rice.impact": {"$nin": IMPACT_SCALE},
    }).to_list(length=None)

    fixed = 0
    for doc in off_scale:
        rice = dict(doc.get("rice") or {})
        original = rice.get("impact")
        rice["impact"] = _nearest_allowed(original, IMPACT_SCALE, 1.0)
        merged = {**doc, "rice": rice}
        compute_all_scores_for_item(merged, weights)
        if write:
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": {"rice": merged["rice"], "value_vs_effort": merged["value_vs_effort"],
                           "weighted": merged["weighted"]}},
            )
        print(
            f"  {doc.get('id') or doc['_id']}  impact {original} -> {rice['impact']}"
            f"{' (written)' if write else ''}"
        )
        fixed += 1
    return fixed


async def migrate(apply: bool) -> None:
    await database.connect_to_mongo()
    if not database._mongodb_available:
        print("MongoDB is not available; nothing to migrate. (The JSON fallback is not affected.)")
        await database.close_mongo_connection()
        return

    collection = database.db.prioritization_items
    legacy = await collection.find({"id": {"$exists": False}}).to_list(length=None)
    total = await collection.count_documents({})
    print(f"prioritization_items: {total} documents, {len(legacy)} in the legacy shape")

    # Group so the new ranks stack below the ranks already in use per workspace.
    by_workspace: dict = {}
    for doc in legacy:
        by_workspace.setdefault(doc.get("workspace_id"), []).append(doc)

    backup = []
    planned = []

    from services.prioritization_service import get_or_create_workspace_weights

    for workspace_id, docs in by_workspace.items():
        weights = await get_or_create_workspace_weights(workspace_id)
        highest = await collection.find_one(
            {"workspace_id": workspace_id, "rank": {"$exists": True}},
            sort=[("rank", -1)],
        )
        next_rank = int((highest or {}).get("rank") or 0) + 1

        for offset, doc in enumerate(docs):
            fresh = convert_legacy_item(doc, next_rank + offset, weights)
            planned.append((doc["_id"], fresh))
            backup.append({"_id": str(doc["_id"]), "before": json.loads(json.dumps(doc, default=str))})
            print(
                f"  {str(doc['_id'])}  ws={workspace_id}  rank={fresh['rank']}  "
                f"{fresh['name'][:50]!r}  RICE={fresh['rice']['score']}"
            )

    # Rows converted on an earlier run can still carry an impact the screen cannot show.
    repair_workspaces = await collection.distinct(
        "workspace_id", {"rice.impact": {"$nin": IMPACT_SCALE}}
    )
    if repair_workspaces:
        print(f"\nOff-scale impact in {len(repair_workspaces)} workspace(s):")

    if not planned and not repair_workspaces:
        print("Nothing to do — every document already has an `id` and an on-scale impact.")
        await database.close_mongo_connection()
        return

    if not apply:
        for workspace_id in repair_workspaces:
            await repair(
                workspace_id, collection,
                await get_or_create_workspace_weights(workspace_id), write=False,
            )
        print("\nDry run. Re-run with --apply to write these changes.")
        await database.close_mongo_connection()
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"prioritization-items-{stamp}.json")
    with open(backup_path, "w", encoding="utf-8") as handle:
        json.dump(backup, handle, indent=2, default=str)
    print(f"\nBacked up {len(backup)} documents to {backup_path}")

    changed = 0
    for doc_id, fresh in planned:
        await collection.update_one({"_id": doc_id}, {"$set": fresh})
        changed += 1

    repaired = 0
    for workspace_id in repair_workspaces:
        repaired += await repair(
            workspace_id, collection,
            await get_or_create_workspace_weights(workspace_id), write=True,
        )

    remaining = await collection.count_documents({"id": {"$exists": False}})
    print(
        f"Updated {changed} legacy documents, corrected {repaired} off-scale impacts. "
        f"Legacy-shaped documents remaining: {remaining}"
    )
    await database.close_mongo_connection()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = parser.parse_args()
    asyncio.run(migrate(args.apply))
