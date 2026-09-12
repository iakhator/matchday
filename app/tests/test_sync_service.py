from datetime import timedelta

import pytest
from sqlmodel import select

from app.connectors.base import (
    Connector,
    NormalizedFixture,
    NormalizedLeague,
    NormalizedTeam,
)
from app.db.models import Fixture, League
from app.services.sync_service import SyncService
from app.utils.datetime_utils import utcnow


class FakeConnector(Connector):
    """Test double for Connector - returns canned normalized data, or
    raises, per-method, so fallback/failure paths can be exercised without
    a real upstream API."""

    def __init__(
        self,
        source: str,
        league: NormalizedLeague = None,
        teams=None,
        fixtures=None,
        raise_on: set = None,
    ):
        self.source = source
        self._league = league
        self._teams = teams or []
        self._fixtures = fixtures or []
        self._raise_on = raise_on or set()

    async def fetch_league(self, competition_code):
        if "fetch_league" in self._raise_on:
            raise RuntimeError(f"{self.source} is down")
        return self._league

    async def fetch_teams(self, competition_code, season_year):
        if "fetch_teams" in self._raise_on:
            raise RuntimeError(f"{self.source} is down")
        return self._teams

    async def fetch_fixtures(self, competition_code, season_year, matchday=None):
        if "fetch_fixtures" in self._raise_on:
            raise RuntimeError(f"{self.source} is down")
        return self._fixtures

    async def fetch_standings(self, competition_code, season_year):
        return []

    async def fetch_player_stats(self, competition_code, season_year):
        return []


def make_league_normalized(external_id=2021, name="Premier League"):
    return NormalizedLeague(
        external_id=external_id,
        external_ref="PL",
        name=name,
        country="England",
        current_season_year=2026,
    )


class TestFirstSuccessFallback:
    async def test_falls_through_to_second_connector_on_failure(
        self, test_session, monkeypatch
    ):
        primary = FakeConnector("primary", raise_on={"fetch_league"})
        fallback = FakeConnector(
            "fallback", league=make_league_normalized(name="From Fallback")
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [primary, fallback]
        )

        service = SyncService(test_session)
        league = await service.sync_league("PL")

        assert league.name == "From Fallback"
        assert league.source == "fallback"

    async def test_raises_when_every_connector_fails(self, test_session, monkeypatch):
        primary = FakeConnector("primary", raise_on={"fetch_league"})
        fallback = FakeConnector("fallback", raise_on={"fetch_league"})
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [primary, fallback]
        )

        service = SyncService(test_session)
        with pytest.raises(RuntimeError, match="All connectors failed"):
            await service.sync_league("PL")


class TestSyncLeagueUpsert:
    async def test_resyncing_updates_in_place_not_duplicates(
        self, test_session, monkeypatch
    ):
        connector = FakeConnector("primary", league=make_league_normalized())
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)

        await service.sync_league("PL")
        connector._league = make_league_normalized(name="Premier League (renamed)")
        await service.sync_league("PL")

        rows = (await test_session.exec(select(League))).all()
        assert len(rows) == 1
        assert rows[0].name == "Premier League (renamed)"


class TestSyncFixtures:
    async def _seeded_league_and_service(self, test_session, monkeypatch, teams):
        connector = FakeConnector(
            "primary", league=make_league_normalized(), teams=teams
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        await service.sync_teams(league, 2026)
        return service, connector, league

    async def test_skips_fixture_referencing_unknown_team(
        self, test_session, monkeypatch
    ):
        # Only team 57 has been synced - a fixture naming team 61 (not yet
        # synced, e.g. newly promoted) must be skipped, not written with a
        # dangling foreign key.
        home_team = NormalizedTeam(external_ref="57", name="Arsenal")
        service, connector, league = await self._seeded_league_and_service(
            test_session, monkeypatch, teams=[home_team]
        )
        connector._fixtures = [
            NormalizedFixture(
                external_ref="999",
                home_team_external_ref="57",
                away_team_external_ref="61",
                kickoff_at=utcnow(),
                status="scheduled",
            )
        ]

        fixtures = await service.sync_fixtures(league, 2026)

        assert fixtures == []
        rows = (await test_session.exec(select(Fixture))).all()
        assert rows == []

    async def test_resyncing_updates_score_without_duplicating_row(
        self, test_session, monkeypatch
    ):
        home_team = NormalizedTeam(external_ref="57", name="Arsenal")
        away_team = NormalizedTeam(external_ref="61", name="Chelsea")
        service, connector, league = await self._seeded_league_and_service(
            test_session, monkeypatch, teams=[home_team, away_team]
        )
        connector._fixtures = [
            NormalizedFixture(
                external_ref="999",
                home_team_external_ref="57",
                away_team_external_ref="61",
                kickoff_at=utcnow(),
                status="scheduled",
            )
        ]
        await service.sync_fixtures(league, 2026)

        connector._fixtures = [
            NormalizedFixture(
                external_ref="999",
                home_team_external_ref="57",
                away_team_external_ref="61",
                kickoff_at=utcnow(),
                status="finished",
                home_score=2,
                away_score=1,
            )
        ]
        await service.sync_fixtures(league, 2026)

        rows = (await test_session.exec(select(Fixture))).all()
        assert len(rows) == 1
        assert rows[0].status == "finished"
        assert rows[0].home_score == 2
        assert rows[0].away_score == 1


class TestHasLiveWindowFixtures:
    async def _service_with_league(self, test_session, monkeypatch):
        connector = FakeConnector("primary", league=make_league_normalized())
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        return service, league

    async def test_true_for_scheduled_fixture_inside_live_window(
        self, test_session, monkeypatch
    ):
        service, league = await self._service_with_league(test_session, monkeypatch)
        test_session.add(
            Fixture(
                id=1,
                league_id=league.id,
                season_year=2026,
                source="primary",
                home_team_id=57,
                away_team_id=61,
                kickoff_at=utcnow() - timedelta(hours=1),
                status="scheduled",
            )
        )
        await test_session.commit()

        assert await service.has_live_window_fixtures("PL") is True

    async def test_false_when_kickoff_is_outside_the_window(
        self, test_session, monkeypatch
    ):
        service, league = await self._service_with_league(test_session, monkeypatch)
        test_session.add(
            Fixture(
                id=1,
                league_id=league.id,
                season_year=2026,
                source="primary",
                home_team_id=57,
                away_team_id=61,
                kickoff_at=utcnow() - timedelta(hours=10),
                status="scheduled",
            )
        )
        await test_session.commit()

        assert await service.has_live_window_fixtures("PL") is False

    async def test_false_when_only_fixture_is_already_finished(
        self, test_session, monkeypatch
    ):
        service, league = await self._service_with_league(test_session, monkeypatch)
        test_session.add(
            Fixture(
                id=1,
                league_id=league.id,
                season_year=2026,
                source="primary",
                home_team_id=57,
                away_team_id=61,
                kickoff_at=utcnow() - timedelta(hours=1),
                status="finished",
                home_score=1,
                away_score=0,
            )
        )
        await test_session.commit()

        assert await service.has_live_window_fixtures("PL") is False

    async def test_false_for_unknown_competition(self, test_session, monkeypatch):
        service, _league = await self._service_with_league(test_session, monkeypatch)
        assert await service.has_live_window_fixtures("XX") is False
