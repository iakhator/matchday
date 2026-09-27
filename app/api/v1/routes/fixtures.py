from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import aliased
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import Fixture, League, Team
from app.schemas.fixture import FixtureListResponse, FixtureOut
from app.schemas.team import TeamOut

router = APIRouter(tags=["fixtures"])


def _to_fixture_out(fixture: Fixture, home_team: Team, away_team: Team) -> FixtureOut:
    return FixtureOut(
        id=fixture.id,
        league_id=fixture.league_id,
        season_year=fixture.season_year,
        matchday=fixture.matchday,
        home_team=TeamOut.model_validate(home_team),
        away_team=TeamOut.model_validate(away_team),
        kickoff_at=fixture.kickoff_at,
        status=fixture.status,
        home_score=fixture.home_score,
        away_score=fixture.away_score,
        last_synced_at=fixture.last_synced_at,
    )


@router.get("/leagues/{league_id}/fixtures", response_model=FixtureListResponse)
async def list_fixtures(
    league_id: int,
    season: Optional[int] = Query(
        None, description="Defaults to the league's current season"
    ),
    matchday: Optional[int] = Query(None),
    status: Optional[str] = Query(
        None,
        description="scheduled | live | finished | postponed | suspended | cancelled",
    ),
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    season_year = season or league.current_season_year
    if not season_year:
        return FixtureListResponse(items=[], total=0)

    HomeTeam = aliased(Team, name="home_team")
    AwayTeam = aliased(Team, name="away_team")

    query = (
        select(Fixture, HomeTeam, AwayTeam)
        .join(HomeTeam, HomeTeam.id == Fixture.home_team_id)
        .join(AwayTeam, AwayTeam.id == Fixture.away_team_id)
        .where(
            Fixture.league_id == league.id,
            Fixture.season_year == season_year,
        )
        .order_by(Fixture.kickoff_at)
    )

    if matchday is not None:
        query = query.where(Fixture.matchday == matchday)
    if status is not None:
        query = query.where(Fixture.status == status)

    rows = (await session.exec(query)).all()

    items = [_to_fixture_out(fixture, home, away) for fixture, home, away in rows]

    return FixtureListResponse(items=items, total=len(items))


@router.get("/fixtures/{fixture_id}", response_model=FixtureOut)
async def get_fixture(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    HomeTeam = aliased(Team, name="home_team")
    AwayTeam = aliased(Team, name="away_team")

    query = (
        select(Fixture, HomeTeam, AwayTeam)
        .join(HomeTeam, HomeTeam.id == Fixture.home_team_id)
        .join(AwayTeam, AwayTeam.id == Fixture.away_team_id)
        .where(Fixture.id == fixture_id)
    )

    row = (await session.exec(query)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Fixture not found")

    fixture, home_team, away_team = row
    return _to_fixture_out(fixture, home_team, away_team)


@router.get("/teams/{team_id}/fixtures", response_model=FixtureListResponse)
async def list_team_fixtures(
    team_id: int,
    season: Optional[int] = Query(
        None, description="Defaults to the team's current league's current season"
    ),
    status: Optional[str] = Query(
        None,
        description="scheduled | live | finished | postponed | suspended | cancelled",
    ),
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """A team's own fixtures, home or away, regardless of which league
    they were played in - the single most common thing to build against
    a football API (a team page) had no direct route before this."""
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    season_year = season
    if season_year is None:
        league = await session.get(League, team.league_id)
        season_year = league.current_season_year if league else None
    if not season_year:
        return FixtureListResponse(items=[], total=0)

    HomeTeam = aliased(Team, name="home_team")
    AwayTeam = aliased(Team, name="away_team")

    query = (
        select(Fixture, HomeTeam, AwayTeam)
        .join(HomeTeam, HomeTeam.id == Fixture.home_team_id)
        .join(AwayTeam, AwayTeam.id == Fixture.away_team_id)
        .where(
            Fixture.season_year == season_year,
            or_(Fixture.home_team_id == team_id, Fixture.away_team_id == team_id),
        )
        .order_by(Fixture.kickoff_at)
    )

    if status is not None:
        query = query.where(Fixture.status == status)

    rows = (await session.exec(query)).all()

    items = [_to_fixture_out(fixture, home, away) for fixture, home, away in rows]

    return FixtureListResponse(items=items, total=len(items))
