"""Provider ref -> gateway id translation.

The point of the mapping is that consumers build against ids this gateway
owns, so upstreams can be swapped underneath them. These tests cover the
two claims that makes: a provider's id never becomes a gateway id, and two
providers can point at the same row.
"""

import pytest
from sqlmodel import select

from app.connectors.base import NormalizedFixture, NormalizedTeam
from app.db.models import EntityType, ExternalId, Fixture, League, Team
from app.services.id_mapper import IdMapper
from app.services.sync_service import SyncService
from app.tests.test_sync_service import (
    FakeConnector,
    make_league_normalized,
)
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio


class TestIdMapper:
    async def test_resolve_returns_none_for_unknown_ref(self, test_session):
        mapper = IdMapper(test_session)
        assert await mapper.resolve(EntityType.TEAM, "football_data_org", "57") is None

    async def test_link_then_resolve_round_trip(self, test_session):
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await test_session.commit()

        assert (
            await mapper.resolve(EntityType.TEAM, "football_data_org", "57")
            == 10_000_001
        )

    async def test_link_is_idempotent(self, test_session):
        """Syncs run repeatedly over the same fixtures - re-linking a known
        ref must not race the unique constraint or duplicate the row."""
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await test_session.commit()
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await test_session.commit()

        rows = (await test_session.exec(select(ExternalId))).all()
        assert len(rows) == 1

    async def test_link_refuses_to_repoint_an_existing_ref(self, test_session):
        """Two gateway rows claiming one upstream entity is a real conflict.
        Silently updating the mapping would hide it and quietly move every
        consumer's reference."""
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await test_session.commit()

        with pytest.raises(ValueError, match="already mapped"):
            await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_002)

    async def test_two_sources_can_map_to_one_row(self, test_session):
        """The whole point: providers disagree about which number means
        Arsenal, and a consumer should never have to care which answered."""
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await mapper.link(EntityType.TEAM, "api_sports", "42", 10_000_001)
        await test_session.commit()

        assert (
            await mapper.resolve(EntityType.TEAM, "football_data_org", "57")
            == await mapper.resolve(EntityType.TEAM, "api_sports", "42")
            == 10_000_001
        )
        assert len(await mapper.aliases(EntityType.TEAM, 10_000_001)) == 2

    async def test_same_ref_in_different_sources_is_not_confused(self, test_session):
        """football-data.org's team 1 and another provider's team 1 are
        different clubs. Only (entity_type, source, ref) identifies."""
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "1", 10_000_001)
        await mapper.link(EntityType.TEAM, "api_sports", "1", 10_000_002)
        await test_session.commit()

        assert await mapper.resolve(EntityType.TEAM, "api_sports", "1") == 10_000_002

    async def test_entity_types_do_not_collide(self, test_session):
        """Provider ids are only unique within an entity type - team 57 and
        fixture 57 are unrelated."""
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
        await mapper.link(EntityType.FIXTURE, "football_data_org", "57", 10_000_500)
        await test_session.commit()

        assert (
            await mapper.resolve(EntityType.FIXTURE, "football_data_org", "57")
            == 10_000_500
        )

    async def test_resolve_many_is_one_query_for_many_refs(self, test_session):
        mapper = IdMapper(test_session)
        for ref, internal in (("57", 10_000_001), ("61", 10_000_002)):
            await mapper.link(EntityType.TEAM, "football_data_org", ref, internal)
        await test_session.commit()

        found = await mapper.resolve_many(
            EntityType.TEAM, "football_data_org", ["57", "61", "999"]
        )
        # Unknown refs are absent rather than None-valued, so callers can
        # treat "not in the map" as the single not-synced-yet signal.
        assert found == {"57": 10_000_001, "61": 10_000_002}

    async def test_resolve_many_handles_no_refs(self, test_session):
        mapper = IdMapper(test_session)
        assert await mapper.resolve_many(EntityType.TEAM, "football_data_org", []) == {}


class TestSyncAssignsGatewayIds:
    """The behaviour change, driven through the real sync path."""

    async def _sync(self, test_session, monkeypatch):
        connector = FakeConnector(
            "football_data_org",
            league=make_league_normalized(),
            teams=[
                NormalizedTeam(external_ref="57", name="Arsenal"),
                NormalizedTeam(external_ref="61", name="Chelsea"),
            ],
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        teams = await service.sync_teams(league, 2026)
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
        return league, teams, fixtures

    async def test_provider_ref_never_becomes_the_gateway_id(
        self, test_session, monkeypatch
    ):
        """Arsenal is 57 upstream. It must not be 57 here - that number
        belongs to football-data.org and means something else elsewhere."""
        _, teams, fixtures = await self._sync(test_session, monkeypatch)

        arsenal = next(t for t in teams if t.name == "Arsenal")
        assert arsenal.id != 57
        assert fixtures[0].id != 999

    async def test_sync_records_a_mapping_for_every_entity(
        self, test_session, monkeypatch
    ):
        league, teams, fixtures = await self._sync(test_session, monkeypatch)
        mapper = IdMapper(test_session)

        assert (
            await mapper.resolve(EntityType.LEAGUE, "football_data_org", "2021")
            == league.id
        )
        arsenal = next(t for t in teams if t.name == "Arsenal")
        assert (
            await mapper.resolve(EntityType.TEAM, "football_data_org", "57")
            == arsenal.id
        )
        assert (
            await mapper.resolve(EntityType.FIXTURE, "football_data_org", "999")
            == fixtures[0].id
        )

    async def test_resync_reuses_rows_and_adds_no_duplicate_mappings(
        self, test_session, monkeypatch
    ):
        """A second sync of the same data must resolve through the mapping
        rather than inserting a parallel set of rows under fresh ids."""
        await self._sync(test_session, monkeypatch)
        first_ids = {
            "leagues": [r.id for r in (await test_session.exec(select(League))).all()],
            "teams": [r.id for r in (await test_session.exec(select(Team))).all()],
            "fixtures": [r.id for r in (await test_session.exec(select(Fixture))).all()],
        }
        mappings_before = len((await test_session.exec(select(ExternalId))).all())

        await self._sync(test_session, monkeypatch)

        assert [
            r.id for r in (await test_session.exec(select(League))).all()
        ] == first_ids["leagues"]
        assert [
            r.id for r in (await test_session.exec(select(Team))).all()
        ] == first_ids["teams"]
        assert [
            r.id for r in (await test_session.exec(select(Fixture))).all()
        ] == first_ids["fixtures"]
        assert (
            len((await test_session.exec(select(ExternalId))).all()) == mappings_before
        )
