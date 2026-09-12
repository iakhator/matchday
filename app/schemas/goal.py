from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class GoalOut(BaseModel):
    """One goal in a match.

    `team_id` is the team the goal *counts for*. For an own goal that is
    not the scorer's team - upstream records the shot against the team of
    the player who took it, so crediting `team_id` directly would hand the
    goal to the side that conceded it. `player_team_id` keeps the scorer's
    actual team available.
    """

    minute: int
    player_name: str
    assist_player_name: Optional[str]
    team_id: int
    player_team_id: int
    is_own_goal: bool
    xg: float

    model_config = ConfigDict(from_attributes=True)


class GoalListResponse(BaseModel):
    """Goals for a fixture, with provenance.

    `enriched` distinguishes "this match finished 0-0" from "we have no
    goal data for this match". Both produce an empty list, and a consumer
    that cannot tell them apart will happily render a goalless scoreline
    for a 3-2 thriller.
    """

    fixture_id: int
    enriched: bool
    source: Optional[str]
    items: List[GoalOut]
    total: int
