from app.connectors.football_data_org import FootballDataOrgConnector
from app.core.config import settings


def make_connector(monkeypatch) -> FootballDataOrgConnector:
    monkeypatch.setattr(settings, "FOOTBALL_DATA_ORG_API_KEY", "dummy-key-for-tests")
    return FootballDataOrgConnector()


def stub_get(connector, monkeypatch, payload: dict) -> None:
    """Replace the connector's HTTP call with a canned response, so these
    tests exercise only the normalization logic - never a real request."""

    async def fake_get(path, params=None):
        return payload

    monkeypatch.setattr(connector, "_get", fake_get)


class TestFetchLeague:
    async def test_derives_season_year_from_current_season_start_date(
        self, monkeypatch
    ):
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "id": 2021,
                "code": "PL",
                "name": "Premier League",
                "area": {"name": "England"},
                "emblem": "https://crests.football-data.org/PL.png",
                "currentSeason": {"startDate": "2026-08-15"},
            },
        )
        league = await connector.fetch_league("PL")
        assert league.external_id == 2021
        assert league.current_season_year == 2026

    async def test_missing_current_season_leaves_year_none(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "id": 2021,
                "code": "PL",
                "name": "Premier League",
                "area": None,
                "emblem": None,
            },
        )
        league = await connector.fetch_league("PL")
        assert league.current_season_year is None
        assert league.country is None


def _match(**overrides):
    base = {
        "id": 12345,
        "matchday": 3,
        "status": "SCHEDULED",
        "utcDate": "2026-09-05T14:00:00Z",
        "homeTeam": {"id": 57},
        "awayTeam": {"id": 61},
        "score": {"fullTime": {"home": None, "away": None}},
    }
    base.update(overrides)
    return base


class TestFetchFixtures:
    async def test_known_status_maps_to_normalized_value(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(
            connector, monkeypatch, {"matches": [_match(status="IN_PLAY")]}
        )
        fixtures = await connector.fetch_fixtures("PL", 2026)
        assert fixtures[0].status == "live"
        assert fixtures[0].raw_status == "IN_PLAY"

    async def test_unrecognized_status_defaults_to_scheduled(self, monkeypatch):
        # football-data.org could introduce a new status string without
        # warning - this must never crash the sync, and it must never
        # silently classify a match as "finished" when we don't actually
        # know that.
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {"matches": [_match(status="SOME_NEW_STATUS_WE_DONT_KNOW")]},
        )
        fixtures = await connector.fetch_fixtures("PL", 2026)
        assert fixtures[0].status == "scheduled"
        assert fixtures[0].raw_status == "SOME_NEW_STATUS_WE_DONT_KNOW"

    async def test_missing_score_stays_none(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(connector, monkeypatch, {"matches": [_match()]})
        fixtures = await connector.fetch_fixtures("PL", 2026)
        assert fixtures[0].home_score is None
        assert fixtures[0].away_score is None

    async def test_finished_score_is_captured(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "matches": [
                    _match(
                        status="FINISHED",
                        score={"fullTime": {"home": 3, "away": 1}},
                    )
                ]
            },
        )
        fixtures = await connector.fetch_fixtures("PL", 2026)
        assert fixtures[0].status == "finished"
        assert fixtures[0].home_score == 3
        assert fixtures[0].away_score == 1


def _standing_row(team_id, position):
    return {
        "team": {"id": team_id},
        "position": position,
        "points": 10,
        "playedGames": 5,
        "won": 3,
        "draw": 1,
        "lost": 1,
        "goalsFor": 8,
        "goalsAgainst": 4,
        "form": "WWDLW",
    }


class TestFetchStandings:
    async def test_only_total_table_is_returned(self, monkeypatch):
        # football-data.org returns TOTAL plus HOME/AWAY breakdowns in the
        # same list for some competitions - mixing those into the result
        # would double- or triple-count every team.
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "standings": [
                    {
                        "type": "TOTAL",
                        "table": [_standing_row(57, 1), _standing_row(61, 2)],
                    },
                    {"type": "HOME", "table": [_standing_row(57, 1)]},
                    {"type": "AWAY", "table": [_standing_row(57, 3)]},
                ]
            },
        )
        standings = await connector.fetch_standings("PL", 2026)
        assert len(standings) == 2
        assert {s.team_external_ref for s in standings} == {"57", "61"}

    async def test_no_total_table_returns_empty(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(connector, monkeypatch, {"standings": []})
        standings = await connector.fetch_standings("PL", 2026)
        assert standings == []


class TestFetchPlayerStats:
    async def test_position_falls_back_to_section(self, monkeypatch):
        # football-data.org's scorers endpoint uses "section" instead of
        # "position" for some competitions/tiers - losing this fallback
        # would leave every affected player's position blank.
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "scorers": [
                    {
                        "player": {"id": 44, "name": "R. Nelson", "section": "Forward"},
                        "team": {"id": 57},
                        "goals": 5,
                        "assists": 2,
                        "playedMatches": 10,
                    }
                ]
            },
        )
        stats = await connector.fetch_player_stats("PL", 2026)
        assert stats[0].position == "Forward"

    async def test_missing_counters_default_to_zero(self, monkeypatch):
        connector = make_connector(monkeypatch)
        stub_get(
            connector,
            monkeypatch,
            {
                "scorers": [
                    {
                        "player": {"id": 44, "name": "R. Nelson"},
                        "team": {"id": 57},
                    }
                ]
            },
        )
        stats = await connector.fetch_player_stats("PL", 2026)
        assert stats[0].goals == 0
        assert stats[0].assists == 0
        assert stats[0].appearances == 0
