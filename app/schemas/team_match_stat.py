import uuid

from pydantic import BaseModel, ConfigDict


class TeamMatchStatOut(BaseModel):
    id: uuid.UUID
    fixture_id: int
    team_id: int
    points: int
    expected_points: float
    goals: int
    xg: float
    np_xg: float
    np_xg_difference: float
    ppda: float
    deep_completions: int

    model_config = ConfigDict(from_attributes=True)


class TeamMatchStatListResponse(BaseModel):
    items: list[TeamMatchStatOut]
    total: int
