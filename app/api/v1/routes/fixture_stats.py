from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import (
    Fixture,
    GoalEvent,
    PlayerMatchStat,
    ShotEvent,
    TeamMatchStat,
)
from app.schemas.goal import GoalListResponse, GoalOut
from app.schemas.player_match_stat import (
    PlayerMatchStatListResponse,
    PlayerMatchStatOut,
)
from app.schemas.shot_event import ShotEventListResponse, ShotEventOut
from app.schemas.team_match_stat import TeamMatchStatListResponse, TeamMatchStatOut

router = APIRouter(prefix="/fixtures/{fixture_id}", tags=["fixture-stats"])


async def _require_fixture(fixture_id: int, session: AsyncSession) -> Fixture:
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture


@router.get("/player-stats", response_model=PlayerMatchStatListResponse)
async def list_player_match_stats(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Advanced per-player match stats (xG, xA, xG-chain/buildup) from
    Understat. Empty if ENABLE_SOCCERDATA is off or Understat has no data
    for this fixture yet (only populated post-match)."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(PlayerMatchStat)
            .where(PlayerMatchStat.fixture_id == fixture_id)
            .order_by(PlayerMatchStat.xg.desc())
        )
    ).all()
    items = [PlayerMatchStatOut.model_validate(row) for row in rows]
    return PlayerMatchStatListResponse(items=items, total=len(items))


@router.get("/team-stats", response_model=TeamMatchStatListResponse)
async def list_team_match_stats(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Advanced team match stats (non-penalty xG, PPDA, deep completions,
    expected points) from Understat."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(TeamMatchStat).where(TeamMatchStat.fixture_id == fixture_id)
        )
    ).all()
    items = [TeamMatchStatOut.model_validate(row) for row in rows]
    return TeamMatchStatListResponse(items=items, total=len(items))


@router.get("/shots", response_model=ShotEventListResponse)
async def list_shot_events(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Shot-map data (location, xG, body part, situation, result) from
    Understat."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(ShotEvent)
            .where(ShotEvent.fixture_id == fixture_id)
            .order_by(ShotEvent.minute)
        )
    ).all()
    items = [ShotEventOut.model_validate(row) for row in rows]
    return ShotEventListResponse(items=items, total=len(items))


@router.get("/goals", response_model=GoalListResponse)
async def list_goals(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Goal events for a fixture: scorer, assister and minute.

    Derived from the shot data rather than fetched separately.
    football-data.org exposes no goal events at all on the current tier -
    `/matches/{id}` has no `goals`, `bookings` or `substitutions` key, so
    there is nothing there to sync. Understat's shot feed already carries
    everything a goal event needs, and more (xG, body part, assister), so
    this reads it rather than adding another upstream dependency.

    That means the same caveat as every other Understat-backed endpoint:
    empty unless `ENABLE_SOCCERDATA=true` and the competition is one
    Understat covers. Check `enriched` before concluding a match was
    goalless - see `GoalListResponse`.
    """
    fixture = await _require_fixture(fixture_id, session)

    # Real goal events first. Derived-from-shots is the fallback, kept for
    # fixtures api-football has no mapping for and for competitions it does
    # not cover - removing it would turn "we have xG but no events" into a
    # blank response.
    events = (
        await session.exec(
            select(GoalEvent)
            .where(GoalEvent.fixture_id == fixture_id)
            .order_by(GoalEvent.minute)
        )
    ).all()

    if events:
        return GoalListResponse(
            fixture_id=fixture_id,
            enriched=True,
            source=events[0].source,
            items=[
                GoalOut(
                    minute=event.minute,
                    player_name=event.player_name,
                    assist_player_name=event.assist_player_name,
                    # api-football reports the team a goal counts for, so
                    # this needs no flipping. Understat reports the
                    # scorer's team, which is why the derived path below
                    # does.
                    team_id=event.team_id,
                    player_team_id=(
                        fixture.away_team_id
                        if event.kind == "own_goal"
                        and event.team_id == fixture.home_team_id
                        else fixture.home_team_id
                        if event.kind == "own_goal"
                        else event.team_id
                    ),
                    is_own_goal=event.kind == "own_goal",
                    xg=0.0,
                )
                for event in events
            ],
            total=len(events),
        )

    shots = (
        await session.exec(
            select(ShotEvent)
            .where(ShotEvent.fixture_id == fixture_id)
            .order_by(ShotEvent.minute)
        )
    ).all()

    # Any shot at all means the fixture was enriched, so an empty goal list
    # is a genuine 0-0 rather than missing data. Falling back to team stats
    # covers the vanishingly rare match with no shots recorded.
    enriched = bool(shots)
    if not enriched:
        enriched = (
            await session.exec(
                select(TeamMatchStat).where(TeamMatchStat.fixture_id == fixture_id)
            )
        ).first() is not None

    goals = []
    seen = set()
    for shot in shots:
        if shot.result not in ("Goal", "Own Goal"):
            continue

        # Defence in depth. The sync path now deduplicates on the same
        # key, so this should never fire on freshly synced data - but a
        # doubled goal produces a visibly wrong scoreline, and a second
        # cheap check is worth more than the line it costs.
        #
        # xG and coordinates are part of the key deliberately. On
        # (minute, player, result) alone this would also collapse
        # rebounds; identical xG *and* identical coordinates is one event
        # recorded twice.
        signature = (
            shot.minute,
            shot.player_name,
            shot.result,
            shot.xg,
            shot.location_x,
            shot.location_y,
        )
        if signature in seen:
            continue
        seen.add(signature)

        own_goal = shot.result == "Own Goal"
        # Credit an own goal to the opponent. Verified against a real 4-0:
        # three goals recorded for the home side plus one own goal recorded
        # against the away side adds up to the four the scoreline shows.
        if own_goal:
            credited = (
                fixture.away_team_id
                if shot.team_id == fixture.home_team_id
                else fixture.home_team_id
            )
        else:
            credited = shot.team_id

        goals.append(
            GoalOut(
                minute=shot.minute,
                player_name=shot.player_name,
                assist_player_name=shot.assist_player_name,
                team_id=credited,
                player_team_id=shot.team_id,
                is_own_goal=own_goal,
                xg=shot.xg,
            )
        )

    return GoalListResponse(
        fixture_id=fixture_id,
        enriched=enriched,
        source=shots[0].source if shots else None,
        items=goals,
        total=len(goals),
    )
