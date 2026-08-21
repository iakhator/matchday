from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import aliased
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import Fixture, League, Team
from app.schemas.fixture import FixtureListResponse, FixtureOut
from app.schemas.team import TeamOut

router = APIRouter(tags=["fixtures"])


@router.get("/leagues/{league_id}/fixtures", response_model=FixtureListResponse)
async def list_fixtures(
    league_id: int,
    season: Optional[int] = Query(
        None, description="Defaults to the league's current season"
    ),
    matchday: Optional[int] = Query(None),
    status: Optional[str] = Query(
        None, description="scheduled | live | finished | postponed | suspended | cancelled"
    ),
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
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

    items = [
        FixtureOut(
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
        for fixture, home_team, away_team in rows
    ]

    return FixtureListResponse(items=items, total=len(items))


@router.get("/fixtures/{fixture_id}", response_model=FixtureOut)
async def get_fixture(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
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
