"""
Title Normalizer Service.
Converts raw, algorithmic n-gram topics into clean, concise, human-grade
Product Defect and Feature Opportunity titles using lightweight AI synthesis
with a robust heuristic fallback.
"""

import os
import re
import json
import logging
import time
from typing import List, Dict, Any, Optional

from services.ai_service import (
    get_gemini_client,
    get_mistral_client,
    get_groq_client,
    get_openrouter_client,
    GEMINI_MODELS,
    MISTRAL_MODELS,
    GROQ_MODELS,
    OPENROUTER_MAX_TOKENS,
    OPENROUTER_MODELS,
    _extract_json_from_text,
    is_provider_throttled,
    mark_provider_throttled,
    provider_in_cooldown,
)

logger = logging.getLogger(__name__)

# Heuristic topic mapper for offline / zero-AI fallback
HEURISTIC_RULES = [
    (r"\b(shuffle|random)\b", "Playlist Shuffle & Repeat Friction"),
    (r"\b(ad|ads|advert|commercial)\b", "Excessive Ad Frequency & Interruptions"),
    (r"\b(progress|lost progress|save|saving|reset|level)\b", "Loss of Game Progress & Save Resets"),
    (r"\b(login|logout|password|auth|account|sign in|banned)\b", "Account Sign-In & Profile Recovery Failures"),
    (r"\b(crash|freeze|stops|stopped|broken|error|black screen|closes)\b", "App Freezes & Playback Termination"),
    (r"\b(slow|lag|latency|load|loading|stutter|fps)\b", "High App Latency & Slow Loading"),
    (r"\b(control|controls|touch|swipe|joystick)\b", "Touch Control Responsiveness & Input Lag"),
    (r"\b(sound|music|audio|volume|mute|glitch)\b", "Audio Glitches & Playback Interruptions"),
    (r"\b(offline|download|wifi|data)\b", "Offline Listening & Download Restrictions"),
    (r"\b(premium|pay|price|subscription|fee|charge)\b", "Subscription Pricing & Paywall Friction"),
    (r"\b(video|canvas|feed|visual)\b", "Intrusive Video Feeds & Media Toggles"),
    (r"\b(battery|heat|overheat|drain)\b", "Battery Drain & Device Overheating"),
    (r"\b(deliver|delivery|rider|late|delay)\b", "Delivery Delays & Order Tracking Lag"),
    (r"\b(missing|spill|spilled|wrong)\b", "Missing Items & Order Fulfillment Errors"),
    (r"\b(support|chat|ticket|agent|help)\b", "Customer Support & Ticket Closure Issues"),
    (r"\b(queue|playlist|liked)\b", "Queue Management & Playlist Customization"),
    (r"\b(audiobook|podcast|show)\b", "Podcast & Audiobook Discovery Limits"),
    (r"\b(update|patch|new version|downgrade)\b", "Post-Update Regressions & Compatibility Issues"),
]


# Where the title a reader is looking at came from. A model-written title is final; a
# heuristic label is a placeholder, kept only while no model is reachable so that a model
# can replace it once one is configured.
TITLE_SOURCE_AI = "normalized_ai"
TITLE_SOURCE_HEURISTIC = "normalized_heuristic"

# Model calls allowed per upgrade pass. Titles that no provider answers for keep a
# heuristic placeholder rather than holding up the request that asked for them.
MAX_TITLE_ATTEMPTS = 4

# Time budget for one upgrade pass. The count above bounds how many calls are made but
# not how long any of them can take — an SDK with no timeout waits on a provider for
# minutes, and a read that triggers an upgrade used to hold the page open for exactly
# that long. Whatever is unanswered when the budget runs out stays a placeholder and is
# retried on the next analysis instead of being waited for here.
TITLE_UPGRADE_BUDGET_SECONDS = 12.0
TITLE_CALL_TIMEOUT_SECONDS = 8.0


def _display_title(topic: Dict[str, Any], topic_type: str) -> str:
    """The title a reader currently sees for this topic."""
    if topic_type == "cluster":
        return str(topic.get("cluster_name") or topic.get("title") or "")
    return str(topic.get("title") or topic.get("cluster_name") or "")


def _ai_provider_available(allow_ai: bool) -> bool:
    """Whether any configured provider could actually rewrite a title right now."""
    if not allow_ai:
        return False
    return any(bool(getter()) for getter in (get_groq_client, get_openrouter_client, get_gemini_client, get_mistral_client))


def needs_title_upgrade(
    topic: Dict[str, Any],
    topic_type: str = "pain_point",
    allow_ai: bool = True,
    revise_placeholders: bool = True,
) -> bool:
    """
    Whether this topic still displays an un-upgraded algorithmic title.

    A bare `ai_title` deliberately does not satisfy this: the merge step records the model's
    own unpolished label there, and accepting that as proof of normalisation is what let
    "Pay Premium" and "Skip Songs" reach the dashboard. What counts is the recorded source
    of the title a reader is actually looking at.

    `revise_placeholders` belongs to upgrade runs — an analysis or a migration — and not to
    a page read: a read that retried every heuristic label would ask the model again on
    every request, because a placeholder stays a placeholder whenever the model is flaky.
    """
    source = topic.get("title_source")
    if source == TITLE_SOURCE_AI:
        return False
    if source == TITLE_SOURCE_HEURISTIC:
        return revise_placeholders and _ai_provider_available(allow_ai)

    # Analyses stored before `title_source` existed: a title that already differs from the
    # algorithmic title recorded beside it has been upgraded once and is left as it is.
    previous = topic.get("raw_cluster_name") if topic_type == "cluster" else topic.get("raw_title")
    if not previous:
        return True
    return _display_title(topic, topic_type) == str(previous)


def _heuristic_fallback_title(raw_title: str, keywords: List[str], quote: str, topic_type: str) -> str:
    """Derive a sensible, professional title when AI is unreachable."""
    context_text = f"{raw_title} {' '.join(keywords)} {quote}".lower()
    
    for pattern, clean_title in HEURISTIC_RULES:
        if re.search(pattern, context_text):
            if topic_type == "cluster":
                return clean_title.replace("Friction", "Capability").replace("Issues", "Enhancement").replace("Defect", "Improvement")
            return clean_title
            
    # Default capitalization cleanup
    words = [w.capitalize() for w in raw_title.split() if len(w) > 2]
    cleaned = " ".join(words)
    suffix = " Opportunity" if topic_type == "cluster" else " Friction"
    return (cleaned + suffix) if cleaned else ("Product " + ("Opportunity" if topic_type == "cluster" else "Friction"))


# One batch prompt now covers pain points, clusters and themes together.
#
# Each group used to be its own call with its own 12 s budget, so the analysis paid for
# three model round trips where one carries the same information. Measured on a
# 10,000-record workspace with Groq rate limited: each pass fell to the free OpenRouter
# model, which needs ~16 s, and 3 × 16 s was 45 s of a 70 s analysis spent naming topics.
# The batch passes a `kind` per item and one prompt names them all.
TITLE_BATCH_BUDGET_SECONDS = 25.0
TITLE_BATCH_ATTEMPTS = 3


def _parse_title_array(text: str, count: int) -> Dict[int, str]:
    """
    Read the ids and titles out of a model reply.

    The shared `_extract_json_from_text` returns a single object when a reply wraps its
    array in a sentence ("Here are the titles: [...]"), which silently discarded a whole
    batch of good titles. The array is matched by its own brackets first; the shared
    helper is only a fallback.
    """
    candidates = []
    if text:
        for attempt in (
            text.strip(),
            re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).replace("```", "").strip(),
        ):
            start = attempt.find("[")
            if start == -1:
                continue
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(attempt)):
                char = attempt[index]
                if in_string:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == '"':
                        in_string = False
                    continue
                if char == '"':
                    in_string = True
                elif char == "[":
                    depth += 1
                elif char == "]":
                    depth -= 1
                    if depth == 0:
                        candidates.append(attempt[start:index + 1])
                        break

    fallback = _extract_json_from_text(text)
    if isinstance(fallback, list):
        candidates.append(fallback)

    for candidate in candidates:
        try:
            items = candidate if isinstance(candidate, list) else json.loads(candidate)
        except Exception:
            continue
        found: Dict[int, str] = {}
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or "title" not in item:
                continue
            try:
                index = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            title = str(item["title"]).strip()
            if 0 <= index < count and title:
                found[index] = title
        if found:
            return found
    return {}


def _topic_kind(topic_type: str) -> str:
    """How a topic's kind reads inside the batch prompt."""
    return {"cluster": "feature opportunity", "theme": "theme"}.get(topic_type, "pain point")


def _topic_payload(pending: List[Dict[str, Any]], topic_type: str, offset: int = 0, with_kind: bool = False) -> List[Dict[str, Any]]:
    """The compact per-topic input the model is asked to retitle."""
    payload = []
    for idx, t in enumerate(pending):
        raw = _display_title(t, topic_type) or f"Topic {idx + 1}"
        quotes = t.get("sample_quotes") or t.get("sample_requests") or t.get("distinct_sample_quotes") or []
        quote = str(quotes[0]).strip() if quotes else ""
        if len(quote) > 160:
            quote = quote[:160] + "..."
        kws = [str(k) for k in (t.get("keywords") or [])[:5]]
        item = {
            "id": offset + idx,
            "raw_title": raw,
            "keywords": kws,
            "customer_quote": quote,
        }
        if with_kind:
            item["kind"] = _topic_kind(topic_type)
        payload.append(item)
    return payload


def _title_prompt(payload: List[Dict[str, Any]], topic_types: List[str]) -> str:
    """The instruction to retitle a payload of one or more topic kinds."""
    if len(topic_types) == 1:
        subject = f"({topic_types[0]}s)"
    else:
        subject = ", ".join(sorted({_topic_kind(kind) for kind in topic_types}))
    return f"""You are a Principal Product Manager.
Review these raw, algorithmic customer feedback topics ({subject}). Each topic has an unpolished n-gram title and a real customer quote.
Rewrite each raw title into a clean, concise, 3-6 word professional Product Defect / Feature Opportunity title (e.g., 'Shuffle Repeats Same Tracks', 'Limited Song Skips on Free Tier', 'Offline Download Restrictions').
Directly address the user's actual grievance or request based on their quote.

Input:
{json.dumps(payload, indent=2)}

Return ONLY a valid JSON array matching this exact format, with no markdown code fences or explanations:
[
  {{"id": 0, "title": "Concise Professional Title"}}
]
"""


def _apply_normalized_titles(
    pending: List[Dict[str, Any]],
    topic_type: str,
    parsed_titles: Dict[int, str],
) -> None:
    """Write the chosen titles onto the topics, falling back per topic where none came back."""
    for idx, t in enumerate(pending):
        raw = _display_title(t, topic_type) or f"Topic {idx+1}"
        kws = t.get("keywords") or []
        quotes = t.get("sample_quotes") or t.get("sample_requests") or []
        quote = str(quotes[0]) if quotes else ""

        if idx in parsed_titles and len(parsed_titles[idx]) >= 4:
            clean_title = parsed_titles[idx]
            title_source = TITLE_SOURCE_AI
        else:
            clean_title = _heuristic_fallback_title(raw, kws, quote, topic_type)
            title_source = TITLE_SOURCE_HEURISTIC

        # The algorithmic title is recorded once, so a later pass can never mistake an
        # upgraded title for the raw one it came from.
        if topic_type == "cluster":
            t["raw_cluster_name"] = t.get("raw_cluster_name") or raw
            t["cluster_name"] = clean_title
            t["ai_cluster_name"] = clean_title
        else:
            t["raw_title"] = t.get("raw_title") or raw
            t["title"] = clean_title
            t["ai_title"] = clean_title
        t["title_source"] = title_source

        # Upgrade robotic description templates into executive-ready PM phrasing
        desc = str(t.get("description") or "")
        if "complaints mention" in desc.lower():
            sb = t.get("score_breakdown") or {}
            c = sb.get("frequency") or t.get("affected_users_count") or 1
            avg = sb.get("avg_rating") or 2.0
            neg = sb.get("negative_sentiment_pct")
            neg_clause = f", {neg}% negative reports" if neg else ""
            t["description"] = f"Recurring customer complaints highlight severe friction regarding {clean_title.lower()} across {c} user signals (avg rating {avg}/5.0{neg_clause})."

        act = str(t.get("recommended_action") or "")
        if "reports mentioning" in act.lower():
            sb = t.get("score_breakdown") or {}
            neg_pct = sb.get("negative_sentiment_pct", 50)
            t["recommended_action"] = f"Audit the user flow for {clean_title.lower()} and deploy targeted remediations to drive down the {neg_pct}% grievance rate."


def normalize_title_groups(
    groups: List[Any],
    allow_ai: bool = True,
    revise_placeholders: bool = True,
) -> None:
    """
    Retitle several topic kinds in one model call.

    `groups` is a list of `(topics, topic_type)` pairs. Titles are written back onto the
    topics in place; nothing is returned, because the caller already owns the lists.

    This is the same work as calling `normalize_topic_titles` once per group, which is what
    it replaces — the difference is one round trip instead of one per group.
    """
    pending_by_group: List[tuple] = []
    payload: List[Dict[str, Any]] = []
    for topics, topic_type in groups:
        if not topics:
            pending_by_group.append((topics, topic_type, []))
            continue
        pending = [t for t in topics if needs_title_upgrade(t, topic_type, allow_ai, revise_placeholders)]
        pending_by_group.append((topics, topic_type, pending))
        payload.extend(_topic_payload(pending, topic_type, offset=len(payload), with_kind=True))

    if not payload:
        return

    topic_types = [topic_type for _topics, topic_type, pending in pending_by_group if pending]
    prompt = _title_prompt(payload, topic_types)
    resolved: Dict[int, str] = {}

    if allow_ai:
        deadline = time.time() + TITLE_BATCH_BUDGET_SECONDS

        def _call_timeout() -> float:
            return max(1.0, min(TITLE_CALL_TIMEOUT_SECONDS, deadline - time.time()))

        def _gemini_titles(client, model, text_prompt):
            from google.genai import types
            response = client.models.generate_content(
                model=model,
                contents=text_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            return response.text

        def _chat_titles(client, model, text_prompt, max_tokens=800):
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a Principal Product Manager. Output ONLY a valid JSON array."},
                    {"role": "user", "content": text_prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
                timeout=_call_timeout(),
            )
            return response.choices[0].message.content

        def _openrouter_titles(client, model, text_prompt):
            return _chat_titles(client, model, text_prompt, max_tokens=min(OPENROUTER_MAX_TOKENS, 4000))

        attempts = [
            ("Groq", get_groq_client(), GROQ_MODELS, _chat_titles),
            ("OpenRouter", get_openrouter_client(), OPENROUTER_MODELS, _openrouter_titles),
            ("Gemini", get_gemini_client(), GEMINI_MODELS, _gemini_titles),
            ("Mistral", get_mistral_client(), MISTRAL_MODELS, _chat_titles),
        ]
        attempts = [a for a in attempts if a[1] is not None and not provider_in_cooldown(a[0])]

        calls = 0
        round_index = 0
        throttled: set = set()
        while calls < TITLE_BATCH_ATTEMPTS and len(resolved) < len(payload):
            if time.time() >= deadline:
                logger.info(
                    "Title batch budget spent after %d call(s); %d of %d titles left as placeholders.",
                    calls, len(payload) - len(resolved), len(payload),
                )
                break
            asked = False
            for provider, client, models, fetch in attempts:
                if round_index >= len(models) or provider in throttled:
                    continue
                if calls >= TITLE_BATCH_ATTEMPTS or time.time() >= deadline:
                    break
                asked = True
                model = models[round_index]
                calls += 1
                call_started = time.time()
                try:
                    text = fetch(client, model, prompt)
                    logger.info(
                        "%s (%s) answered the title batch in %.1fs",
                        provider, model, time.time() - call_started,
                    )
                except Exception as e:
                    logger.info(
                        "%s (%s) failed the title batch after %.1fs: %s",
                        provider, model, time.time() - call_started, e,
                    )
                    if is_provider_throttled(e):
                        # Kept local to this pass. `mark_provider_throttled` writes to the
                        # shared 5-minute registry that the analysis stage reads, and one
                        # free OpenRouter model answering 429 is not the provider refusing
                        # traffic: measured live, a re-run within the same minute found
                        # OpenRouter skipped and fell back to the deterministic engine
                        # because a title call had stood the provider down.
                        throttled.add(provider)
                    continue
                for index, title in _parse_title_array(text, len(payload)).items():
                    resolved.setdefault(index, title)
                if resolved:
                    logger.info(
                        "%s (%s) normalized %d titles (%d/%d)",
                        provider, model, len(resolved), len(resolved), len(payload),
                    )
            if not asked:
                break
            round_index += 1

    # Distribute the answers back to the group that asked for them, then let each group
    # fill its own gaps heuristically.
    cursor = 0
    for topics, topic_type, pending in pending_by_group:
        if pending:
            local = {
                index - cursor: title
                for index, title in resolved.items()
                if cursor <= index < cursor + len(pending)
            }
            cursor += len(pending)
            _apply_normalized_titles(pending, topic_type, local)


def normalize_topic_titles(
    topics: List[Dict[str, Any]],
    topic_type: str = "pain_point",
    allow_ai: bool = True,
    revise_placeholders: bool = True,
) -> List[Dict[str, Any]]:
    """
    Auto-upgrade raw algorithmic topic titles into clean, professional PM titles.
    Runs a fast, batched prompt across top AI providers with heuristic fallback.

    Only the topics that still need it are sent, so a second pass over an already-upgraded
    analysis neither rewrites titles that were already good nor calls the model again.
    """
    if not topics:
        return []

    # Early exit if nothing is left to upgrade (avoids repeated network calls)
    pending = [t for t in topics if needs_title_upgrade(t, topic_type, allow_ai, revise_placeholders)]
    if not pending:
        return topics

    # 1. Build compact batch payload for the pending topics only, keyed by payload position
    payload = []
    for idx, t in enumerate(pending):
        raw = _display_title(t, topic_type) or f"Topic {idx+1}"
        quotes = t.get("sample_quotes") or t.get("sample_requests") or t.get("distinct_sample_quotes") or []
        quote = str(quotes[0]).strip() if quotes else ""
        if len(quote) > 160:
            quote = quote[:160] + "..."
        kws = [str(k) for k in (t.get("keywords") or [])[:5]]
        payload.append({
            "id": idx,
            "raw_title": raw,
            "keywords": kws,
            "customer_quote": quote,
        })

    prompt = f"""You are a Principal Product Manager.
Review these raw, algorithmic customer feedback topics ({topic_type}s). Each topic has an unpolished n-gram title and a real customer quote.
Rewrite each raw title into a clean, concise, 3-6 word professional Product Defect / Feature Opportunity title (e.g., 'Shuffle Repeats Same Tracks', 'Limited Song Skips on Free Tier', 'Offline Download Restrictions').
Directly address the user's actual grievance or request based on their quote.

Input:
{json.dumps(payload, indent=2)}

Return ONLY a valid JSON array matching this exact format, with no markdown code fences or explanations:
[
  {{"id": 0, "title": "Concise Professional Title"}}
]
"""

    parsed_titles: Dict[int, str] = {}
    # Started once there is work to do: a pass that never makes a call never spends it.
    deadline = time.time() + TITLE_UPGRADE_BUDGET_SECONDS

    def _call_timeout() -> float:
        """Seconds left for the next call, never below a value the SDK accepts."""
        return max(1.0, min(TITLE_CALL_TIMEOUT_SECONDS, deadline - time.time()))

    def _budget_spent() -> bool:
        return time.time() >= deadline

    # Shared with the batched entry point above so both read a reply the same way.
    _titles_from_response = _parse_title_array

    def _record(found: Dict[int, str]) -> int:
        """Keep the titles a model returned; the next one fills whatever it left out."""
        added = 0
        for index, title in found.items():
            if index not in parsed_titles:
                parsed_titles[index] = title
                added += 1
        return added

    def _gemini_titles(client, model: str, text_prompt: str) -> str:
        from google.genai import types
        response = client.models.generate_content(
            model=model,
            contents=text_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )
        return response.text

    # The OpenRouter free models reason before answering and reasoning tokens are billed
    # against `max_tokens`, so the 800 that is right for a chat model's short JSON array is
    # not enough for them: they spend it thinking and return an empty string. One cap per
    # provider, so a title pass is never silently handed an answer-less response.
    def _chat_titles(client, model: str, text_prompt: str, max_tokens: int = 800) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a Principal Product Manager. Output ONLY a valid JSON array."},
                {"role": "user", "content": text_prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            timeout=_call_timeout(),
        )
        return response.choices[0].message.content

    def _openrouter_titles(client, model: str, text_prompt: str) -> str:
        return _chat_titles(client, model, text_prompt, max_tokens=min(OPENROUTER_MAX_TOKENS, 4000))

    if allow_ai:
        # 2-4. Every configured provider. A partial answer used to end the search, so one
        # answered topic left the rest on heuristic placeholders. Providers are taken in
        # turns now — a different model family answers the gaps rather than another variant
        # of the one that just fell short. The attempt cap keeps a page read bounded;
        # anything still unanswered stays a placeholder for a later upgrade run to retry.
        attempts = [
            # Groq first: it answers a title batch in about a second when it is not rate
            # limited. allam-2-7b is left out of this list — measured across providers it
            # never returned a parsable JSON array, so it only spent the budget.
            ("Groq", get_groq_client(), GROQ_MODELS, _chat_titles),
            ("OpenRouter", get_openrouter_client(), OPENROUTER_MODELS, _openrouter_titles),
            ("Gemini", get_gemini_client(), GEMINI_MODELS, _gemini_titles),
            ("Mistral", get_mistral_client(), MISTRAL_MODELS, _chat_titles),
        ]
        # Providers already cooling down are dropped before any request is made, so a
        # provider that refused an earlier call is not asked again here.
        attempts = [a for a in attempts if not provider_in_cooldown(a[0])]
        calls = 0
        round_index = 0
        # Providers that are refusing traffic right now. Rotating a throttled provider back
        # in on the next round only buys another timeout for the same refusal, which is what
        # stretched this loop out while Gemini and Mistral were both rate-limited.
        throttled: set = set()
        while calls < MAX_TITLE_ATTEMPTS and len(parsed_titles) < len(pending):
            if _budget_spent():
                logger.info(
                    "Title upgrade budget spent after %d call(s); %d of %d titles left as placeholders.",
                    calls, len(pending) - len(parsed_titles), len(pending),
                )
                break
            asked = False
            for provider, client, models, fetch in attempts:
                if client is None or round_index >= len(models) or provider in throttled:
                    continue
                if calls >= MAX_TITLE_ATTEMPTS or len(parsed_titles) >= len(pending):
                    break
                if _budget_spent():
                    break
                asked = True
                model = models[round_index]
                calls += 1
                try:
                    text = fetch(client, model, prompt)
                except Exception as e:
                    logger.debug(f"{provider} title normalization error on {model}: {e}")
                    if is_provider_throttled(e):
                        throttled.add(provider)
                        mark_provider_throttled(provider)
                        logger.info(f"{provider} is throttled; dropping it from title normalization.")
                    continue
                added = _record(_titles_from_response(text, len(pending)))
                if added:
                    logger.info(
                        f"{provider} ({model}) normalized {added} titles "
                        f"({len(parsed_titles)}/{len(pending)} so far)"
                    )
            if not asked:
                break
            round_index += 1

    # 5. Apply normalized titles with heuristic fallback
    for idx, t in enumerate(pending):
        raw = _display_title(t, topic_type) or f"Topic {idx+1}"
        kws = t.get("keywords") or []
        quotes = t.get("sample_quotes") or t.get("sample_requests") or []
        quote = str(quotes[0]) if quotes else ""

        if idx in parsed_titles and len(parsed_titles[idx]) >= 4:
            clean_title = parsed_titles[idx]
            title_source = TITLE_SOURCE_AI
        else:
            clean_title = _heuristic_fallback_title(raw, kws, quote, topic_type)
            title_source = TITLE_SOURCE_HEURISTIC

        # The algorithmic title is recorded once, so a later pass can never mistake an
        # upgraded title for the raw one it came from.
        if topic_type == "cluster":
            t["raw_cluster_name"] = t.get("raw_cluster_name") or raw
            t["cluster_name"] = clean_title
            t["ai_cluster_name"] = clean_title
        else:
            t["raw_title"] = t.get("raw_title") or raw
            t["title"] = clean_title
            t["ai_title"] = clean_title
        t["title_source"] = title_source

        # Upgrade robotic description templates into executive-ready PM phrasing
        desc = str(t.get("description") or "")
        if "complaints mention" in desc.lower():
            sb = t.get("score_breakdown") or {}
            c = sb.get("frequency") or t.get("affected_users_count") or 1
            avg = sb.get("avg_rating") or 2.0
            neg = sb.get("negative_sentiment_pct")
            neg_clause = f", {neg}% negative reports" if neg else ""
            t["description"] = f"Recurring customer complaints highlight severe friction regarding {clean_title.lower()} across {c} user signals (avg rating {avg}/5.0{neg_clause})."

        act = str(t.get("recommended_action") or "")
        if "reports mentioning" in act.lower():
            sb = t.get("score_breakdown") or {}
            neg_pct = sb.get("negative_sentiment_pct", 50)
            t["recommended_action"] = f"Audit the user flow for {clean_title.lower()} and deploy targeted remediations to drive down the {neg_pct}% grievance rate."

    return topics
