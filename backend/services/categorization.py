"""
Rule-based categorization and sentiment detection service.

Classification is deterministic: generic English phrasing for failures, requests and
performance problems is matched on whole words, every category is scored, and the
strongest signal wins. There is no per-app vocabulary here — a record that carries no
such signal is honestly reported as general_feedback rather than forced into a bucket.
"""

import re
from typing import Dict, List, Optional, Tuple

from database import db

# Generic English phrases per category. Order defines the tie-break priority.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "bug_report": [
        "bug", "bugs", "crash", "crashes", "crashing", "error", "errors", "broken",
        "fails", "fail", "failing", "failed", "exception", "not working", "doesnt work",
        "doesn't work", "does not work", "wont work", "won't work", "frozen", "freeze",
        "freezes", "glitch", "glitches", "defect", "wrong", "incorrect", "unexpected",
        "unresponsive", "stuck", "hang", "hangs", "corrupt", "corrupted", "404", "500",
        "timeout", "refused", "segfault", "overflow", "null pointer", "stopped working",
        "keeps closing", "closes", "shuts down", "black screen", "blank screen",
        "no sound", "wont load", "won't load", "wont play", "won't play", "cant open",
        "can't open", "cannot open", "cant log", "can't log", "stopped", "disappeared",
        "keeps stopping", "signed out", "logs me out", "missing item", "missing items",
        "missing food", "missing drink", "missing dessert", "missing order", "wrong order",
        "wrong item", "spilled", "not delivered", "fees add up", "overcharged",
    ],
    "feature_request": [
        "feature", "features", "wish", "would like",
        "could you", "please add", "suggestion", "suggestions", "improve", "improved",
        "enhancement", "request", "requests", "want", "wants", "need", "needs",
        "it would be great", "would be great", "would be nice",
        "it would be nice", "would be helpful", "support for", "ability to",
        "option to", "option for", "can we", "is there a way", "how about",
        "would love", "bring back", "please bring", "restore", "allow us", "let us",
        "why cant", "why can't", "when will", "should have", "upgrade",
        "could you add", "would like to see", "add support", "add option",
        "add feature", "add ability", "add filter", "add button", "add payment",
        "missing feature", "missing option", "missing capability", "wish there was",
        "requesting", "suggest adding", "it would help if", "can you provide",
    ],
    "performance_issue": [
        "slow", "slower", "slowness", "lag", "laggy", "lagging", "performance",
        "speed", "delay", "delays", "delayed", "latency", "loading", "loads slowly",
        "takes too long", "takes forever", "unresponsive", "memory", "cpu", "battery",
        "heating", "overheating", "choppy", "framerate", "fps", "bandwidth",
        "optimize", "optimization", "heavy", "resource", "buffering", "buffers",
        "freezing up", "very slow", "too slow", "not loading",
    ],
}

POSITIVE_KEYWORDS: List[str] = [
    "great", "excellent", "amazing", "love", "loves", "awesome", "fantastic", "good",
    "nice", "perfect", "wonderful", "best", "brilliant", "helpful", "easy", "smooth",
    "fast", "reliable", "recommend", "recommended", "thank", "thanks", "pleased",
    "satisfied", "impressed", "enjoy", "enjoying", "happy", "delighted", "superb",
    "outstanding", "useful", "handy", "convenient", "on time", "warm", "quick",
    "quickly", "prompt", "promptly", "polite", "delicious", "fresh", "generous",
    "honest", "smoothly", "flawless", "courteous", "friendly", "fair price", "seamless",
]

NEGATIVE_KEYWORDS: List[str] = [
    "bad", "terrible", "awful", "worst", "hate", "horrible", "poor", "disappointing",
    "disappointed", "frustrating", "frustrated", "annoying", "annoyed", "useless",
    "waste", "broken", "slow", "crash", "crashes", "error", "errors", "fail", "fails",
    "bug", "bugs", "painful", "unacceptable", "unusable", "rage", "angry", "upset",
    "sucks", "garbage", "refund", "uninstall", "delete", "never again", "trash",
    "scam", "rip off", "worse", "missing", "wrong", "cold", "soggy", "spilled",
    "no help", "unhelpful", "closed ticket", "closed the ticket", "did not fix",
    "could not fix", "not delivered", "overcharged", "charging extra", "disappeared",
    "draining", "drain", "lags", "lagging", "fees add up",
]



def _build_matchers(keywords: List[str]) -> Tuple[Optional[re.Pattern], Optional[re.Pattern]]:
    """
    Compile one whole-word pattern and one phrase pattern for a keyword list.

    Whole-word matching matters: plain substring search classified any review containing
    "address" as a feature request because it contains "add". One alternation per list
    keeps this fast enough for ten-thousand-record imports.
    """
    singles = [keyword for keyword in keywords if " " not in keyword]
    phrases = [keyword for keyword in keywords if " " in keyword]
    single_pattern = (
        re.compile(r"\b(?:" + "|".join(re.escape(k) for k in singles) + r")(?:s|es|ed|d|ing|ly)?\b", re.IGNORECASE)
        if singles else None
    )
    phrase_pattern = (
        re.compile("|".join(re.escape(p) for p in phrases), re.IGNORECASE)
        if phrases else None
    )
    return single_pattern, phrase_pattern


def _score(single_pattern: Optional[re.Pattern], phrase_pattern: Optional[re.Pattern], text: str) -> int:
    """Distinct matched keywords, with multi-word phrases weighing double."""
    score = 0
    if single_pattern:
        score += len({match.group(0).lower() for match in single_pattern.finditer(text)})
    if phrase_pattern:
        score += 2 * len({match.group(0).lower() for match in phrase_pattern.finditer(text)})
    return score


_MATCHERS: Dict[str, Tuple[Optional[re.Pattern], Optional[re.Pattern]]] = {
    category: _build_matchers(keywords) for category, keywords in CATEGORY_KEYWORDS.items()
}

_POSITIVE_MATCHER = _build_matchers(POSITIVE_KEYWORDS)
_NEGATIVE_MATCHER = _build_matchers(NEGATIVE_KEYWORDS)


def categorize(text: str) -> str:
    """
    Classify feedback intent from generic English phrasing.

    Every category is scored (phrases weigh more than single words) and the strongest
    signal wins; no signal at all means general_feedback, which is the honest answer for
    praise and opinion that states neither a defect nor a request.
    """
    if not text:
        return "general_feedback"

    scores: Dict[str, int] = {
        category: _score(single_pattern, phrase_pattern, text)
        for category, (single_pattern, phrase_pattern) in _MATCHERS.items()
    }

    best_category = max(scores, key=lambda category: scores[category])
    return best_category if scores[best_category] > 0 else "general_feedback"


def detect_sentiment(text: str, rating: int = None) -> str:
    """
    Detect the sentiment of feedback.
    Priority: rating-based > keyword-based > default neutral.
    """
    if rating is not None:
        if rating >= 4:
            return "positive"
        elif rating == 3:
            return "neutral"
        else:
            return "negative"

    if not text:
        return "neutral"

    positive_count = _score(*_POSITIVE_MATCHER, text)
    negative_count = _score(*_NEGATIVE_MATCHER, text)

    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    return "neutral"


async def batch_categorize(workspace_id: str) -> Dict[str, int]:
    """
    Categorize every uncategorized record in a workspace.

    Writes are grouped into bulk operations: a per-record round trip made this endpoint
    unusable on large imports.
    """
    cursor = db.feedback.find({"workspace_id": workspace_id, "category": None})
    records = await cursor.to_list(length=None)

    processed = 0
    operations = []

    for record in records:
        processed += 1
        combined_text = f"{record.get('title', '')} {record.get('content', '')}".strip()
        operations.append((
            record["_id"],
            {
                "category": categorize(combined_text),
                "sentiment": detect_sentiment(combined_text, record.get("rating")),
            },
        ))

    from pymongo import UpdateOne

    updated = 0
    for start in range(0, len(operations), 500):
        chunk = operations[start : start + 500]
        writes = [UpdateOne({"_id": record_id}, {"$set": fields}) for record_id, fields in chunk]
        result = await db.feedback.bulk_write(writes, ordered=False)
        updated += result.modified_count

    return {"processed": processed, "updated": updated}
