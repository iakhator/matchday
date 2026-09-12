"""Propose -> review -> approve, and the guarantee that holds it together:
an unreviewed mapping never reaches data consumers depend on.
"""

import pytest
from sqlmodel import select

from app.connectors.base import NormalizedFixture, NormalizedTeam
from app.db.models import EntityType, ExternalId, Fixture, Team
from app.services.external_id_seeder import ExternalIdSeeder, to_review_document
from app.services.id_mapper import IdMapper
from app.services.name_matcher import Confidence, propose
from app.services.sync_service import SyncService
from app.tests.test_sync_service import FakeConnector, make_league_normalized
from app.utils.datetime_utils import utcnow


async def _seed_teams(session, names):
    teams = [Team(source="football_data_org", league_id=1, season_year=2026, name=n)
             for n in names]
    for team in teams:
        session.add(team)
    await session.commit()
    for team in teams:
        await session.refresh(team)
    return teams


@pytest.mark.asyncio
class TestPropose:
    async def test_writes_confident_matches_as_unverified(self, test_session):
        await _seed_teams(test_session, ["Brighton & Hove Albion FC", "Arsenal FC"])
        seeder = ExternalIdSeeder(test_session)

        await seeder.propose_team_mappings(
            "api_sports",
            [{"external_id": "42", "name": "Brighton"},
             {"external_id": "43", "name": "Arsenal"}],
        )

        rows = (await test_session.exec(select(ExternalId))).all()
        assert len(rows) == 2
        assert all(row.verified is False for row in rows)

    async def test_does_not_persist_a_guess_it_is_unsure_about(self, test_session):
        """An absent mapping is honest about not knowing. A weak guess sitting
        in the table looks like knowledge."""
        await _seed_teams(test_session, ["Arsenal FC"])
        seeder = ExternalIdSeeder(test_session)

        await seeder.propose_team_mappings(
            "api_sports", [{"external_id": "99", "name": "Sporting Lisbon"}]
        )

        assert (await test_session.exec(select(ExternalId))).all() == []

    async def test_never_repoints_an_existing_mapping(self, test_session):
        """A disagreement between a proposal and a recorded mapping is for a
        reviewer to see, not for the matcher to overwrite."""
        teams = await _seed_teams(test_session, ["Arsenal FC", "Aston Villa FC"])
        mapper = IdMapper(test_session)
        await mapper.link(EntityType.TEAM, "api_sports", "42", teams[1].id)
        await test_session.commit()

        seeder = ExternalIdSeeder(test_session)
        await seeder.propose_team_mappings(
            "api_sports", [{"external_id": "42", "name": "Arsenal"}]
        )

        assert (
            await mapper.resolve(EntityType.TEAM, "api_sports", "42") == teams[1].id
        )

    async def test_matches_against_short_name_too(self, test_session):
        team = Team(
            source="football_data_org", league_id=1, season_year=2026,
            name="Tottenham Hotspur FC", short_name="Spurs",
        )
        test_session.add(team)
        await test_session.commit()
        await test_session.refresh(team)

        seeder = ExternalIdSeeder(test_session)
        await seeder.propose_team_mappings(
            "api_sports", [{"external_id": "50", "name": "Spurs"}]
        )

        assert (
            await IdMapper(test_session).resolve(EntityType.TEAM, "api_sports", "50")
            == team.id
        )


@pytest.mark.asyncio
class TestApprove:
    async def test_approve_marks_reviewed_rows_verified(self, test_session):
        await _seed_teams(test_session, ["Arsenal FC"])
        seeder = ExternalIdSeeder(test_session)
        await seeder.propose_team_mappings(
            "api_sports", [{"external_id": "43", "name": "Arsenal"}]
        )

        assert await seeder.approve("api_sports", ["43"]) == 1
        row = (await test_session.exec(select(ExternalId))).first()
        assert row.verified is True

    async def test_approve_only_touches_the_ids_given(self, test_session):
        await _seed_teams(test_session, ["Arsenal FC", "Chelsea FC"])
        seeder = ExternalIdSeeder(test_session)
        await seeder.propose_team_mappings(
            "api_sports",
            [{"external_id": "43", "name": "Arsenal"},
             {"external_id": "44", "name": "Chelsea"}],
        )

        await seeder.approve("api_sports", ["43"])

        pending = await seeder.pending("api_sports")
        assert [row.external_id for row in pending] == ["44"]


@pytest.mark.asyncio
class TestUnverifiedMappingsAreInvisibleToSync:
    """The guarantee the whole flow rests on."""

    async def test_sync_skips_a_fixture_whose_team_mapping_is_unreviewed(
        self, test_session, monkeypatch
    ):
        connector = FakeConnector(
            "football_data_org",
            league=make_league_normalized(),
            teams=[NormalizedTeam(external_ref="57", name="Arsenal")],
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        await service.sync_teams(league, 2026)

        # A second club known only through an unreviewed, guessed mapping.
        chelsea = Team(
            source="football_data_org", league_id=league.id,
            season_year=2026, name="Chelsea FC",
        )
        test_session.add(chelsea)
        await test_session.commit()
        await test_session.refresh(chelsea)
        await IdMapper(test_session).link(
            EntityType.TEAM, "football_data_org", "61", chelsea.id, verified=False
        )
        await test_session.commit()

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

        # Skipped, not written against a guess.
        assert fixtures == []
        assert (await test_session.exec(select(Fixture))).all() == []

    async def test_the_same_fixture_syncs_once_the_mapping_is_approved(
        self, test_session, monkeypatch
    ):
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
        await service.sync_teams(league, 2026)

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
        assert len(fixtures) == 1


class TestReviewDocument:
    def test_groups_rows_by_what_the_reviewer_must_do(self):
        candidates = [{"id": 1, "name": "Arsenal FC"}, {"id": 2, "name": "Chelsea FC"}]
        proposals = propose(
            [
                {"external_id": "1", "name": "Arsenal"},
                {"external_id": "2", "name": "Sporting Lisbon"},
            ],
            candidates,
        )
        document = to_review_document("api_sports", proposals)

        assert document["summary"]["confirm"] == 1
        assert document["summary"]["needs_manual_match"] == 1
        assert all(not row["approved"] for row in document["confirm"])

    def test_ambiguous_rows_carry_their_alternatives(self):
        candidates = [{"id": 1, "name": "Racing Club"}, {"id": 2, "name": "Racing Club"}]
        proposals = propose([{"external_id": "7", "name": "Racing"}], candidates)
        document = to_review_document("api_sports", proposals)

        assert document["summary"]["needs_choice"] == 1
        alternatives = document["needs_choice"][0]["alternatives"]
        assert [a["id"] for a in alternatives] == [1, 2]

    def test_output_is_stable_for_the_same_input(self):
        """A re-run should diff cleanly against the last review file."""
        candidates = [{"id": 1, "name": "Arsenal FC"}, {"id": 2, "name": "Chelsea FC"}]
        entries = [
            {"external_id": "2", "name": "Chelsea"},
            {"external_id": "1", "name": "Arsenal"},
        ]
        first = to_review_document("api_sports", propose(entries, candidates))
        second = to_review_document("api_sports", propose(entries, candidates))
        assert first == second
        assert [r["external_name"] for r in first["confirm"]] == ["Arsenal", "Chelsea"]

    def test_confidence_is_carried_through_for_the_reviewer(self):
        candidates = [{"id": 1, "name": "Brighton & Hove Albion FC"}]
        proposals = propose([{"external_id": "2", "name": "Brighton"}], candidates)
        document = to_review_document("api_sports", proposals)
        assert document["confirm"][0]["confidence"] == Confidence.STRONG
