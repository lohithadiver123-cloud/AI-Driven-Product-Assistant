"""Feedback Classification, Category Confidence Scoring, Sentiment, and Priority heuristics."""
import re
from typing import Any, Dict, List, Optional, Tuple
from app.services.preprocessing import clean_text

# 10 Controlled Categories
CATEGORIES: List[str] = [
    "Authentication",
    "Performance",
    "Payment",
    "Bug",
    "UI/UX",
    "Feature Request",
    "Notifications",
    "Account Management",
    "Integration",
    "Other",
]

CATEGORY_METADATA: Dict[str, Dict[str, str]] = {
    "Authentication": {
        "description": "User login, SSO, multi-factor auth (2FA/MFA), password reset, and access credentials.",
        "icon": "Lock",
        "color": "#6366f1",
    },
    "Performance": {
        "description": "System speed, load latency, browser responsiveness, battery drain, and timeout issues.",
        "icon": "Zap",
        "color": "#eab308",
    },
    "Payment": {
        "description": "Billing, subscriptions, double charges, credit cards, invoices, tax/VAT, and refunds.",
        "icon": "CreditCard",
        "color": "#10b981",
    },
    "Bug": {
        "description": "Application crashes, HTTP errors (500, 502), broken UI elements, and unexpected exceptions.",
        "icon": "AlertCircle",
        "color": "#ef4444",
    },
    "UI/UX": {
        "description": "Visual design, layout clarity, color contrast, dark/light themes, and navigation ergonomics.",
        "icon": "Layout",
        "color": "#8b5cf6",
    },
    "Feature Request": {
        "description": "Customer suggestions for new capabilities, custom configurations, and workflow enhancements.",
        "icon": "Sparkles",
        "color": "#06b6d4",
    },
    "Notifications": {
        "description": "Push notifications, email mention delivery, SMS alerts, and reminder delivery timing.",
        "icon": "Bell",
        "color": "#f97316",
    },
    "Account Management": {
        "description": "User roles, workspace ownership, organization members, team invites, and GDPR data erasure.",
        "icon": "Users",
        "color": "#3b82f6",
    },
    "Integration": {
        "description": "Third-party connections (Jira, Figma, Notion, Slack, GitHub, GitLab, Zapier, Webhooks).",
        "icon": "Share2",
        "color": "#ec4899",
    },
    "Other": {
        "description": "General customer comments, uncategorized inquiries, and edge-case feedback.",
        "icon": "HelpCircle",
        "color": "#6b7280",
    },
}

# Domain keyword groups with specificity weights
CATEGORY_KEYWORD_RULES: Dict[str, List[str]] = {
    "Authentication": [
        "login", "logout", "sso", "password", "2fa", "mfa", "token", "oauth",
        "credential", "session", "sign in", "sign up", "faceid", "biometric",
        "auth", "unauthorized", "401", "forbidden", "reset link", "invalid token",
        "log in", "cannot login", "reset password", "two-factor"
    ],
    "Performance": [
        "slow", "lag", "latency", "timeout", "times out", "timed out", "time out", "delay",
        "hang", "hangs", "hanging", "speed", "memory", "battery", "load time", "frozen",
        "loading", "seconds to load", "drain", "bandwidth", "504", "browser hangs", "sluggish"
    ],
    "Payment": [
        "charge", "charged", "payment", "refund", "invoice", "subscription",
        "stripe", "credit card", "checkout", "vat", "tax", "pricing", "billed",
        "receipt", "plan", "discount", "transaction", "pay", "mastercard", "visa", "charged twice"
    ],
    "Bug": [
        "crash", "crashes", "crashing", "error", "exception", "500", "502", "bug",
        "broken", "fail", "fails", "failure", "glitch", "freeze", "disappeared",
        "cannot upload", "completely broken"
    ],
    "UI/UX": [
        "dark mode", "light mode", "theme", "contrast", "color", "design",
        "layout", "font", "button", "drag and drop", "interface", "confusing",
        "navigation", "sidebar", "unreadable", "ui", "ux", "visual", "look and feel"
    ],
    "Feature Request": [
        "feature", "please add", "request", "would love", "custom role", "support for",
        "allow custom", "wish list", "suggestion", "could you add", "add export",
        "want to have", "hope to see", "custom estimation"
    ],
    "Notifications": [
        "notification", "notifications", "push notification", "email alert", "sms", "mention",
        "reminder", "bell", "delivery", "spam folder", "delayed alert", "sms code"
    ],
    "Account Management": [
        "account", "workspace", "organization", "member", "permission",
        "ownership", "delete account", "gdpr", "transfer", "profile",
        "team invite", "roles", "user role", "transfer ownership", "workspace ownership"
    ],
    "Integration": [
        "figma", "notion", "slack", "gitlab", "github", "jira", "zapier",
        "webhook", "api export", "okta", "salesforce", "export to jira", "export to notion",
        "integration", "integrations"
    ],
}

COMPILED_CATEGORY_PATTERNS = {
    cat: [(re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE), 2.0 if " " in kw else 1.0)
          for kw in keywords]
    for cat, keywords in CATEGORY_KEYWORD_RULES.items()
}

POSITIVE_WORDS = {
    "love", "great", "fantastic", "awesome", "amazing", "super", "intuitive",
    "excellent", "game changer", "helpful", "saved", "best", "perfect",
    "wonderful", "seamless", "clean", "easy", "impressed", "kudos", "brilliant"
}

NEGATIVE_WORDS = {
    "broken", "crash", "crashes", "error", "fail", "fails", "failure", "slow",
    "hate", "terrible", "worst", "bug", "issue", "unreadable", "timeout",
    "charged twice", "lost", "urgent", "cannot", "expired", "frustrating",
    "poor", "confusing", "disaster", "useless", "drain", "garbage", "bad", "failing"
}

URGENT_PHRASES = [
    "charged twice", "duplicate transaction", "data loss", "security", "gdpr",
    "delete our workspace", "urgent", "asap", "exploit", "crash every", "crashes every",
    "completely broken", "cannot login", "cannot reset", "2fa sms", "err_stripe"
]


def classify_feedback(text: str, cleaned_text: Optional[str] = None) -> Tuple[str, float]:
    """
    Classify feedback text into one of the 10 controlled categories with a confidence score.
    
    Returns:
        (category_name, confidence_score)
        Example: ("Authentication", 0.92)
    """
    if not text:
        return "Other", 0.0

    eval_text = (cleaned_text or text).lower()
    scores: Dict[str, float] = {}

    for cat_name, patterns in COMPILED_CATEGORY_PATTERNS.items():
        score = 0.0
        for pattern, weight in patterns:
            if pattern.search(eval_text):
                score += weight
        if score > 0:
            scores[cat_name] = score

    if not scores:
        return "Other", 0.30

    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    if best_score >= 4:
        confidence = min(0.96, 0.90 + 0.02 * (best_score - 4))
    elif best_score >= 3:
        confidence = 0.88
    elif best_score >= 2:
        confidence = 0.84
    else:
        confidence = 0.76

    return best_category, round(confidence, 2)


def detect_sentiment(text: str) -> str:
    """Classify sentiment polarity into Positive, Neutral, or Negative."""
    if not text:
        return "Neutral"

    lower_text = text.lower()
    pos_count = sum(1 for word in POSITIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower_text))
    neg_count = sum(1 for word in NEGATIVE_WORDS if re.search(r"\b" + re.escape(word) + r"\b", lower_text))

    if pos_count > neg_count and pos_count >= 1:
        return "Positive"
    elif neg_count > pos_count and neg_count >= 1:
        return "Negative"
    return "Neutral"


def detect_priority(text: str, category: str = "Other", sentiment: str = "Neutral") -> str:
    """Infer baseline priority rating: Urgent, High, Medium, or Low."""
    if not text:
        return "Medium"

    lower_text = text.lower()

    # 1. Critical operational keywords
    for phrase in URGENT_PHRASES:
        if phrase in lower_text:
            return "Urgent"

    # 2. Critical domain errors with negative sentiment
    if category in ["Payment", "Authentication"] and sentiment == "Negative":
        return "High"

    if category in ["Bug", "Performance"] and sentiment == "Negative":
        return "High"

    # 3. Positive reviews / low priority feedback
    if sentiment == "Positive":
        return "Low"

    return "Medium"


def analyze_feedback_item(text: str) -> Dict[str, Any]:
    """
    Convenience orchestrator returning complete analysis dictionary.
    """
    cleaned = clean_text(text)
    category, confidence = classify_feedback(text, cleaned)
    sentiment = detect_sentiment(text)
    priority = detect_priority(text, category, sentiment)

    return {
        "text": text,
        "cleaned_text": cleaned,
        "category": category,
        "category_confidence": confidence,
        "sentiment": sentiment,
        "priority": priority,
    }
