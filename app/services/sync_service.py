from datetime import timedelta
from typing import List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.base import Connector
from app.connectors.registry import get_connectors
from app.core.config import settings
from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.db.models import (
    Fixture,
    League,
    PlayerMatchStat,
    PlayerStat,
    ShotEvent,
    Standing,
    Team,
    TeamMatchStat,
)
from app.utils.datetime_utils import utcnow


class SyncService:
    """Orchestrates connectors -> normalize -> upsert into the gateway DB.

    Every fetch tries connectors in registry order and falls through to the
    next one on failure, so a single upstream outage doesn't take the whole
    gateway down.

    League/Team/Fixture ids are the provider's own stable numeric ids
    (confirmed these never change across seasons - see each model's
    docstring), so upserts here resolve rows by that id directly instead of
    a league+season-scoped lookup. Standing/PlayerStat keep synthetic UUID
    ids since a "this team's standing this season" row has no natural id of
    its own from the provider.
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

        existing = await self.session.get(League, normalized.external_id)

        if existing:
            existing.source = connector.source
            existing.external_ref = normalized.external_ref
            existing.name = normalized.name
            existing.country = normalized.country
            existing.logo = normalized.logo
            existing.current_season_year = normalized.current_season_year
            existing.updated_at = utcnow()
            league = existing
        else:
            league = League(
                id=normalized.external_id,
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

        candidate_ids = [int(t.external_ref) for t in normalized_teams]
        existing_rows = (
            (
                await self.session.exec(
                    select(Team).where(Team.id.in_(candidate_ids))
                )
            ).all()
            if candidate_ids
            else []
        )
        existing_by_id = {t.id: t for t in existing_rows}

        teams = []
        for normalized in normalized_teams:
            team_id = int(normalized.external_ref)
            existing = existing_by_id.get(team_id)
            if existing:
                existing.name = normalized.name
                existing.short_name = normalized.short_name
                existing.code = normalized.code
                existing.logo = normalized.logo
                existing.venue = normalized.venue
                # A club can move between leagues (promotion/relegation) -
                # this keeps "current league/season" accurate without
                # duplicating the team row. See Team's docstring.
                existing.league_id = league.id
                existing.season_year = season_year
                existing.updated_at = utcnow()
                team = existing
            else:
                team = Team(
                    id=team_id,
                    source=connector.source,
                    league_id=league.id,
                    season_year=season_year,
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

    async def _existing_team_ids(self, candidate_ids: List[int]) -> set:
        if not candidate_ids:
            return set()
        rows = (
            await self.session.exec(
                select(Team.id).where(Team.id.in_(candidate_ids))
            )
        ).all()
        return set(rows)

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

        team_candidates = {
            int(f.home_team_external_ref) for f in normalized_fixtures
        } | {int(f.away_team_external_ref) for f in normalized_fixtures}
        valid_team_ids = await self._existing_team_ids(list(team_candidates))

        fixture_ids = [int(f.external_ref) for f in normalized_fixtures]
        existing_rows = (
            (
                await self.session.exec(
                    select(Fixture).where(Fixture.id.in_(fixture_ids))
                )
            ).all()
            if fixture_ids
            else []
        )
        existing_by_id = {f.id: f for f in existing_rows}

        fixtures = []
        newly_finished = []
        skipped = 0
        for normalized in normalized_fixtures:
            home_team_id = int(normalized.home_team_external_ref)
            away_team_id = int(normalized.away_team_external_ref)
            if home_team_id not in valid_team_ids or away_team_id not in valid_team_ids:
                # Team hasn't been synced yet (e.g. promoted/relegated club
                # not yet in this season's roster) - skip until sync_teams
                # catches up rather than writing a broken fixture row.
                skipped += 1
                continue

            fixture_id = int(normalized.external_ref)
            existing = existing_by_id.get(fixture_id)
            if existing:
                just_finished = (
                    existing.status != "finished" and normalized.status == "finished"
                )
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
                just_finished = normalized.status == "finished"
                fixture = Fixture(
                    id=fixture_id,
                    league_id=league.id,
                    season_year=season_year,
                    matchday=normalized.matchday,
                    source=connector.source,
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
            if just_finished:
                newly_finished.append(fixture)

        await self.session.commit()
        for fixture in fixtures:
            await self.session.refresh(fixture)

        if skipped:
            logger.warning(
                f"Skipped {skipped} fixtures for league {league.name} - "
                "unknown team ref, run sync_teams first"
            )
        logger.info(f"Synced {len(fixtures)} fixtures for league {league.name}")

        # Reactive, not scheduled - enrich a fixture with Understat's
        # advanced stats right when it actually finishes, same trigger
        # pattern as standings/player-stats sync elsewhere in this
        # codebase. No-ops immediately if ENABLE_SOCCERDATA is off.
        if settings.ENABLE_SOCCERDATA:
            for fixture in newly_finished:
                try:
                    await self.sync_fixture_stats(fixture)
                except Exception as e:  # noqa: BLE001 - one bad enrichment shouldn't break the sync
                    logger.warning(
                        f"Understat enrichment failed for fixture {fixture.id}: {e}"
                    )

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

        valid_team_ids = await self._existing_team_ids(
            [int(s.team_external_ref) for s in normalized_standings]
        )

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
            team_id = int(normalized.team_external_ref)
            if team_id not in valid_team_ids:
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

        valid_team_ids = await self._existing_team_ids(
            [int(s.team_external_ref) for s in normalized_stats]
        )

        existing_rows = (
            (
                await self.session.exec(
                    select(PlayerStat).where(
                        PlayerStat.team_id.in_(valid_team_ids),
                        PlayerStat.season_year == season_year,
                        PlayerStat.source == connector.source,
                    )
                )
            ).all()
            if valid_team_ids
            else []
        )
        existing_by_key = {(s.team_id, s.external_ref): s for s in existing_rows}

        stats = []
        skipped = 0
        for normalized in normalized_stats:
            team_id = int(normalized.team_external_ref)
            if team_id not in valid_team_ids:
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
        if not settings.ENABLE_SOCCERDATA:
            raise RuntimeError(
                "Soccerdata fallback is disabled - set "
                "ENABLE_SOCCERDATA=true and install the "
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

        # Not season-filtered - Team rows track their *current* league/
        # season only, and a backfill can target a season that's since
        # moved on. league_id alone is a good enough proxy for "teams
        # relevant to this competition" here.
        team_rows = (
            await self.session.exec(
                select(Team).where(Team.league_id == league.id)
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

    async def sync_fixture_stats(self, fixture: Fixture) -> bool:
        """Post-match enrichment for one already-finished fixture: advanced
        stats (xG, xA, PPDA, shot map) from Understat - data api-sports.io
        doesn't offer at any tier. Call this once a fixture's status flips
        to finished, not on a recurring schedule; see
        `UnderstatConnector`'s docstring for why this needs
        ENABLE_SOCCERDATA=true and what that tradeoff is.

        Returns False (no-op) if the flag is off, the competition isn't
        covered, or Understat has no data for this fixture yet.
        """
        if not settings.ENABLE_SOCCERDATA:
            return False

        from app.connectors.understat import UnderstatConnector

        league = await self.session.get(League, fixture.league_id)
        home_team = await self.session.get(Team, fixture.home_team_id)
        away_team = await self.session.get(Team, fixture.away_team_id)
        if not league or not home_team or not away_team:
            return False

        connector = UnderstatConnector()
        try:
            data = await connector.fetch_match_stats(
                league.external_ref,
                fixture.season_year,
                fixture.kickoff_at.date(),
                home_team.name,
                away_team.name,
            )
        except ValueError:
            # Competition not covered by Understat - not an error, just
            # nothing to enrich.
            return False
        except Exception as e:  # noqa: BLE001 - scraper, many ways to fail
            logger.warning(f"Understat enrichment failed for fixture {fixture.id}: {e}")
            return False

        if not data:
            return False

        from app.connectors.soccerdata_sofascore import _team_ref

        team_id_by_ref = {
            _team_ref(home_team.name): home_team.id,
            _team_ref(away_team.name): away_team.id,
        }

        for ps in data.player_stats:
            team_id = team_id_by_ref.get(ps.team_external_ref)
            if not team_id:
                continue
            existing = (
                await self.session.exec(
                    select(PlayerMatchStat).where(
                        PlayerMatchStat.fixture_id == fixture.id,
                        PlayerMatchStat.source == connector.source,
                        PlayerMatchStat.external_ref == ps.external_ref,
                    )
                )
            ).first()
            values = dict(
                team_id=team_id,
                player_name=ps.player_name,
                position=ps.position,
                minutes=ps.minutes,
                goals=ps.goals,
                own_goals=ps.own_goals,
                shots=ps.shots,
                xg=ps.xg,
                xg_chain=ps.xg_chain,
                xg_buildup=ps.xg_buildup,
                assists=ps.assists,
                xa=ps.xa,
                key_passes=ps.key_passes,
                yellow_cards=ps.yellow_cards,
                red_cards=ps.red_cards,
            )
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                existing.updated_at = utcnow()
                self.session.add(existing)
            else:
                self.session.add(
                    PlayerMatchStat(
                        fixture_id=fixture.id,
                        source=connector.source,
                        external_ref=ps.external_ref,
                        **values,
                    )
                )

        for ts in data.team_stats:
            team_id = team_id_by_ref.get(ts.team_external_ref)
            if not team_id:
                continue
            existing = (
                await self.session.exec(
                    select(TeamMatchStat).where(
                        TeamMatchStat.fixture_id == fixture.id,
                        TeamMatchStat.team_id == team_id,
                    )
                )
            ).first()
            values = dict(
                points=ts.points,
                expected_points=ts.expected_points,
                goals=ts.goals,
                xg=ts.xg,
                np_xg=ts.np_xg,
                np_xg_difference=ts.np_xg_difference,
                ppda=ts.ppda,
                deep_completions=ts.deep_completions,
            )
            if existing:
                for k, v in values.items():
                    setattr(existing, k, v)
                existing.updated_at = utcnow()
                self.session.add(existing)
            else:
                self.session.add(
                    TeamMatchStat(
                        fixture_id=fixture.id,
                        team_id=team_id,
                        source=connector.source,
                        **values,
                    )
                )

        for shot in data.shots:
            team_id = team_id_by_ref.get(shot.team_external_ref)
            if not team_id:
                continue
            existing = (
                await self.session.exec(
                    select(ShotEvent).where(
                        ShotEvent.source == connector.source,
                        ShotEvent.external_ref == shot.external_ref,
                    )
                )
            ).first()
            if existing:
                continue  # a shot is an immutable historical event
            self.session.add(
                ShotEvent(
                    fixture_id=fixture.id,
                    team_id=team_id,
                    source=connector.source,
                    external_ref=shot.external_ref,
                    player_name=shot.player_name,
                    assist_player_name=shot.assist_player_name,
                    minute=shot.minute,
                    xg=shot.xg,
                    location_x=shot.location_x,
                    location_y=shot.location_y,
                    body_part=shot.body_part,
                    situation=shot.situation,
                    result=shot.result,
                )
            )

        await self.session.commit()
        logger.info(
            f"Synced Understat stats for fixture {fixture.id}: "
            f"{len(data.player_stats)} players, {len(data.shots)} shots"
        )
        return True
