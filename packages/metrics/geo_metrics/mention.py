from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MentionMatch:
    mentioned: bool
    mention_type: str  # body | citation_only | none
    matched_term: str | None
    offset: int | None  # char offset in body if body hit


def _fold(s: str) -> str:
    """Length-preserving case fold — index i in the result maps to index i in ``s``.

    ``str.casefold()`` may change length (ß→ss, İ→i̇). Callers slice the *original*
    body with the offset we return (position_bucket, evidence_snippet), so a
    length change would silently misalign every downstream metric. Characters that
    do not fold to exactly one character are left as-is; matching them
    case-insensitively is not worth corrupting offsets for.
    """
    return "".join(c if len(c.casefold()) != 1 else c.casefold() for c in s)


def _terms(aliases: list[str]) -> list[str]:
    """Folded, de-duplicated, non-empty alias terms."""
    seen: set[str] = set()
    out: list[str] = []
    for a in aliases:
        t = _fold((a or "").strip())
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def match_brand(
    body: str,
    aliases: list[str],
    *,
    citation_text: str = "",
) -> MentionMatch:
    """Detect brand presence in answer body and/or citation blob.

    Reports the **earliest** occurrence across all aliases (docs/03 §1.2 defines
    position_bucket on the first mention). Ties at the same offset go to the
    longer, more specific alias.
    """
    terms = _terms(aliases)
    if not terms:
        return MentionMatch(False, "none", None, None)

    body_n = _fold(body or "")
    best_idx: int | None = None
    best_term: str | None = None
    for term in terms:
        idx = body_n.find(term)
        if idx < 0:
            continue
        if best_idx is None or idx < best_idx or (idx == best_idx and len(term) > len(best_term or "")):
            best_idx, best_term = idx, term
    if best_idx is not None:
        return MentionMatch(True, "body", best_term, best_idx)

    cite_n = _fold(citation_text or "")
    for term in sorted(terms, key=len, reverse=True):
        if term in cite_n:
            return MentionMatch(True, "citation_only", term, None)

    return MentionMatch(False, "none", None, None)
