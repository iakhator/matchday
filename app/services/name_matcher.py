"""Matching clubs across providers by name.

Providers that hand over their own identifiers need none of this - the
sync path maps them directly. This is for the other case: a source that
only gives names, or a consumer asking "which of your teams is my 42?",
where the name is the only thing connecting the two.

It is deliberately a *proposer*, not a decider. Comparing this gateway
against another provider's dataset, a reasonable normalizer matched 36 of
40 fixtures and missed 4 - all one club, `Brighton` on one side and
`Brighton & Hove Albion FC` on the other. That one failed safe by finding
nothing. A looser rule would have matched the wrong club just as quietly,
and every consumer's reference would then be wrong with nothing to
indicate it.

So every proposal carries a confidence, ambiguity is reported rather than
resolved by picking a winner, and nothing here writes a mapping that is
trusted without review.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

# Dropped before comparing: they appear in one provider's rendering of a
# name and not another's, and never distinguish two real clubs from each
# other. "United" and "City" are NOT here - Manchester United and
# Manchester City differ by exactly that word.
NOISE_WORDS = {
    "fc",
    "afc",
    "cf",
    "sc",
    "ac",
    "as",
    "ss",
    "ssc",
    "sv",
    "vfb",
    "vfl",
    "tsg",
    "rc",
    "cd",
    "ud",
    "club",
    "calcio",
    "futbol",
    "football",
    "the",
}


class Confidence:
    """How much a proposal deserves to be believed."""

    EXACT = "exact"  # identical once normalized
    STRONG = "strong"  # one name contains the other in full
    WEAK = "weak"  # overlapping words, but neither contains the other
    AMBIGUOUS = "ambiguous"  # more than one candidate scored equally
    NONE = "none"  # nothing plausible


@dataclass
class Proposal:
    external_id: str
    external_name: str
    internal_id: Optional[int]
    internal_name: Optional[str]
    confidence: str
    # Populated when more than one candidate tied. Carries ids, not just
    # names: the case that most needs review is two different clubs with
    # the same name, and a list of identical strings tells a reviewer
    # nothing about which row is which.
    alternatives: Optional[List[Dict[str, object]]] = None

    @property
    def needs_review(self) -> bool:
        """EXACT still needs a human. Two different clubs genuinely share a
        normalized name across countries, and the cost of a wrong mapping
        is borne by every consumer downstream."""
        return True


def normalize(name: str) -> str:
    """Comparable form of a club name."""
    lowered = name.strip().lower()
    # Accented characters are rendered inconsistently between providers
    # (Köln / Koln / Cologne). This handles the first two; the third is a
    # translation and no normalizer will catch it - that is what review is
    # for.
    lowered = (
        lowered.replace("ö", "o")
        .replace("ä", "a")
        .replace("ü", "u")
        .replace("ß", "ss")
        .replace("é", "e")
        .replace("è", "e")
        .replace("á", "a")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    cleaned = re.sub(r"[^a-z0-9\s]", " ", lowered)
    words = [w for w in cleaned.split() if w and w not in NOISE_WORDS]
    return " ".join(words)


def _tokens(name: str) -> set:
    return set(normalize(name).split())


def _score(external_name: str, candidate_name: str) -> Optional[str]:
    """Confidence that these two names are the same club, or None."""
    a, b = normalize(external_name), normalize(candidate_name)
    if not a or not b:
        return None
    if a == b:
        return Confidence.EXACT

    # "brighton" vs "brighton hove albion" - one name is the other plus
    # detail. This is the case that broke before.
    if a.startswith(b) or b.startswith(a):
        return Confidence.STRONG

    ta, tb = _tokens(external_name), _tokens(candidate_name)
    if ta and tb and (ta <= tb or tb <= ta):
        return Confidence.STRONG

    shared = ta & tb
    if shared and len(shared) >= min(len(ta), len(tb)):
        return Confidence.STRONG
    if shared:
        return Confidence.WEAK
    return None


_RANK = {Confidence.EXACT: 3, Confidence.STRONG: 2, Confidence.WEAK: 1}


def propose(
    external_entries: Sequence[Dict[str, str]],
    candidates: Sequence[Dict[str, object]],
) -> List[Proposal]:
    """Suggest a gateway row for each external entry.

    `external_entries` are `{"external_id": ..., "name": ...}` from the
    other provider; `candidates` are `{"id": ..., "name": ...}` from here.

    A tie is reported as AMBIGUOUS rather than broken arbitrarily. Picking
    one of two equally-good matches is how the wrong club gets mapped, and
    it is precisely the case a human should see.
    """
    proposals: List[Proposal] = []

    for entry in external_entries:
        external_id = str(entry["external_id"])
        external_name = str(entry["name"])

        scored = []
        for candidate in candidates:
            confidence = _score(external_name, str(candidate["name"]))
            if confidence:
                scored.append((_RANK[confidence], confidence, candidate))

        if not scored:
            proposals.append(
                Proposal(external_id, external_name, None, None, Confidence.NONE)
            )
            continue

        best_rank = max(s[0] for s in scored)
        best = [s for s in scored if s[0] == best_rank]

        # A club can appear as more than one candidate - its registered name
        # and its short name are both offered, so "Arsenal" legitimately
        # ties against "Arsenal FC" and "Arsenal". That is one team agreeing
        # with itself, not a choice for a reviewer to make. Ambiguity means
        # two *different* rows scored equally.
        distinct_ids = {int(c["id"]) for _, _, c in best}
        if len(distinct_ids) > 1:
            proposals.append(
                Proposal(
                    external_id,
                    external_name,
                    None,
                    None,
                    Confidence.AMBIGUOUS,
                    alternatives=[
                        {"id": cid, "name": name}
                        for cid, name in sorted(
                            {(int(c["id"]), str(c["name"])) for _, _, c in best}
                        )
                    ],
                )
            )
            continue

        _, confidence, candidate = max(best, key=lambda s: len(str(s[2]["name"])))
        proposals.append(
            Proposal(
                external_id,
                external_name,
                int(candidate["id"]),
                str(candidate["name"]),
                confidence,
            )
        )

    return proposals
