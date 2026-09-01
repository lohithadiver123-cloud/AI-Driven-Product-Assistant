"""Python text preprocessing, cleaning, categorization, and sentiment heuristics module."""
import html
import re
from typing import Dict, Optional, Tuple


# Regex patterns for text cleaning
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
MULTIPLE_SPACES_PATTERN = re.compile(r"\s+")
SPECIAL_NOISE_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Common contraction mapping for standardizing text
CONTRACTIONS_MAP: Dict[str, str] = {
    r"\bcan't\b": "cannot",
    r"\bcant\b": "cannot",
    r"\bwon't\b": "will not",
    r"\bwont\b": "will not",
    r"\bdon't\b": "do not",
    r"\bdont\b": "do not",
    r"\bdidn't\b": "did not",
    r"\bdidnt\b": "did not",
    r"\bisn't\b": "is not",
    r"\bisnt\b": "is not",
    r"\baren't\b": "are not",
    r"\barent\b": "are not",
    r"\bwasn't\b": "was not",
    r"\bwasnt\b": "was not",
    r"\bweren't\b": "were not",
    r"\bwerent\b": "were not",
    r"\bhaven't\b": "have not",
    r"\bhavent\b": "have not",
    r"\bhasn't\b": "has not",
    r"\bhasnt\b": "has not",
    r"\bhadn't\b": "had not",
    r"\bhadnt\b": "had not",
    r"\bwouldn't\b": "would not",
    r"\bwouldnt\b": "would not",
    r"\bshouldn't\b": "should not",
    r"\bshouldnt\b": "should not",
    r"\bcouldn't\b": "could not",
    r"\bcouldnt\b": "could not",
    r"\bit's\b": "it is",
    r"\bi'm\b": "i am",
    r"\bi've\b": "i have",
    r"\bwe're\b": "we are",
    r"\bthey're\b": "they are",
}


def remove_html(text: str) -> str:
    """Strip HTML markup and unescape HTML entities."""
    if not text:
        return ""
    text_unescaped = html.unescape(text)
    return HTML_TAG_PATTERN.sub(" ", text_unescaped)


def remove_urls(text: str, replacement: str = "") -> str:
    """Remove web URLs (http, https, www)."""
    if not text:
        return ""
    return URL_PATTERN.sub(replacement, text)


def remove_emails(text: str, replacement: str = "") -> str:
    """Remove or mask email addresses."""
    if not text:
        return ""
    return EMAIL_PATTERN.sub(replacement, text)


def normalize_whitespace(text: str) -> str:
    """Normalize multiple spaces, tabs, and newlines into a single clean space."""
    if not text:
        return ""
    return MULTIPLE_SPACES_PATTERN.sub(" ", text).strip()


def normalize_contractions(text: str) -> str:
    """Standardize common English contractions without altering word semantics."""
    if not text:
        return ""
    processed = text
    for pattern, replacement in CONTRACTIONS_MAP.items():
        processed = re.sub(pattern, replacement, processed, flags=re.IGNORECASE)
    return processed


# Exported function aliases
strip_html = remove_html
strip_urls = remove_urls
mask_emails = remove_emails
expand_contractions = normalize_contractions


def clean_text(text: str) -> str:
    """
    Main preprocessing pipeline for customer feedback.
    
    Transforms raw customer input into normalized, clean text suitable
    for downstream NLP and clustering while preserving core semantic meaning.
    
    Steps:
      1. Strip control characters / low-level noise
      2. Remove HTML tags and unescape entities
      3. Remove external URLs
      4. Remove email addresses
      5. Normalize contractions
      6. Normalize whitespace
    """
    if not text or not isinstance(text, str):
        return ""

    # 1. Remove binary/control noise
    cleaned = SPECIAL_NOISE_PATTERN.sub(" ", text)

    # 2. Strip HTML
    cleaned = remove_html(cleaned)

    # 3. Strip URLs
    cleaned = remove_urls(cleaned)

    # 4. Strip Emails
    cleaned = remove_emails(cleaned)

    # 5. Expand / Normalize contractions
    cleaned = normalize_contractions(cleaned)

    # 6. Normalize Whitespace
    cleaned = normalize_whitespace(cleaned)

    return cleaned
