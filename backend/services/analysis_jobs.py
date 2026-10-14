"""
Background analysis jobs.

A full workspace analysis reads every record, mines topics, scores trends and may wait
on rate-limited LLM providers — measured at 59 s for a 10,000-record workspace, and the
reason a page load used to hang. Running it inside the request that triggered it makes
the caller wait for all of it, so this module owns the work instead: a request starts a
job and returns immediately, and any page can ask what is happening.

There is at most one live job per workspace, so two pages opening at the same time share
one analysis rather than writing the same collection twice.

The registry is in-memory and is the authority on "is it running" — a job cannot survive
a restart, so a persisted document that claims otherwise is stale and is corrected on
read. Only the finished run is persisted; the token used to start it never is.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import database

logger = logging.getLogger(__name__)

COLLECTION = "analysis_jobs"

# The stages the pipeline passes through, in order. `progress` is the percentage shown
# while the stage runs; it is deliberately not evenly spaced because the AI stage is the
# one that can take tens of seconds and the deterministic stages before it are fast.
STAGES = (
    ("reading", "Reading feedback", 5),
    ("categorizing", "Categorising and scoring sentiment", 15),
    ("themes", "Extracting themes", 30),
    ("pain_points", "Finding pain points", 40),
    ("clusters", "Clustering feature requests", 50),
    ("ai", "Running AI analysis", 60),
    ("titles", "Normalising titles", 80),
    ("trends", "Scoring trends and health", 85),
    ("saving", "Saving results", 92),
)

STAGE_LABELS = {stage_id: label for stage_id, label, _ in STAGES}

# workspace_id -> the job currently running for it.
_live: Dict[str, Dict[str, Any]] = {}


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if isinstance(value, datetime) else None


def _now() -> str:
    return _iso(datetime.utcnow())


def _stage_progress(stage_id: str) -> int:
    for known_id, _label, progress in STAGES:
        if known_id == stage_id:
            return progress
    return 0


def _public(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    The status a caller is allowed to see.

    A job carries the bearer token that started it so the pipeline can authenticate —
    that must never reach a response body, so it is dropped on every read, including the
    one that returns immediately after starting.
    """
    return {key: value for key, value in job.items() if key != "authorization"}


def _base(workspace_id: str) -> Dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "state": "idle",
        "stage": None,
        "stage_label": None,
        "progress": 0,
        "reason": None,
        "queued_at": None,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "records": None,
        "ai_powered": False,
        "ai_model": None,
    }


async def _last_finished(workspace_id: str) -> Optional[Dict[str, Any]]:
    """The persisted record of the previous run, or None."""
    if not database._mongodb_available:
        return None
    try:
        doc = await database.db[COLLECTION].find_one({"workspace_id": workspace_id})
        if doc:
            doc.pop("_id", None)
        return doc
    except Exception as exc:  # A status read must never fail the page it is reporting on.
        logger.warning("Could not read analysis job for %s: %s", workspace_id, exc)
        return None


async def _persist(job: Dict[str, Any]) -> None:
    if not database._mongodb_available:
        return
    payload = {k: v for k, v in job.items() if k != "authorization"}
    try:
        await database.db[COLLECTION].update_one(
            {"workspace_id": job["workspace_id"]},
            {"$set": payload},
            upsert=True,
        )
    except Exception as exc:
        logger.warning("Could not persist analysis job for %s: %s", job["workspace_id"], exc)


async def _has_stored_insights(workspace_id: str) -> bool:
    try:
        if database._mongodb_available:
            return await database.db.workspace_insights.find_one(
                {"workspace_id": workspace_id}, {"_id": 1}
            ) is not None
        from fallback_db import get_workspace_insights as fb_get_workspace_insights

        return bool(await fb_get_workspace_insights(workspace_id))
    except Exception:
        return False


async def get_status(workspace_id: str) -> Dict[str, Any]:
    """
    What is happening with this workspace's analysis.

    A live job always wins. Without one, the persisted record of the last run is shown;
    a persisted document still marked "running" cannot be true (the process that owned it
    is gone), so it is reported as idle and repaired rather than left to hang forever.
    """
    live = _live.get(workspace_id)
    if live:
        return _public(live)

    status = _base(workspace_id)
    stored = await _last_finished(workspace_id)
    if stored:
        if stored.get("state") == "running":
            stored["state"] = "idle"
            stored["stage"] = None
            stored["stage_label"] = None
            stored["progress"] = 0
            stored["error"] = None
            await _persist(stored)
        status.update({k: v for k, v in stored.items() if k in status})

    if status["state"] == "idle":
        status["ai_powered"] = False

    status["has_insights"] = await _has_stored_insights(workspace_id)
    if status["has_insights"] and not status["finished_at"]:
        # Analysis predates this registry (or was written by another path): the result is
        # there, so report it as completed rather than claiming nothing has run.
        status["state"] = "completed"
        try:
            if database._mongodb_available:
                doc = await database.db.workspace_insights.find_one(
                    {"workspace_id": workspace_id}, {"analyzed_at": 1, "total_analyzed": 1}
                )
            else:
                from fallback_db import get_workspace_insights as fb_get_workspace_insights

                doc = await fb_get_workspace_insights(workspace_id)
            if doc:
                status["finished_at"] = _iso(doc.get("analyzed_at"))
                status["records"] = doc.get("total_analyzed")
                status["ai_powered"] = bool(doc.get("ai_powered"))
                status["ai_model"] = doc.get("ai_model")
        except Exception:
            pass
        if status["progress"] < 100:
            status["progress"] = 100
    return status


def start(workspace_id: str, authorization: str, reason: str = "manual") -> Dict[str, Any]:
    """
    Queue an analysis for a workspace, or return the one already running.

    Returns the status immediately; the caller is expected to poll `get_status` rather
    than wait. Starting is idempotent — a second request joins the running job instead
    of starting a competing one that would write the same collections.
    """
    existing = _live.get(workspace_id)
    if existing:
        return _public(existing)

    job = _base(workspace_id)
    job.update(
        {
            "state": "running",
            "stage": "queued",
            "stage_label": "Waiting to start",
            "progress": 0,
            "reason": reason,
            "queued_at": _now(),
            "authorization": authorization,
        }
    )
    _live[workspace_id] = job
    asyncio.create_task(_execute(job))
    return _public(job)


async def _execute(job: Dict[str, Any]) -> None:
    workspace_id = job["workspace_id"]
    started = _now()
    job["started_at"] = started
    job["stage"] = "reading"
    job["stage_label"] = STAGE_LABELS["reading"]
    job["progress"] = _stage_progress("reading")
    await _persist({k: v for k, v in job.items() if k != "authorization"})

    def report(stage_id: str) -> None:
        """Called by the pipeline as it reaches each stage."""
        job["stage"] = stage_id
        job["stage_label"] = STAGE_LABELS.get(stage_id, stage_id)
        job["progress"] = _stage_progress(stage_id)

    try:
        # Imported lazily: the router imports this module for its own status endpoints.
        from routers.insights import run_analysis

        insights = await run_analysis(
            workspace_id, job.pop("authorization"), progress=report
        )
        job.update(
            {
                "state": "completed",
                "stage": "done",
                "stage_label": "Complete",
                "progress": 100,
                "finished_at": _now(),
                "records": insights.total_analyzed if hasattr(insights, "total_analyzed") else None,
                "ai_powered": bool(getattr(insights, "ai_powered", False)),
                "ai_model": getattr(insights, "ai_model", None),
                "error": None,
            }
        )
    except Exception as exc:
        logger.exception("Analysis failed for %s", workspace_id)
        job.update(
            {
                "state": "failed",
                "stage": "failed",
                "stage_label": "Failed",
                "finished_at": _now(),
                "error": str(exc) or type(exc).__name__,
            }
        )
    finally:
        job.pop("authorization", None)
        await _persist(job)
        _live.pop(workspace_id, None)
