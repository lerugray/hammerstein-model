"""Phase 1.5 fallback filter: recency-decayed lexical overlap.

Replaces the corpus-id intersection heuristic, which scored 14/92 = 15.2%
on the 2026-05-08 precision test (gate was ≥60%). The intersection signal
was degenerate at the current corpus granularity (35 entries, ~6 principle
values; verification_first dominates retrieval for almost every query).

The new filter is content-based:
  - Tokenize the new query and each prior query (alphanumeric, ≥3 chars,
    stop-word-filtered).
  - Score each prior entry by: |overlap| × max(0, 1 - age_days/30).
  - Keep entries with score ≥ min_score (default 1.0). Sort descending.

Project names, technical terms, and concept words naturally weight high
because they pass the stop-word filter and are rare. Generic audit
vocabulary ("plan", "audit", "scope") is in the stop list."""

from __future__ import annotations

import datetime as dt
import re

RECENCY_DECAY_DAYS = 30
DEFAULT_MIN_SCORE = 4.0
DEFAULT_TOP_K = 3  # cap per-query matches; data shows precision degrades fast past 3
RARE_TOKEN_THRESHOLD = 0.10  # tokens in <10% of entries count as "rare"
TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")

# Stop-words: common English + audit-template vocabulary that's universal
# across queries and therefore not a relevance signal.
STOP_WORDS = frozenset("""
the and for with not but are was were been being have has had can could will
would should may might shall must about above after again all also any because
before below between both each few from further into more most other own same
some such than then there through too under until very what when where which
while who whom why your you they them their this that these those its his her
out off over only than too they our ours you'll you're you've i'm i've it's
plan audit scope query response context content next move shape kind type form
phase ship build design make use user implement implementation system tool tools
agent agents wrapper hp.py corpus state memory cli framework
should could would maybe perhaps probably possibly really actually
basically essentially primarily entirely largely mostly mainly always usually
often sometimes rarely never just only even still already yet still rather
quite very pretty fairly less least more most much many most few several lots
new old current existing recent old previous prior earlier later final last
first time times day days week weeks month months year years today tomorrow
yesterday now soon later already then since while during before after when
how why what where which whose whom there here yes no maybe perhaps probably
operator user player ray hammerstein this that these those one two three four
five six seven eight nine ten zero
""".split())


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens ≥3 chars, stop-words removed."""
    return {t for t in TOKEN_RE.findall(text.lower()) if t not in STOP_WORDS}


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")


def compute_rare_tokens(entries: list[dict], threshold: float = RARE_TOKEN_THRESHOLD) -> set[str]:
    """Tokens that appear in fewer than `threshold` fraction of entries.
    The TF-IDF moral equivalent for sparse corpora: project names ('twar',
    'fnordos', 'pto-lens') stay; common audit vocabulary ('tests',
    'behavior', 'change') drops. This is what saves the heuristic from
    matching on shared common-English tokens."""
    if not entries:
        return set()
    df = {}
    for e in entries:
        for t in tokenize(e.get("query") or ""):
            df[t] = df.get(t, 0) + 1
    n = len(entries)
    return {t for t, c in df.items() if c / n < threshold}


def relevance_score(query_tokens: set[str], entry: dict, now: dt.datetime,
                    rare_tokens: set[str] | None = None) -> float:
    """Overlap on rare tokens × linear recency decay."""
    entry_tokens = tokenize(entry.get("query") or "")
    overlap = query_tokens & entry_tokens
    if rare_tokens is not None:
        overlap = overlap & rare_tokens
    if not overlap:
        return 0.0
    ts = entry.get("timestamp")
    if not ts:
        return 0.0
    try:
        age_days = (now - parse_ts(ts)).total_seconds() / 86400
    except (ValueError, TypeError):
        return 0.0
    recency = max(0.0, 1.0 - age_days / RECENCY_DECAY_DAYS)
    return len(overlap) * recency


def filter_by_relevance(entries: list[dict], query: str,
                        now: dt.datetime | None = None,
                        min_score: float = DEFAULT_MIN_SCORE,
                        top_k: int = DEFAULT_TOP_K,
                        rare_threshold: float = RARE_TOKEN_THRESHOLD) -> list[dict]:
    """Score every entry; return top_k above threshold, sorted by score desc.
    Output is pre-sorted — select_for_preamble preserves order."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    rare = compute_rare_tokens(entries, threshold=rare_threshold)
    scored = [(relevance_score(query_tokens, e, now, rare_tokens=rare), e) for e in entries]
    scored = [(s, e) for s, e in scored if s >= min_score]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]
