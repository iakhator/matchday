from datetime import datetime, timezone
from typing import List, Optional

import httpx

from app.connectors.base import (
    Connector,
    NormalizedFixture,
    NormalizedLeague,
    NormalizedPlayerStat,
    NormalizedStanding,
    NormalizedTeam,
)
from app.core.config import settings
from app.core.logger import logger

# football-data.org v4 status -> this gateway's normalized status.
# See https://docs.football-data.org/general/v4/match.html
_STATUS_MAP = {
    "SCHEDULED": "scheduled",
    "TIMED": "scheduled",
    "IN_PLAY": "live",
    "PAUSED": "live",
    "FINISHED": "finished",
    "AWARDED": "finished",
    "POSTPONED": "postponed",
    "SUSPENDED": "suspended",
    "CANCELLED": "cancelled",
}


class FootballDataOrgConnector(Connector):
    source = "football_data_org"

    def __init__(self) -> None:
        if not settings.FOOTBALL_DATA_ORG_API_KEY:
            raise RuntimeError(
                "FOOTBALL_DATA_ORG_API_KEY is not set - sign up for a free "
                "key at https://www.football-data.org/client/register"
            )
        self._base_url = settings.FOOTBALL_DATA_ORG_BASE_URL
        self._headers = {"X-Auth-Token": settings.FOOTBALL_DATA_ORG_API_KEY}

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        async with httpx.AsyncClient(base_url=self._base_url, timeout=15.0) as client:
            response = await client.get(path, headers=self._headers, params=params)
            response.raise_for_status()
            return response.json()

    async def fetch_league(self, competition_code: str) -> NormalizedLeague:
        data = await self._get(f"/competitions/{competition_code}")
        current_season = data.get("currentSeason") or {}
        start_date = current_season.get("startDate")

        return NormalizedLeague(
            external_id=data["id"],
            external_ref=data["code"],
            name=data["name"],
            country=(data.get("area") or {}).get("name"),
            logo=data.get("emblem"),
            current_season_year=(
                int(start_date.split("-")[0]) if start_date else None
            ),
        )

    async def fetch_teams(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedTeam]:
        data = await self._get(
            f"/competitions/{competition_code}/teams", params={"season": season_year}
        )

        teams = []
        for team in data.get("teams", []):
            teams.append(
                NormalizedTeam(
                    external_ref=str(team["id"]),
                    name=team["name"],
                    short_name=team.get("shortName"),
                    code=team.get("tla"),
                    logo=team.get("crest"),
                    venue=team.get("venue"),
                )
            )
        return teams

    async def fetch_fixtures(
        self,
        competition_code: str,
        season_year: int,
        matchday: Optional[int] = None,
    ) -> List[NormalizedFixture]:
        params = {"season": season_year}
        if matchday is not None:
            params["matchday"] = matchday

        data = await self._get(
            f"/competitions/{competition_code}/matches", params=params
        )

        fixtures = []
        for match in data.get("matches", []):
            raw_status = match.get("status", "")
            status = _STATUS_MAP.get(raw_status)
            if status is None:
                logger.warning(
                    f"Unrecognized football-data.org status '{raw_status}' "
                    f"on match {match.get('id')} - defaulting to 'scheduled'"
                )
                status = "scheduled"

            score = match.get("score") or {}
            full_time = score.get("fullTime") or {}
            kickoff_raw = match["utcDate"]
            kickoff_at = datetime.fromisoformat(
                kickoff_raw.replace("Z", "+00:00")
            ).astimezone(timezone.utc)

            fixtures.append(
                NormalizedFixture(
                    external_ref=str(match["id"]),
                    matchday=match.get("matchday"),
                    home_team_external_ref=str(match["homeTeam"]["id"]),
                    away_team_external_ref=str(match["awayTeam"]["id"]),
                    kickoff_at=kickoff_at,
                    status=status,
                    raw_status=raw_status,
                    home_score=full_time.get("home"),
                    away_score=full_time.get("away"),
                )
            )
        return fixtures

    async def fetch_standings(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedStanding]:
        data = await self._get(
            f"/competitions/{competition_code}/standings",
            params={"season": season_year},
        )

        # There's one "TOTAL" table plus (for some competitions) separate
        # HOME/AWAY breakdowns under the same `standings` list - only the
        # overall table is what Standing.rank/points etc represent.
        total_table = next(
            (s["table"] for s in data.get("standings", []) if s.get("type") == "TOTAL"),
            [],
        )

        standings = []
        for row in total_table:
            standings.append(
                NormalizedStanding(
                    team_external_ref=str(row["team"]["id"]),
                    rank=row["position"],
                    points=row["points"],
                    played=row["playedGames"],
                    won=row["won"],
                    drawn=row["draw"],
                    lost=row["lost"],
                    goals_for=row["goalsFor"],
                    goals_against=row["goalsAgainst"],
                    form=row.get("form"),
                )
            )
        return standings

    async def fetch_player_stats(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedPlayerStat]:
        # 100 is the max `limit` football-data.org's free tier accepts for
        # this endpoint - covers every player who's scored, which is the
        # only set a "hot player" pick could ever need anyway.
        data = await self._get(
            f"/competitions/{competition_code}/scorers",
            params={"season": season_year, "limit": 100},
        )

        stats = []
        for entry in data.get("scorers", []):
            player = entry.get("player") or {}
            team = entry.get("team") or {}
            stats.append(
                NormalizedPlayerStat(
                    external_ref=str(player["id"]),
                    team_external_ref=str(team["id"]),
                    name=player["name"],
                    position=player.get("position") or player.get("section"),
                    goals=entry.get("goals") or 0,
                    assists=entry.get("assists") or 0,
                    appearances=entry.get("playedMatches") or 0,
                )
            )
        return stats
