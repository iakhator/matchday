"""Cross-provider club name matching.

The cases here are the ones that actually went wrong, plus the ones that
would go wrong if the matcher were made more eager to please.
"""

from app.services.name_matcher import Confidence, normalize, propose


class TestNormalize:
    def test_strips_club_suffixes(self):
        assert normalize("Arsenal FC") == normalize("Arsenal")

    def test_keeps_words_that_distinguish_clubs(self):
        """'United' and 'City' must never be treated as noise - they are
        the only thing telling the two Manchester clubs apart."""
        assert normalize("Manchester United") != normalize("Manchester City")

    def test_folds_accents(self):
        assert normalize("1. FC Köln") == normalize("1 FC Koln")

    def test_ignores_punctuation_and_case(self):
        assert normalize("Brighton & Hove Albion") == normalize("brighton hove albion")


class TestPropose:
    def _candidates(self):
        return [
            {"id": 10_000_001, "name": "Brighton & Hove Albion FC"},
            {"id": 10_000_002, "name": "Arsenal FC"},
            {"id": 10_000_003, "name": "Manchester United FC"},
            {"id": 10_000_004, "name": "Manchester City FC"},
        ]

    def test_exact_match_after_normalizing(self):
        [p] = propose([{"external_id": "1", "name": "Arsenal"}], self._candidates())
        assert p.confidence == Confidence.EXACT
        assert p.internal_id == 10_000_002

    def test_the_brighton_case(self):
        """The failure that motivated all of this: a short name against a
        full registered name. A naive normalizer returned no match."""
        [p] = propose([{"external_id": "2", "name": "Brighton"}], self._candidates())
        assert p.confidence == Confidence.STRONG
        assert p.internal_id == 10_000_001

    def test_does_not_confuse_the_manchester_clubs(self):
        [p] = propose(
            [{"external_id": "3", "name": "Man United"}], self._candidates()
        )
        assert p.internal_id != 10_000_004

    def test_reports_no_match_rather_than_guessing(self):
        [p] = propose(
            [{"external_id": "9", "name": "Sporting Lisbon"}], self._candidates()
        )
        assert p.confidence == Confidence.NONE
        assert p.internal_id is None

    def test_a_tie_is_ambiguous_not_arbitrarily_resolved(self):
        """Two equally good candidates must surface for a human. Picking one
        is how the wrong club gets mapped, silently."""
        candidates = [
            {"id": 1, "name": "Racing Club"},
            {"id": 2, "name": "Racing Club"},
        ]
        [p] = propose([{"external_id": "7", "name": "Racing"}], candidates)
        assert p.confidence == Confidence.AMBIGUOUS
        assert p.internal_id is None
        # Both are called "Racing Club" - the ids are the only thing that
        # distinguishes them, which is exactly why they must be included.
        assert [a["id"] for a in p.alternatives] == [1, 2]

    def test_every_proposal_needs_review_even_exact_ones(self):
        """Different clubs in different countries share normalized names.
        Confidence orders the reviewer's attention; it does not replace
        them."""
        proposals = propose(
            [{"external_id": "1", "name": "Arsenal"}], self._candidates()
        )
        assert all(p.needs_review for p in proposals)

    def test_handles_an_empty_candidate_set(self):
        [p] = propose([{"external_id": "1", "name": "Arsenal"}], [])
        assert p.confidence == Confidence.NONE
