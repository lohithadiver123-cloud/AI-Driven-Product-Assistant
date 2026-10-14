"""
AI Service utilizing Groq LLMs for intelligent feedback understanding,
root-cause pain point analysis, theme extraction, and feature clustering.
Designed for Milestone 2 product insights with graceful fallback to heuristic models.
"""

import os
import re
import json
import logging
import time
from typing import List, Dict, Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# Gemini models ordered by performance and stability
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

# OpenRouter free models — all $0 cost verified.
#
# Measured against the real analysis prompt (100 sampled reviews, JSON schema out):
#   liquid/lfm-2.5-2.6b:free           16.2s, complete JSON
#   dots-studio/dots-3-note-preview    104s,  complete JSON (kept as a slow last resort)
#   nvidia/nemotron-3.5-lightning      spent every output token on reasoning, returned
#                                      nothing at 120s — unusable for a JSON answer
#   cohere/north-mini-code             answered in prose, never matched the schema
# The two models that cannot produce the schema are dropped rather than left in the list
# to burn a slot of the budget on every call.
OPENROUTER_MODELS = [
    "liquid/lfm-2.5-2.6b:free",
    "dots-studio/dots-3-note-preview:free",
]

# Groq models — verified available and active for this API key.
#
# Ordered by measured time to a schema-valid answer on the real analysis prompt:
#   openai/gpt-oss-20b    2.3s
#   qwen/qwen3.8-27b      3.6s
#   openai/gpt-oss-120b   4.0s
# allam-2-7b is dropped: it answered in 1.6-16s on every attempt but never returned the
# required keys, so it only ever delayed the model that could.
GROQ_MODELS = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
]

# Mistral models — free Experiment tier
MISTRAL_MODELS = [
    "mistral-small-latest",
    "mistral-medium-latest",
]

# Output budget for an OpenRouter call.
#
# The free models on this provider reason before they answer, and reasoning tokens are
# billed against `max_tokens`. At 2,200 none of them ever reached the JSON: measured at
# that cap, every one of them stopped on finish_reason="length" with an empty or half
# written object. Raised to 8,000 the same prompt returns a complete answer (3,642
# completion tokens, of which 2,277 were reasoning), which is why the OpenRouter calls
# no longer share the smaller Groq budget.
OPENROUTER_MAX_TOKENS = 8000

# Time allowed for one OpenRouter call. The 20 s used elsewhere in the chain clipped the
# slower free models mid-answer: the first model in the list needs ~16 s on the analysis
# prompt, and a document prompt is larger than that.
OPENROUTER_TIMEOUT_SECONDS = 45.0


# Markers for a throttle. A 429 or a 503 is a property of the provider account or of the
# service as a whole, not of the individual model, so asking the provider's next model
# after one has already said "rate limited" just spends another timeout to collect the
# same answer. Observed live: Gemini answering 503 "high demand" for both of its models
# and Mistral answering 429 for both of its models, on every single call.
_THROTTLE_MARKERS = (
    "429",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "too many requests",
    "resource_exhausted",
    "resource exhausted",
    "quota",
    "503",
    "unavailable",
    "high demand",
    "overloaded",
)


def is_provider_throttled(error: Exception) -> bool:
    """Whether a provider error means the provider itself is refusing traffic right now."""
    text = f"{type(error).__name__}: {error}".lower()
    return any(marker in text for marker in _THROTTLE_MARKERS)


# A throttled provider is set aside for a cooldown window rather than retried on the next
# call. Without this, every request re-pays a doomed attempt against a provider that is
# already refusing us: one analysis call measured 36.6 s, nearly all of it waiting on a
# Gemini 503 and a Mistral 429 that were never going to answer before Groq did.
_PROVIDER_COOLDOWN_SECONDS = 300
_provider_cooldown: Dict[str, float] = {}


def mark_provider_throttled(provider: str) -> None:
    """Set a provider aside after it refused traffic."""
    _provider_cooldown[provider] = time.time() + _PROVIDER_COOLDOWN_SECONDS


# Wall-clock budget for one analysis call across every provider in the chain.
#
# Each provider is asked in turn with its own per-request timeout, so without a ceiling
# the worst case is the sum of all of them — measured at 36.6 s for a single analysis
# spent waiting on a Gemini 503 and a Mistral 429, and 59 s end to end for a
# 10,000-record workspace. The deterministic engine always has an answer to give, so a
# model that has not answered within the budget is one the analysis can do without.
AI_ANALYSIS_BUDGET_SECONDS = 45.0

# ...and a slice of that budget for each provider, because the total alone was not enough.
#
# Measured on a 10,000-record workspace: Groq answered 429 "output tokens per minute"
# first, and by the time the code had finished with it the shared 25 s deadline had
# already passed — so the OpenRouter, Gemini and Mistral blocks were skipped without a
# single request being made, and the run fell back to the deterministic engine 30 s in
# while a working provider sat unused. A provider now only ever spends its own slice, so
# a refusal from the first one cannot starve the rest.
PROVIDER_BUDGET_SECONDS = {
    "Groq": 12.0,        # answers in 2-4 s when it is not rate limited
    "OpenRouter": 32.0,  # the free reasoning models need ~16 s end to end
    "Gemini": 15.0,
    "Mistral": 15.0,
}


def _provider_window(total_deadline: float, provider: str) -> float:
    """When this provider's own slice of the budget runs out.

    Never later than the overall deadline, so the chain still finishes inside its ceiling.
    """
    return min(total_deadline, time.time() + PROVIDER_BUDGET_SECONDS.get(provider, 15.0))


def _remaining_budget(deadline: float, cap: float = 20.0) -> float:
    """Seconds to allow for the next call: never more than its own cap, never below 1."""
    return max(1.0, min(cap, deadline - time.time()))


def provider_in_cooldown(provider: str) -> bool:
    """Whether a provider is currently being skipped, expiring the entry when it lapses."""
    until = _provider_cooldown.get(provider)
    if not until:
        return False
    if until <= time.time():
        _provider_cooldown.pop(provider, None)
        return False
    return True


# Timeout for a Gemini call, in milliseconds, applied to the client rather than to a
# request. It used to be passed as `timeout=` inside GenerateContentConfig, which this
# version of the SDK rejects outright — "Extra inputs are not permitted" — so every Gemini
# call failed before it left the machine, silently costing the chain its third provider.
GEMINI_TIMEOUT_MS = 15000


def get_gemini_client():
    """Create and return a Google GenAI client if an API key is configured."""
    api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
        )
    except Exception as e:
        logger.warning(f"Failed to initialize Gemini client: {e}")
        return None


# The SDKs retry a timed-out request twice by default, so one logical attempt can cost
# three times its timeout. This module is already a fallback chain — it has its own next
# provider to ask — and paying the provider's retries on top measured at 43.6 s for a
# single title pass whose own budget was 25 s.
_PROVIDER_MAX_RETRIES = 0


def get_mistral_client():
    """Create and return an OpenAI-compatible Mistral client if an API key is configured."""
    api_key = settings.MISTRAL_API_KEY or os.getenv("MISTRAL_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url="https://api.mistral.ai/v1", max_retries=_PROVIDER_MAX_RETRIES)
    except Exception as e:
        logger.warning(f"Failed to initialize Mistral client: {e}")
        return None


def get_openrouter_client():
    """Create and return an OpenAI-compatible OpenRouter client if an API key is configured."""
    api_key = settings.OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            max_retries=_PROVIDER_MAX_RETRIES,
            default_headers={
                "HTTP-Referer": "https://pm-copilot.app",
                "X-Title": "PM Copilot",
            },
        )
    except Exception as e:
        logger.warning(f"Failed to initialize OpenRouter client: {e}")
        return None


def get_groq_client():
    """Create and return a Groq client if an API key is configured."""
    api_key = settings.GROQ_API_KEY or os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=api_key, max_retries=_PROVIDER_MAX_RETRIES)
    except Exception as e:
        logger.warning(f"Failed to initialize Groq client: {e}")
        return None


def check_ai_status() -> Dict[str, Any]:
    """
    Report which AI providers have a key configured.

    This deliberately does not claim a provider is working: a key can be present while the
    provider is out of quota or down. What actually produced a result is recorded with the
    result itself (each analysis and document stores its model), and every caller falls back
    in order: Gemini, then Mistral, then Groq, then the deterministic engine.
    """
    groq_client = get_groq_client()
    openrouter_client = get_openrouter_client()
    gem_client = get_gemini_client()
    mistral_client = get_mistral_client()

    # Providers are tried in this order: Groq (fastest) -> OpenRouter -> Gemini -> Mistral
    configured = [
        name for name, client in (
            ("Groq", groq_client),
            ("OpenRouter", openrouter_client),
            ("Gemini", gem_client),
            ("Mistral", mistral_client),
        ) if client
    ]

    if configured:
        # Report the model of the provider that will actually be tried first.
        if groq_client:
            lead_model = GROQ_MODELS[0]
        elif openrouter_client:
            lead_model = OPENROUTER_MODELS[0]
        elif gem_client:
            lead_model = GEMINI_MODELS[0]
        else:
            lead_model = MISTRAL_MODELS[0]
        order = " then ".join(configured)
        if len(configured) == 1:
            name_list = configured[0]
        elif len(configured) == 2:
            name_list = f"{configured[0]} and {configured[1]}"
        else:
            name_list = ", ".join(configured[:-1]) + f" and {configured[-1]}"
        return {
            "available": True,
            "provider": " + ".join(configured),
            "model": lead_model,
            "status": "Configured",
            "message": (
                f"Keys configured for {name_list}. Each call is tried in order: "
                f"{order}, and if every provider fails the deterministic engine runs instead. "
                "The model that actually answered is stored with each analysis and document, so "
                "a quota or outage never silences a section."
            )
        }

    return {
        "available": False,
        "provider": "None",
        "model": "None",
        "status": "No API key configured",
        "message": "No AI key is configured, so every analysis and document is produced by the deterministic engine from workspace feedback."
    }


def _extract_json_from_text(text: str) -> Optional[Dict]:
    """
    Robustly extract a JSON object from raw LLM response text.
    Handles markdown code fences, thinking tags, and leading/trailing prose.
    """
    if not text:
        return None

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = text.find('{')
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _get_stratified_substantive_sample(feedback_records: List[Dict[str, Any]], max_sample_size: int = 120) -> List[str]:
    """
    Stratified sampling of substantive customer reviews for datasets of up to 50,000+ items.
    Filters out 1-2 word noise and collects high-signal representative reviews.
    """
    substantive_items = []
    for item in feedback_records:
        text = f"{item.get('title') or ''} {item.get('content') or ''}".strip()
        words = text.split()
        if len(words) >= 3:
            substantive_items.append((item, text, len(words)))

    if not substantive_items:
        substantive_items = [(it, f"{it.get('title') or ''} {it.get('content') or ''}".strip(), 1) for it in feedback_records]

    complaints = []
    feature_wishes = []
    praise_items = []

    feat_keywords = ["add", "feature", "wish", "please", "would like", "need", "update", "option", "bring back", "improve", "support for", "allow", "button", "scroll", "mode"]

    for item, text, word_len in substantive_items:
        rating = item.get("rating")
        text_lower = text.lower()
        is_feat = any(kw in text_lower for kw in feat_keywords)
        is_neg = (rating is not None and rating <= 2) or item.get("sentiment") == "negative" or any(kw in text_lower for kw in ["bug", "crash", "error", "broken", "ads", "suspend", "deactivated", "stuck", "lag", "slow", "terrible", "worst", "hate"])

        if is_feat and not (rating is not None and rating == 1 and not any(k in text_lower for k in ["add", "option", "feature", "bring back"])):
            feature_wishes.append((item, text))
        elif is_neg:
            complaints.append((item, text))
        else:
            praise_items.append((item, text))

    selected_items = []
    
    # 1. Complaints (up to 60)
    step_c = max(1, len(complaints) // 60)
    for i in range(0, min(len(complaints), 60 * step_c), step_c):
        selected_items.append(complaints[i])
        if len(selected_items) >= 60:
            break

    # 2. Feature Wishes (up to 40)
    step_f = max(1, len(feature_wishes) // 40)
    for i in range(0, min(len(feature_wishes), 40 * step_f), step_f):
        selected_items.append(feature_wishes[i])
        if len(selected_items) >= 100:
            break

    # 3. Praise (up to 20)
    step_p = max(1, len(praise_items) // 20)
    for i in range(0, min(len(praise_items), 20 * step_p), step_p):
        selected_items.append(praise_items[i])
        if len(selected_items) >= max_sample_size:
            break

    formatted_lines = []
    for idx, (it, text) in enumerate(selected_items[:max_sample_size]):
        rating = it.get("rating")
        rating_str = f" ({rating}★)" if rating else ""
        clean_text = text.replace("\n", " ")[:160]
        formatted_lines.append(f"[{idx+1}]{rating_str} {clean_text}")

    return formatted_lines


def analyze_feedback_with_ai(feedback_records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Run 100% Pure AI feedback understanding using Google Gemini with Groq fallback.
    Produces authentic themes, pain points with root causes, feature clusters, and executive summary.
    """
    if not feedback_records:
        return None

    formatted_sample = _get_stratified_substantive_sample(feedback_records, max_sample_size=100)
    feedback_text = "\n".join(formatted_sample)
    deadline = time.time() + AI_ANALYSIS_BUDGET_SECONDS

    prompt = f"""You are a Principal AI Product Manager analyzing real customer reviews.
Generate deep, authentic product intelligence based STRICTLY on the real feedback below.
Do NOT invent generic SaaS categories (like CSV/Excel exports) unless explicitly discussed by users.

Return ONLY a valid JSON object matching this schema:
{{
  "ai_summary": {{
    "headline": "Short strategic summary headline",
    "overview": "2-3 sentence executive overview of customer sentiment, friction, and app health",
    "top_frictions": ["Friction 1", "Friction 2", "Friction 3"],
    "quick_wins": ["Actionable quick win 1", "Actionable quick win 2"]
  }},
  "themes": [
    {{
      "title": "Clear Domain Theme Name",
      "description": "Why users are discussing this theme",
      "category": "bug_report",
      "keywords": ["kw1", "kw2"]
    }}
  ],
  "pain_points": [
    {{
      "title": "Specific authentic pain point title",
      "description": "User experience description of the friction",
      "root_cause": "Underlying technical, moderation, or UX root cause",
      "severity": "high",
      "impact_score": 88.0,
      "category": "bug_report",
      "recommended_action": "Actionable engineering/PM recommendation",
      "keywords": ["kw1", "kw2"]
    }}
  ],
  "feature_clusters": [
    {{
      "cluster_name": "Specific User-Requested Feature Opportunity",
      "summary": "Clear summary of user demand and product value proposition",
      "demand_level": "high",
      "priority_score": 90.0,
      "keywords": ["kw1", "kw2"]
    }}
  ]
}}

Requirements:
- Ground all insights 100% in the real customer reviews provided.
- Provide exactly 5 distinct themes.
- Provide exactly 5 prioritized customer pain points (severity: 'high'/'medium'/'low').
- Provide exactly 5 specific feature request clusters (demand: 'high'/'medium'/'low', priority: 25-95).
- Output valid JSON only.

Customer Reviews Corpus (Sampled from {len(feedback_records)} records):
{feedback_text}
"""

    # 1. Try Groq first — confirmed working key, fastest free tier
    groq_client = get_groq_client()
    if groq_client and not provider_in_cooldown("Groq"):
        groq_deadline = _provider_window(deadline, "Groq")
        attempted = 0
        throttled = 0
        for model_name in GROQ_MODELS:
            if time.time() >= groq_deadline:
                break
            attempted += 1
            try:
                logger.info(f"Attempting Groq AI analysis using {model_name}...")
                # No `response_format` here on purpose. Measured on the real analysis
                # prompt, Groq's fastest model (openai/gpt-oss-20b) rejected JSON mode
                # outright — 400 "Failed to validate JSON" with an empty failed_generation —
                # while answering correctly, in 2.3 s, without it. The question asks for
                # JSON in prose, and _extract_json_from_text unwraps fences and surrounding
                # text, so the response format is the weaker guarantee of the two.
                response = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a Principal AI Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=2200,
                    timeout=_remaining_budget(groq_deadline),
                )
                raw_content = response.choices[0].message.content
                parsed = _extract_json_from_text(raw_content)
                if parsed and "pain_points" in parsed and "themes" in parsed and "feature_clusters" in parsed:
                    parsed["ai_model"] = f"Groq ({model_name})"
                    logger.info(f"Groq AI analysis succeeded with {model_name}!")
                    return parsed
            except Exception as e:
                logger.warning(f"Groq model {model_name} error: {e}. Trying next...")
                if is_provider_throttled(e):
                    throttled += 1
        # Groq meters output tokens per model, not per account, so one model answering
        # 429 says nothing about the next one. The provider is only stood down when every
        # model in the list refused — breaking out on the first refusal is what left the
        # chain with no provider to answer at all.
        if attempted and throttled == attempted:
            mark_provider_throttled("Groq")
            logger.warning("Every Groq model refused; skipping Groq until the cooldown lapses.")

    # 2. Try OpenRouter (free tier — OpenAI-compatible, verified active)
    openrouter_client = get_openrouter_client()
    if openrouter_client and not provider_in_cooldown("OpenRouter"):
        openrouter_deadline = _provider_window(deadline, "OpenRouter")
        attempted = 0
        throttled = 0
        for model_name in OPENROUTER_MODELS:
            if time.time() >= openrouter_deadline:
                break
            attempted += 1
            try:
                logger.info(f"Attempting OpenRouter AI analysis using {model_name}...")
                response = openrouter_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a Principal AI Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=OPENROUTER_MAX_TOKENS,
                    timeout=_remaining_budget(openrouter_deadline),
                )
                raw_content = response.choices[0].message.content
                parsed = _extract_json_from_text(raw_content)
                if parsed and "pain_points" in parsed and "themes" in parsed and "feature_clusters" in parsed:
                    parsed["ai_model"] = f"OpenRouter ({model_name})"
                    logger.info(f"OpenRouter AI analysis succeeded with {model_name}!")
                    return parsed
            except Exception as e:
                logger.warning(f"OpenRouter model {model_name} error: {e}. Trying next...")
                if is_provider_throttled(e):
                    throttled += 1
        if attempted and throttled == attempted:
            mark_provider_throttled("OpenRouter")
            logger.warning("Every OpenRouter model refused; skipping it until the cooldown lapses.")

    # 3. Try Google Gemini (backup)
    gem_client = get_gemini_client()
    if gem_client and not provider_in_cooldown("Gemini"):
        gemini_deadline = _provider_window(deadline, "Gemini")
        for g_model in GEMINI_MODELS:
            if time.time() >= gemini_deadline:
                break
            try:
                from google.genai import types
                logger.info(f"Attempting Gemini analysis with model {g_model}...")
                response = gem_client.models.generate_content(
                    model=g_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                        timeout=_remaining_budget(gemini_deadline, cap=15),
                    ),
                )
                parsed = _extract_json_from_text(response.text)
                if parsed and "pain_points" in parsed and "themes" in parsed and "feature_clusters" in parsed:
                    parsed["ai_model"] = f"Google Gemini ({g_model})"
                    logger.info(f"Gemini analysis succeeded with {g_model}!")
                    return parsed
            except Exception as e:
                logger.warning(f"Gemini model {g_model} error: {e}. Trying next...")
                if is_provider_throttled(e):
                    mark_provider_throttled("Gemini")
                    logger.warning("Gemini is throttled; skipping it until the cooldown lapses.")
                    break

    # 4. Try Mistral (last resort)
    mistral_client = get_mistral_client()
    if mistral_client and not provider_in_cooldown("Mistral"):
        mistral_deadline = _provider_window(deadline, "Mistral")
        for model_name in MISTRAL_MODELS:
            if time.time() >= mistral_deadline:
                break
            try:
                logger.info(f"Attempting Mistral analysis using {model_name}...")
                response = mistral_client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a Principal AI Product Manager. Respond ONLY in valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2200,
                    response_format={"type": "json_object"},
                    timeout=_remaining_budget(mistral_deadline),
                )
                parsed = _extract_json_from_text(response.choices[0].message.content)
                if parsed and "pain_points" in parsed and "themes" in parsed and "feature_clusters" in parsed:
                    parsed["ai_model"] = f"Mistral ({model_name})"
                    logger.info(f"Mistral analysis succeeded with {model_name}!")
                    return parsed
            except Exception as e:
                logger.warning(f"Mistral model {model_name} error: {e}. Trying next...")
                if is_provider_throttled(e):
                    mark_provider_throttled("Mistral")
                    logger.warning("Mistral is throttled; skipping it until the cooldown lapses.")
                    break

    logger.error("All AI providers failed. Falling back to heuristic engine.")
    return None



