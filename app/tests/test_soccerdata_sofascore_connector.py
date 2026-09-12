from app.connectors.soccerdata_sofascore import _team_ref


class TestTeamRef:
    """`_team_ref` is the whole matching mechanism `backfill_finished_
    results` relies on to line up Sofascore's name-only data against
    existing Team rows (see SyncService.backfill_finished_results) - a
    subtle slugging bug here fails silently as "unmatched", not a crash,
    so it's worth pinning down exactly.
    """

    def test_basic_lowercasing_and_spacing(self):
        assert _team_ref("Manchester United") == "name:manchester-united"

    def test_apostrophe_becomes_dash(self):
        assert _team_ref("Nott'm Forest") == "name:nott-m-forest"

    def test_collapses_multiple_separators_into_one_dash(self):
        # A run of non-alphanumeric characters (double space, "  CF ")
        # must collapse to a single dash, not one per character - two
        # different sources spacing a name slightly differently should
        # still resolve to the same ref.
        assert _team_ref("Real   Madrid CF") == "name:real-madrid-cf"

    def test_strips_leading_and_trailing_separators(self):
        assert _team_ref("  Arsenal  ") == "name:arsenal"

    def test_case_insensitive(self):
        assert _team_ref("ARSENAL") == _team_ref("arsenal") == "name:arsenal"

    def test_period_becomes_dash(self):
        assert _team_ref("Sheffield Utd.") == "name:sheffield-utd"
