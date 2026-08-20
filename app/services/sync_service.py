from datetime import timedelta
from typing import List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.base import Connector
from app.connectors.registry import get_connectors
from app.core.config import settings
from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.db.models import Fixture, League, PlayerStat, Standing, Team
from app.utils.datetime_utils import utcnow


class SyncService:
    """Orchestrates connectors -> normalize -> upsert into the gateway DB.

    Every fetch tries connectors in registry order and falls through to the
    next one on failure, so a single upstream outage doesn't take the whole
    gateway down.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _first_success(self, label: str, attempts: list):
        last_error: Optional[Exception] = None
        for connector, call in attempts:
            try:
                return connector, await call
            except Exception as e:  # noqa: BLE001 - deliberately broad, we fall through
                logger.warning(
                    f"Connector '{connector.source}' failed for {label}: {e}"
                )
                last_error = e
        raise RuntimeError(f"All connectors failed for {label}") from last_error

    async def sync_league(self, competition_code: str) -> League:
        connectors: List[Connector] = get_connectors()
        connector, normalized = await self._first_success(
            f"league {competition_code}",
            [(c, c.fetch_league(competition_code)) for c in connectors],
        )

        existing = (
            await self.session.exec(
                select(League).where(
                    League.source == connector.source,
                    League.external_ref == normalized.external_ref,
                )
            )
        ).first()

        if existing:
            existing.name = normalized.name
            existing.country = normalized.country
            existing.logo = normalized.logo
            existing.current_season_year = normalized.current_season_year
            existing.updated_at = utcnow()
            league = existing
        else:
            league = League(
                source=connector.source,
                external_ref=normalized.external_ref,
                name=normalized.name,
                country=normalized.country,
                logo=normalized.logo,
                current_season_year=normalized.current_season_year,
            )
            self.session.add(league)

        await self.session.commit()
        await self.session.refresh(league)
        logger.info(
            f"Synced league {league.name} ({league.source}:{league.external_ref})"
        )
        return league

    async def sync_teams(self, league: League, season_year: int) -> List[Team]:
        connectors: List[Connector] = get_connectors()
        connector, normalized_teams = await self._first_success(
            f"teams for league {league.id} season {season_year}",
            [
                (c, c.fetch_teams(league.external_ref, season_year))
                for c in connectors
                if c.source == league.source
            ]
            or [(c, c.fetch_teams(league.external_ref, season_year)) for c in connectors],
        )

        existing_rows = (
            await self.session.exec(
                select(Team).where(
                    Team.league_id == league.id, Team.season_year == season_year
                )
            )
        ).all()
        existing_by_ref = {t.external_ref: t for t in existing_rows}

        teams = []
        for normalized in normalized_teams:
            existing = existing_by_ref.get(normalized.external_ref)
            if existing:
                existing.name = normalized.name
                existing.short_name = normalized.short_name
                existing.code = normalized.code
                existing.logo = normalized.logo
                existing.venue = normalized.venue
                existing.updated_at = utcnow()
                team = existing
            else:
                team = Team(
                    league_id=league.id,
                    season_year=season_year,
                    source=connector.source,
                    external_ref=normalized.external_ref,
                    name=normalized.name,
                    short_name=normalized.short_name,
                    code=normalized.code,
                    logo=normalized.logo,
                    venue=normalized.venue,
                )
                self.session.add(team)
            teams.append(team)

        await self.session.commit()
        for team in teams:
            await self.session.refresh(team)

        logger.info(f"Synced {len(teams)} teams for league {league.name}")
        return teams

    async def sync_fixtures(
        self,
        league: League,
        season_year: int,
        matchday: Optional[int] = None,
    ) -> List[Fixture]:
        connectors: List[Connector] = get_connectors()
        connector, normalized_fixtures = await self._first_success(
            f"fixtures for league {league.id} season {season_year}",
            [
                (c, c.fetch_fixtures(league.external_ref, season_year, matchday))
                for c in connectors
                if c.source == league.source
            ]
            or [
                (c, c.fetch_fixtures(league.external_ref, season_year, matchday))
                for c in connectors
            ],
        )

        team_rows = (
            await self.session.exec(
                select(Team).where(
                    Team.league_id == league.id, Team.season_year == season_year
                )
            )
        ).all()
        team_id_by_ref = {t.external_ref: t.id for t in team_rows}

        existing_rows = (
            await self.session.exec(
                select(Fixture).where(
                    Fixture.league_id == league.id, Fixture.season_year == season_year
                )
            )
        ).all()
        existing_by_ref = {f.external_ref: f for f in existing_rows}

        fixtures = []
        skipped = 0
        for normalized in normalized_fixtures:
            home_team_id = team_id_by_ref.get(normalized.home_team_external_ref)
            away_team_id = team_id_by_ref.get(normalized.away_team_external_ref)
            if not home_team_id or not away_team_id:
                # Team hasn't been synced yet (e.g. promoted/relegated club
                # not yet in this season's roster) - skip until sync_teams
                # catches up rather than writing a broken fixture row.
                skipped += 1
                continue

            existing = existing_by_ref.get(normalized.external_ref)
            if existing:
                existing.matchday = normalized.matchday
                existing.status = normalized.status
                existing.raw_status = normalized.raw_status
                existing.home_score = normalized.home_score
                existing.away_score = normalized.away_score
                existing.kickoff_at = normalized.kickoff_at
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                fixture = existing
            else:
                fixture = Fixture(
                    league_id=league.id,
                    season_year=season_year,
                    matchday=normalized.matchday,
                    source=connector.source,
                    external_ref=normalized.external_ref,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    kickoff_at=normalized.kickoff_at,
                    status=normalized.status,
                    raw_status=normalized.raw_status,
                    home_score=normalized.home_score,
                    away_score=normalized.away_score,
                )
                self.session.add(fixture)
            fixtures.append(fixture)

        await self.session.commit()
        for fixture in fixtures:
            await self.session.refresh(fixture)

        if skipped:
            logger.warning(
                f"Skipped {skipped} fixtures for league {league.name} - "
                "unknown team ref, run sync_teams first"
            )
        logger.info(f"Synced {len(fixtures)} fixtures for league {league.name}")
        return fixtures

    async def sync_standings(self, league: League, season_year: int) -> List[Standing]:
        connectors: List[Connector] = get_connectors()
        connector, normalized_standings = await self._first_success(
            f"standings for league {league.id} season {season_year}",
            [
                (c, c.fetch_standings(league.external_ref, season_year))
                for c in connectors
                if c.source == league.source
            ]
            or [
                (c, c.fetch_standings(league.external_ref, season_year))
                for c in connectors
            ],
        )

        team_rows = (
            await self.session.exec(
                select(Team).where(
                    Team.league_id == league.id, Team.season_year == season_year
                )
            )
        ).all()
        team_id_by_ref = {t.external_ref: t.id for t in team_rows}

        existing_rows = (
            await self.session.exec(
                select(Standing).where(
                    Standing.league_id == league.id, Standing.season_year == season_year
                )
            )
        ).all()
        existing_by_team_id = {s.team_id: s for s in existing_rows}

        standings = []
        skipped = 0
        for normalized in normalized_standings:
            team_id = team_id_by_ref.get(normalized.team_external_ref)
            if not team_id:
                # Same reasoning as sync_fixtures - a team not yet in this
                # season's roster (sync_teams hasn't caught up). Skip rather
                # than write a standing row with no valid team.
                skipped += 1
                continue

            existing = existing_by_team_id.get(team_id)
            if existing:
                existing.rank = normalized.rank
                existing.points = normalized.points
                existing.played = normalized.played
                existing.won = normalized.won
                existing.drawn = normalized.drawn
                existing.lost = normalized.lost
                existing.goals_for = normalized.goals_for
                existing.goals_against = normalized.goals_against
                existing.form = normalized.form
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                standing = existing
            else:
                standing = Standing(
                    league_id=league.id,
                    team_id=team_id,
                    season_year=season_year,
                    rank=normalized.rank,
                    points=normalized.points,
                    played=normalized.played,
                    won=normalized.won,
                    drawn=normalized.drawn,
                    lost=normalized.lost,
                    goals_for=normalized.goals_for,
                    goals_against=normalized.goals_against,
                    form=normalized.form,
                )
                self.session.add(standing)
            standings.append(standing)

        await self.session.commit()
        for standing in standings:
            await self.session.refresh(standing)

        if skipped:
            logger.warning(
                f"Skipped {skipped} standings rows for league {league.name} - "
                "unknown team ref, run sync_teams first"
            )
        logger.info(f"Synced {len(standings)} standings for league {league.name}")
        return standings

    async def sync_player_stats(
        self, league: League, season_year: int
    ) -> List[PlayerStat]:
        connectors: List[Connector] = get_connectors()
        connector, normalized_stats = await self._first_success(
            f"player stats for league {league.id} season {season_year}",
            [
                (c, c.fetch_player_stats(league.external_ref, season_year))
                for c in connectors
                if c.source == league.source
            ]
            or [
                (c, c.fetch_player_stats(league.external_ref, season_year))
                for c in connectors
            ],
        )

        team_rows = (
            await self.session.exec(
                select(Team).where(
                    Team.league_id == league.id, Team.season_year == season_year
                )
            )
        ).all()
        team_id_by_ref = {t.external_ref: t.id for t in team_rows}
        team_ids = list(team_id_by_ref.values())

        existing_rows = (
            (
                await self.session.exec(
                    select(PlayerStat).where(
                        PlayerStat.team_id.in_(team_ids),
                        PlayerStat.season_year == season_year,
                        PlayerStat.source == connector.source,
                    )
                )
            ).all()
            if team_ids
            else []
        )
        existing_by_key = {(s.team_id, s.external_ref): s for s in existing_rows}

        stats = []
        skipped = 0
        for normalized in normalized_stats:
            team_id = team_id_by_ref.get(normalized.team_external_ref)
            if not team_id:
                skipped += 1
                continue

            existing = existing_by_key.get((team_id, normalized.external_ref))
            if existing:
                existing.name = normalized.name
                existing.photo = normalized.photo
                existing.position = normalized.position
                existing.goals = normalized.goals
                existing.assists = normalized.assists
                existing.appearances = normalized.appearances
                existing.last_synced_at = utcnow()
                existing.updated_at = utcnow()
                stat = existing
            else:
                stat = PlayerStat(
                    team_id=team_id,
                    season_year=season_year,
                    source=connector.source,
                    external_ref=normalized.external_ref,
                    name=normalized.name,
                    photo=normalized.photo,
                    position=normalized.position,
                    goals=normalized.goals,
                    assists=normalized.assists,
                    appearances=normalized.appearances,
                )
                self.session.add(stat)
            stats.append(stat)

        await self.session.commit()
        for stat in stats:
            await self.session.refresh(stat)

        if skipped:
            logger.warning(
                f"Skipped {skipped} player stat rows for league {league.name} - "
                "unknown team ref, run sync_teams first"
            )
        logger.info(f"Synced {len(stats)} player stats for league {league.name}")
        return stats

    async def has_live_window_fixtures(self, competition_code: str) -> bool:
        """Cheap DB-only check (no upstream call) for whether
        `competition_code` has a fixture currently in or near its live
        window. Lets the fast-cadence job skip the upstream API entirely
        when nothing's on, instead of polling blindly every tick."""
        leagues = (
            await self.session.exec(
                select(League).where(League.external_ref == competition_code)
            )
        ).all()
        if not leagues:
            return False

        now = utcnow()
        window_start = now - timedelta(hours=SchedulerConfig.LIVE_WINDOW_HOURS)
        league_ids = [league.id for league in leagues]

        result = await self.session.exec(
            select(Fixture).where(
                Fixture.league_id.in_(league_ids),
                Fixture.kickoff_at >= window_start,
                Fixture.kickoff_at <= now,
                Fixture.status.in_(["scheduled", "live"]),
            )
        )
        return result.first() is not None

    async def backfill_finished_results(self, league: League, season_year: int) -> dict:
        """Manually-triggered emergency path: fills in FINISHED results
        (status + score) for fixtures this gateway already knows about but
        never got a final score - e.g. because football-data.org was down
        while they were played. Uses the Sofascore fallback connector; see
        `SoccerDataSofascoreConnector`'s docstring for why this isn't part
        of the automatic sync chain.

        Deliberately narrow: only UPDATES existing fixture rows, matched by
        kickoff date + team names (Sofascore doesn't share football-data
        .org's team/fixture IDs) - never creates new fixtures or teams.
        That avoids ending up with duplicate team rows from two unrelated
        ID namespaces for the same real-world team.
        """
        if not settings.ENABLE_SOCCERDATA_FALLBACK:
            raise RuntimeError(
                "Soccerdata fallback is disabled - set "
                "ENABLE_SOCCERDATA_FALLBACK=true and install the "
                "'soccerdata' optional dependency group to use it"
            )

        from app.connectors.soccerdata_sofascore import (
            SoccerDataSofascoreConnector,
            _team_ref,
        )

        connector = SoccerDataSofascoreConnector()
        fallback_fixtures = await connector.fetch_fixtures(
            league.external_ref, season_year
        )

        team_rows = (
            await self.session.exec(
                select(Team).where(
                    Team.league_id == league.id, Team.season_year == season_year
                )
            )
        ).all()
        team_id_by_ref = {}
        for team in team_rows:
            team_id_by_ref.setdefault(_team_ref(team.name), team.id)
            if team.short_name:
                team_id_by_ref.setdefault(_team_ref(team.short_name), team.id)

        unfinished_fixtures = (
            await self.session.exec(
                select(Fixture).where(
                    Fixture.league_id == league.id,
                    Fixture.season_year == season_year,
                    Fixture.status != "finished",
                )
            )
        ).all()
        fixture_by_key = {
            (f.kickoff_at.date(), f.home_team_id, f.away_team_id): f
            for f in unfinished_fixtures
        }

        updated = 0
        unmatched = 0
        for fallback in fallback_fixtures:
            home_id = team_id_by_ref.get(fallback.home_team_external_ref)
            away_id = team_id_by_ref.get(fallback.away_team_external_ref)
            fixture = (
                fixture_by_key.get((fallback.kickoff_at.date(), home_id, away_id))
                if home_id and away_id
                else None
            )
            if not fixture:
                unmatched += 1
                continue

            fixture.status = "finished"
            fixture.raw_status = f"backfilled:{fallback.raw_status}"
            fixture.home_score = fallback.home_score
            fixture.away_score = fallback.away_score
            fixture.last_synced_at = utcnow()
            fixture.updated_at = utcnow()
            self.session.add(fixture)
            updated += 1

        await self.session.commit()
        logger.info(
            f"Backfilled {updated} finished results for league {league.name} "
            f"season {season_year} ({unmatched} unmatched)"
        )
        return {"updated": updated, "unmatched": unmatched}
