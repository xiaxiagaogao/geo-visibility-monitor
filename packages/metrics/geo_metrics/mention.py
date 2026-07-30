from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MentionMatch:
    mentioned: bool
    mention_type: str  # body | citation_only | none
    matched_term: str | None
    offset: int | None  # char offset in body if body hit


def _norm(s: str) -> str:
    return s.casefold().strip()


def match_brand(
    body: str,
    aliases: list[str],
    *,
    citation_text: str = "",
) -> MentionMatch:
    """Detect brand presence in answer body and/or citation blob."""
    terms = [t for t in (_norm(a) for a in aliases) if t]
    if not terms:
        return MentionMatch(False, "none", None, None)

    body_n = _norm(body or "")
    for term in sorted(terms, key=len, reverse=True):
        idx = body_n.find(term)
        if idx >= 0:
            return MentionMatch(True, "body", term, idx)

    cite_n = _norm(citation_text or "")
    for term in sorted(terms, key=len, reverse=True):
        if term in cite_n:
            return MentionMatch(True, "citation_only", term, None)

    return MentionMatch(False, "none", None, None)
