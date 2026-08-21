from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class NormalizedLeague(BaseModel):
    external_id: int
    external_ref: str
    name: str
    country: Optional[str] = None
    logo: Optional[str] = None
    current_season_year: Optional[int] = None


class NormalizedTeam(BaseModel):
    external_ref: str
    name: str
    short_name: Optional[str] = None
    code: Optional[str] = None
    logo: Optional[str] = None
    venue: Optional[str] = None


class NormalizedFixture(BaseModel):
    external_ref: str
    matchday: Optional[int] = None
    home_team_external_ref: str
    away_team_external_ref: str
    kickoff_at: datetime
    status: str  # must be one of app.db.models.fixture.FIXTURE_STATUSES
    raw_status: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None


class NormalizedStanding(BaseModel):
    team_external_ref: str
    rank: int
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    form: Optional[str] = None


class NormalizedPlayerStat(BaseModel):
    external_ref: str
    team_external_ref: str
    name: str
    photo: Optional[str] = None
    position: Optional[str] = None
    goals: int = 0
    assists: int = 0
    appearances: int = 0


class Connector(ABC):
    """A pluggable upstream data source.

    Implement this to add a new provider (a different free API, a scraper,
    a static dataset) - the rest of the gateway (sync service, scheduler,
    REST API, DB schema) never needs to change. Every connector is
    responsible for translating its provider's field names/status strings
    into the normalized shapes above.
    """

    #: Short, stable identifier stored on every row this connector produces
    #: (e.g. "football_data_org"). Used for traceability and to avoid ID
    #: collisions between connectors that happen to reuse numeric IDs.
    source: str

    @abstractmethod
    async def fetch_league(self, competition_code: str) -> NormalizedLeague: ...

    @abstractmethod
    async def fetch_teams(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedTeam]: ...

    @abstractmethod
    async def fetch_fixtures(
        self,
        competition_code: str,
        season_year: int,
        matchday: Optional[int] = None,
    ) -> List[NormalizedFixture]: ...

    @abstractmethod
    async def fetch_standings(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedStanding]: ...

    @abstractmethod
    async def fetch_player_stats(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedPlayerStat]: ...
