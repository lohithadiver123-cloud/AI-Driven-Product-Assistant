"""
Corpus mining primitives shared by clustering, theme extraction and document grounding.

Everything produced here is derived from the feedback records handed in. The only
constant data in this module is generic English language material (function words,
opinion words, request phrases, acronym casing) — no product, brand, feature or
domain vocabulary belongs in this file, because every analysis surface must work
for any workspace a user imports.
"""

import hashlib
import re
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from services.preprocessing import STOPWORDS_SET


WORD_RE = re.compile(r"[a-z][a-z0-9]*")
WHITESPACE_RE = re.compile(r"\s+")

# Words that express intent, opinion or filler rather than a subject. They never
# name a theme, cluster or pain point.
INTENT_AND_OPINION_WORDS = {
    "add", "added", "adding", "adds", "want", "wanted", "needs", "need", "needed",
    "wish", "wishes", "would", "could", "should", "please", "make", "makes", "made",
    "give", "gives", "bring", "turn", "let", "lets", "allow", "request", "requested",
    "requesting", "suggest", "suggestion", "suggestions", "update", "updates",
    "updated", "fix", "fixed", "fixing", "issue", "issues", "problem", "problems",
    "thing", "things", "good", "great", "best", "bad", "worst", "love", "loved",
    "loving", "nice", "awful", "terrible", "poor", "amazing", "awesome", "cool",
    "fine", "better", "really", "very", "much", "many", "still", "now", "just",
    "also", "even", "ever", "never", "always", "sometimes", "stuff", "way", "ways",
    "keep", "keeps", "say", "says", "said", "thank", "thanks", "because", "since",
    "whenever", "however", "though", "app", "apps", "application", "version",
    "user", "users", "people", "know", "think", "star", "stars", "hoping",
    "everything", "anything", "something", "nothing", "everybody", "anybody",
    "hopefully", "hope", "seem", "seems", "felt", "feel", "feels", "looking",
    "look", "looks", "become", "kinda", "sorta", "maybe", "probably",
    "sharing", "reaches", "share", "team", "rather", "report", "reporting",
    "walk", "away", "full", "day", "days", "streets", "street", "recording",
    "counts", "count", "writing", "write", "fresh", "curious", "roadmap",
    "explain", "instance", "instances", "worth", "story", "rough", "flagging",
    "flag", "deciding", "posting", "post", "waited", "waiting", "whole",
    "happily", "happy", "sure", "decide",
}

# Generic phrasing that signals an enhancement idea rather than a plain statement.
FEATURE_INTENT_KEYWORDS = [
    "feature", "wish", "would like", "please add", "suggestion", "could you add",
    "support for", "option to", "switch between", "export", "biometric", "reach control",
    "auto scroll", "pause", "volume", "notification", "tutorial", "offline",
]

# Language that asks for a change. Generic English only.
REQUEST_MARKERS = [
    "please", "add ", "adding ", "adds ", "should be", "should have", "need ", "needs ",
    "want ", "wants ", "wish", "hope", "would like", "would love", "could you",
    "can you", "can we", "allow ", "let us", "bring back", "restore", "fix ",
    "improve", "support for", "remove ", "option to", "option for", "ability to",
    "missing feature", "missing option", "lack ", "lack of", "why can", "when will", "introduce", "make it",
    "give us", "no way to", "not able to", "unable to",
]


# Tokens that read better upper-cased inside a generated label.
ACRONYMS = {"pdf", "csv", "ui", "ux", "api", "ios", "sms", "faq", "kpi", "2fa", "mfa"}

# A group of records must share a phrase this many times to be reported.
MIN_GROUP_SIZE = 2

# Corpora at least this large get share-based filtering: a phrase mentioned in a
# large share of every record describes the whole corpus rather than a topic.
CORPUS_WIDE_SHARE_MIN_ITEMS = 20

# Word-order agreement a bigram needs before it is treated as real user phrasing.
DIRECTION_CONFIDENCE_MIN = 0.75


def content_tokens(text: Any) -> List[str]:
    """Lowercase content words with stopwords, filler, numbers and repeats removed."""
    tokens: List[str] = []
    for word in WORD_RE.findall(str(text or "").lower()):
        if len(word) < 3 or word.isdigit():
            continue
        if word in STOPWORDS_SET or word in INTENT_AND_OPINION_WORDS:
            continue
        if tokens and tokens[-1] == word:
            continue
        tokens.append(word)
    return tokens


def canonical_key(first: str, second: str) -> str:
    """Order-independent key so 'play song' and 'song play' are the same phrase."""
    return " ".join(sorted((first, second)))


def record_text(item: Dict[str, Any]) -> str:
    """Title and body of a feedback record, lowercased."""
    return f"{item.get('title') or ''} {item.get('content') or ''}".lower()


def item_phrases(item: Dict[str, Any]) -> Tuple[Set[str], Dict[str, Counter]]:
    """
    One record's content as (canonical phrase keys, surface wording votes).

    Keys are order-independent; the votes record the wording users actually typed so a
    group can be labelled with the phrasing people use most.
    """
    tokens = content_tokens(f"{item.get('title') or ''} {item.get('content') or ''}")
    keys: Set[str] = set(tokens)
    votes: Dict[str, Counter] = defaultdict(Counter)
    for first, second in zip(tokens, tokens[1:]):
        if first == second:
            continue
        key = canonical_key(first, second)
        keys.add(key)
        votes[key][f"{first} {second}"] += 1
    return keys, votes


def build_surface_index(items: List[Dict[str, Any]]) -> Tuple[List[Set[str]], Dict[str, Counter]]:
    """Phrase keys and surface wording for a whole list of records."""
    phrases_per_item: List[Set[str]] = []
    surface_index: Dict[str, Counter] = defaultdict(Counter)
    for item in items:
        keys, votes = item_phrases(item)
        phrases_per_item.append(keys)
        for key, forms in votes.items():
            surface_index[key].update(forms)
    return phrases_per_item, surface_index


def display_phrase(key: str, surface_index: Dict[str, Counter]) -> str:
    """Human wording for a canonical phrase key, using the phrasing users wrote most."""
    votes = surface_index.get(key)
    if not votes:
        return key
    return sorted(votes.items(), key=lambda item: (-item[1], item[0]))[0][0]


def direction_confidence(key: str, surface_index: Dict[str, Counter]) -> float:
    """
    Share of a phrase's wording votes that agree on one word order.

    Bigrams users actually write ("dark mode") keep a single direction. Bigrams that
    only exist because a stopword was removed ("ads song" out of "ads between songs")
    collect votes in both orders. A low confidence marks the phrase as an artifact
    rather than user vocabulary.
    """
    votes = surface_index.get(key)
    if not votes:
        return 1.0
    total = sum(votes.values())
    return votes.most_common(1)[0][1] / total if total else 1.0


def titleize(phrase: str) -> str:
    return " ".join(word.upper() if word in ACRONYMS else word.capitalize() for word in phrase.split())


def phrase_sort_key(phrase: str, phrase_freq: Counter, corpus_freq: Counter):
    """Rank phrases: most shared inside the group first, phrases before single words."""
    return (
        -phrase_freq.get(phrase, 0),
        0 if " " in phrase else 1,
        -corpus_freq.get(phrase, 0),
        phrase,
    )


def token_stem(word: str) -> str:
    """Crude deterministic stem so 'ads'/'ad' and 'song'/'songs' land in one topic."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    return word


@lru_cache(maxsize=None)
def key_stems(key: str) -> frozenset:
    """Word stems a canonical phrase key is built from."""
    return frozenset(token_stem(word) for word in key.split())


def stem_frequencies(phrase_freq) -> Counter:
    """How often each word stem is mentioned, derived from phrase frequencies."""
    stems: Counter = Counter()
    for phrase, count in phrase_freq.items():
        for stem in key_stems(phrase):
            stems[stem] += count
    return stems


def is_descriptive(phrase: str, corpus_freq: Counter, item_count: int, max_share: float) -> bool:
    """False when a phrase is mentioned in so many records it describes the whole corpus."""
    if item_count < CORPUS_WIDE_SHARE_MIN_ITEMS:
        return True
    return corpus_freq.get(phrase, 0) <= max_share * item_count


def group_by_phrases(
    phrases_per_item: List[Set[str]],
    max_groups: int,
    max_share: float = 0.2,
    min_size: int = MIN_GROUP_SIZE,
    allow_leftovers: bool = True,
) -> Tuple[List[Tuple[Optional[str], List[int]]], Counter]:
    """
    Greedy phrase grouping: repeatedly take the phrase shared by the most ungrouped
    records and make it a group.

    max_share rejects phrases that are too common to describe a subset of the corpus.
    Returns (seed phrase, member indexes) groups plus corpus-wide phrase frequencies.
    """
    item_count = len(phrases_per_item)
    corpus_freq: Counter = Counter()
    phrase_index = defaultdict(list)
    for index, phrases in enumerate(phrases_per_item):
        for phrase in phrases:
            corpus_freq[phrase] += 1
            phrase_index[phrase].append(index)

    seeds = [phrase for phrase, freq in corpus_freq.items() if freq >= min_size]
    if max_share < 1.0:
        seeds = [phrase for phrase in seeds if is_descriptive(phrase, corpus_freq, item_count, max_share)]
    seeds.sort(key=lambda phrase: (-corpus_freq[phrase], 0 if " " in phrase else 1, phrase))

    assigned = [False] * item_count
    groups: List[Tuple[Optional[str], List[int]]] = []
    for seed in seeds:
        if len(groups) >= max_groups:
            break
        members = [index for index in phrase_index[seed] if not assigned[index]]
        if len(members) < min_size:
            continue
        for index in members:
            assigned[index] = True
        groups.append((seed, members))

    leftovers = [index for index, is_assigned in enumerate(assigned) if not is_assigned]
    if allow_leftovers and leftovers and len(groups) < max_groups and len(leftovers) >= min_size:
        groups.append((None, leftovers))
    return groups, corpus_freq


def label_group(
    seed: Optional[str],
    phrase_freq: Counter,
    corpus_freq: Counter,
    item_count: int,
    surface_index: Dict[str, Counter],
    used_labels: Set[str],
    max_share: float = 0.2,
    fallback: str = "Miscellaneous Requests",
) -> str:
    """
    Name a group after the topic its records share most.

    Phrase keys are folded into word-stem topics — "too many ads", "skip ads" and
    "ads song" are one topic headed by "ad" — and the topic is labelled with the
    phrase users wrote most, so a group reads as a coherent subject instead of one
    lucky bigram. Names already used by another group are skipped so two groups can
    never share a title. Every label is user wording; nothing is invented.
    """
    def usable(phrase: str, freq_map: Counter) -> bool:
        return not freq_map.get(phrase) or is_descriptive(phrase, freq_map, item_count, max_share)

    group_stems = stem_frequencies(phrase_freq)
    corpus_stems = stem_frequencies(corpus_freq)
    seed_stems = key_stems(seed) if seed else frozenset()

    heads = sorted(
        group_stems,
        key=lambda stem: (-group_stems[stem] - (0.5 if stem in seed_stems else 0.0), stem),
    )
    for head in heads:
        if not usable(head, corpus_stems):
            continue
        topic = [key for key in phrase_freq if head in key_stems(key)]
        # Within the topic, trust only phrases users write verbatim in one direction.
        directional = sorted(
            (
                key for key in topic
                if " " in key and direction_confidence(key, surface_index) >= DIRECTION_CONFIDENCE_MIN
            ),
            key=lambda key: phrase_sort_key(key, phrase_freq, corpus_freq),
        )
        for candidate in directional:
            if not usable(candidate, corpus_freq):
                continue
            label = titleize(display_phrase(candidate, surface_index))
            if label.lower() not in used_labels:
                return label
        head_label = titleize(head)
        if head_label.lower() not in used_labels:
            return head_label
    return fallback


def group_keywords(
    label: str,
    phrase_freq: Counter,
    corpus_freq: Counter,
    surface_index: Dict[str, Counter],
    item_count: int,
    max_share: float = 0.2,
    limit: int = 5,
) -> List[str]:
    """Leading phrase first, then the group's most-shared descriptive terms."""
    keywords = [label.lower()]
    for phrase in sorted(phrase_freq, key=lambda phrase: phrase_sort_key(phrase, phrase_freq, corpus_freq)):
        if len(keywords) >= limit:
            break
        if not is_descriptive(phrase, corpus_freq, item_count, max_share):
            continue
        display = display_phrase(phrase, surface_index)
        if display not in keywords:
            keywords.append(display)
    return keywords[:limit]


def top_phrases(
    items: List[Dict[str, Any]],
    limit: int = 8,
    surface_index: Optional[Dict[str, Counter]] = None,
    max_share: Optional[float] = None,
) -> List[str]:
    """
    The phrases a set of records mentions most, in the wording users wrote them.

    Used to ground generated documents in real user vocabulary. A phrase's share of the
    set is only filtered when the caller passes max_share: a deliberately scoped subset
    (for example the records behind one cluster) may legitimately be dominated by the
    very phrase that defines it.
    """
    if not items:
        return []
    phrases_per_item, surfaces = build_surface_index(items)
    if surface_index is not None:
        surfaces = surface_index
    corpus_freq: Counter = Counter()
    for phrases in phrases_per_item:
        corpus_freq.update(phrases)

    ordered = sorted(corpus_freq, key=lambda phrase: phrase_sort_key(phrase, corpus_freq, corpus_freq))
    terms: List[str] = []
    for phrase in ordered:
        if max_share is not None and not is_descriptive(phrase, corpus_freq, len(items), max_share):
            continue
        display = display_phrase(phrase, surfaces)
        if display not in terms:
            terms.append(display)
        if len(terms) >= limit:
            break
    return terms


def match_records_by_terms(items: List[Dict[str, Any]], terms: List[str]) -> List[Dict[str, Any]]:
    """
    Records that mention any of the given terms as whole words (inflections allowed).

    Substring matching counted "downloads" as a mention of "ads", which inflated the
    request volume reported for AI clusters by an order of magnitude.
    """
    patterns = [
        re.compile(rf"\b{re.escape(str(term).lower())}(s|es|ed|d|ing)?\b")
        for term in terms
        if len(str(term).strip()) > 2
    ]
    if not patterns:
        return []
    return [item for item in items if any(pattern.search(record_text(item)) for pattern in patterns)]


def stable_topic_id(prefix: str, label: str, terms: Optional[Iterable[str]] = None) -> str:
    """
    A topic id derived from the topic itself rather than its rank.

    Rank-based ids (`pain_point_1`, `ai_cluster_3`) are renumbered whenever the analysis
    is re-run, so every document, prioritization item and roadmap entry that referenced
    one silently starts pointing at a different topic. Hashing the label's own words
    keeps an id stable for as long as the topic is described the same way.
    """
    words: Set[str] = set()
    for token in content_tokens(label):
        words.add(token_stem(token))
    for term in terms or []:
        for token in content_tokens(str(term)):
            words.add(token_stem(token))
    basis = " ".join(sorted(words)) or str(label or "topic").lower()
    return f"{prefix}_{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:10]}"


def term_mention_share(term: str, items: List[Dict[str, Any]]) -> float:
    """Share of records that mention a term at all, as a whole word."""
    if not items:
        return 0.0
    return len(match_records_by_terms(items, [term])) / len(items)


def distinctive_terms(
    terms: Iterable[Any],
    items: List[Dict[str, Any]],
    max_share: float = 0.2,
    min_items: int = CORPUS_WIDE_SHARE_MIN_ITEMS,
) -> List[str]:
    """
    Keep only the terms that actually pick a subset of the corpus out.

    A word mentioned across most of a corpus describes the corpus itself — in a music
    app, "music", "song" and "spotify" match nearly everything, so a topic defined by
    them is not a topic, and grouping on them makes several "different" issues match the
    same complaints. Terms that match nothing here are dropped for the same reason.
    """
    kept: List[str] = []
    for term in terms:
        cleaned = " ".join(str(term or "").lower().split())
        if len(cleaned) <= 2 or cleaned in kept:
            continue
        share = term_mention_share(cleaned, items)
        if share <= 0.0:
            continue
        if len(items) >= min_items and share > max_share:
            continue
        kept.append(cleaned)
    return kept


def absorb_overlapping_groups(
    groups: List[Tuple[str, Set[Any]]],
    containment: float = 0.6,
) -> Tuple[List[Tuple[str, Set[Any]]], List[Tuple[str, str]]]:
    """
    Collapse groups that describe the same records, most important group first.

    Input groups are ordered by importance. A group whose members are mostly already
    covered by a kept group is an alias of it, not a second issue — reporting both
    counts the same customers twice, which is how one complaint became four "separate"
    pain points in an earlier analysis.

    Returns (kept groups, [(absorbed label, kept label), ...]).
    """
    kept: List[Tuple[str, Set[Any]]] = []
    absorbed: List[Tuple[str, str]] = []
    for label, members in groups:
        member_set = {member for member in members if member is not None}
        if not member_set:
            continue
        for kept_label, kept_members in kept:
            if len(member_set & kept_members) / len(member_set) >= containment:
                absorbed.append((label, kept_label))
                break
        else:
            kept.append((label, member_set))
    return kept, absorbed


def request_phrases(items: List[Dict[str, Any]], limit: int = 6) -> List[str]:
    """
    Phrases used by records that ask for a change — i.e. what users say they want,
    in their own words. Generic request markers only; no product vocabulary.
    """
    asking = [
        item for item in items
        if any(marker in record_text(item) for marker in REQUEST_MARKERS)
    ]
    return top_phrases(asking or items, limit=limit, max_share=0.6)


def rating_stats(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Measured rating and sentiment summary for a set of records."""
    ratings = [item.get("rating") for item in items if item.get("rating") is not None]
    return {
        "count": len(items),
        "rated_count": len(ratings),
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "low_rating_count": sum(1 for rating in ratings if rating <= 2),
    }
