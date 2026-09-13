"""api-football (api-sports.io), for what football-data.org's free tier lacks.

Deliberately **not** a general-purpose connector and deliberately not in
`app/connectors/registry.py`. `SyncService._first_success` tries registered
connectors in order for the *same* data - that is redundancy. This one is
complementary: it supplies goal events and pre-match odds, which the free
tier of the primary source does not carry at all, rather than standing in
for it.

The whole design here is shaped by one number: **100 requests per day.**
football-data.org's free tier allows 10 per minute, which is ~14,400 a day
- generous enough that the existing connector can retry freely and think
about rate limits only as a transient 429. Here the budget is the
constraint, and exhausting it means no odds and no goal events until
midnight UTC, with no way to buy more.

So this connector counts what it spends and refuses to start work it
cannot finish, rather than discovering the limit halfway through a
matchday.
"""

from datetime import date, datetime, timezone
from typing import List, Optional

import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.logger import logger


class NormalizedGoalEvent(BaseModel):
    """One goal, as this gateway understands it."""

    fixture_external_ref: str
    team_external_ref: str
    player_name: str
    assist_player_name: Optional[str] = None
    minute: int
    # "goal" | "own_goal" | "penalty" - upstream's `detail` field, mapped.
    kind: str = "goal"


class NormalizedOdds(BaseModel):
    fixture_external_ref: str
    bookmaker: str
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None


class NormalizedFixtureRef(BaseModel):
    """Just enough of a fixture to match it against one we already hold."""

    external_ref: str
    kickoff_at: datetime
    home_team_name: str
    away_team_name: str
    league_external_ref: str


# api-football's `detail` on a Goal event.
_GOAL_KIND = {
    "Normal Goal": "goal",
    "Own Goal": "own_goal",
    "Penalty": "penalty",
}


class DailyBudgetExceeded(RuntimeError):
    """Raised before spending a request that would breach the daily cap.

    A deliberate stop rather than a 429 partway through: a sync that dies
    halfway leaves some fixtures with odds and some without, and no signal
    saying which.
    """


class ApiFootballConnector:
    source = "api_football"

    def __init__(self, daily_budget: Optional[int] = None) -> None:
        if not settings.API_FOOTBALL_KEY:
            raise RuntimeError(
                "API_FOOTBALL_KEY is not set - free key at https://www.api-football.com/"
            )
        self._base_url = settings.API_FOOTBALL_BASE_URL
        self._headers = {"x-apisports-key": settings.API_FOOTBALL_KEY}
        self._budget = daily_budget or settings.API_FOOTBALL_DAILY_BUDGET

        # Counted in-process, which is enough: one gateway, one scheduler.
        # `remaining_today()` reads the real figure from upstream when it
        # matters, since this resets on restart.
        self._spent = 0
        self._spent_on = date.today()

    # ---------------------------------------------------------------- http

    def _note_spend(self) -> None:
        today = date.today()
        if today != self._spent_on:
            self._spent, self._spent_on = 0, today
        if self._spent >= self._budget:
            raise DailyBudgetExceeded(
                f"api-football daily budget of {self._budget} requests is "
                f"used up. It resets at midnight UTC; there is no way to "
                f"buy more on the free plan."
            )
        self._spent += 1

    async def _get(self, path: str, params: Optional[dict] = None) -> dict:
        self._note_spend()
        async with httpx.AsyncClient(base_url=self._base_url, timeout=20.0) as client:
            response = await client.get(path, headers=self._headers, params=params)
            response.raise_for_status()
            payload = response.json()

        # api-football answers 200 with an `errors` object rather than an
        # HTTP error code, so a quota or plan problem looks like success to
        # anything checking the status. Predify's fixture sync died
        # silently for exactly this reason - a plan restriction on the
        # `ids=` parameter returned 200 and an empty response.
        errors = payload.get("errors")
        if errors:
            raise RuntimeError(f"api-football returned errors for {path}: {errors}")
        return payload

    async def remaining_today(self) -> Optional[int]:
        """Requests left according to upstream, not our own count.

        Worth asking before a large job: the in-process counter resets on
        restart, and a redeploy mid-matchday would otherwise make the
        connector think it has a full budget it does not have.
        """
        payload = await self._get("/status")
        requests = (payload.get("response") or {}).get("requests") or {}
        current, limit = requests.get("current"), requests.get("limit_day")
        if current is None or limit is None:
            return None
        return max(0, limit - current)

    # ------------------------------------------------------------- fixtures

    async def fetch_fixtures_for_date(self, on: date) -> List[NormalizedFixtureRef]:
        """Every fixture api-football knows about on one date.

        One request covers every competition - 1,130 fixtures across 335
        leagues on a normal Saturday. Mapping a day's fixtures per league
        would cost a request each and exhaust the budget by lunchtime.
        """
        payload = await self._get("/fixtures", params={"date": on.isoformat()})

        refs = []
        for row in payload.get("response", []):
            fixture, teams, league = row["fixture"], row["teams"], row["league"]
            refs.append(
                NormalizedFixtureRef(
                    external_ref=str(fixture["id"]),
                    kickoff_at=datetime.fromisoformat(
                        fixture["date"].replace("Z", "+00:00")
                    ).astimezone(timezone.utc),
                    home_team_name=teams["home"]["name"],
                    away_team_name=teams["away"]["name"],
                    league_external_ref=str(league["id"]),
                )
            )
        logger.info(f"api-football: {len(refs)} fixtures on {on.isoformat()}")
        return refs

    # ---------------------------------------------------------------- goals

    async def fetch_goal_events(self, fixture_ref: str) -> List[NormalizedGoalEvent]:
        """Goals only, from the full events timeline.

        Cards and substitutions come back in the same response and are
        discarded - taking them would mean another model and another
        endpoint to maintain for data nothing asks for yet.
        """
        payload = await self._get("/fixtures/events", params={"fixture": fixture_ref})

        goals = []
        for event in payload.get("response", []):
            if event.get("type") != "Goal":
                continue
            assist = (event.get("assist") or {}).get("name")
            goals.append(
                NormalizedGoalEvent(
                    fixture_external_ref=str(fixture_ref),
                    team_external_ref=str(event["team"]["id"]),
                    player_name=(event.get("player") or {}).get("name") or "Unknown",
                    assist_player_name=assist,
                    minute=(event.get("time") or {}).get("elapsed") or 0,
                    kind=_GOAL_KIND.get(event.get("detail"), "goal"),
                )
            )
        return goals

    # ----------------------------------------------------------------- odds

    async def fetch_odds(self, fixture_ref: str) -> List[NormalizedOdds]:
        """Pre-match 1X2 odds, one row per bookmaker.

        Every bookmaker in the response is kept - they arrive together, so
        storing several costs no extra requests and lets a consumer see a
        spread rather than one house's opinion.

        Returns empty for a fixture that has already kicked off. Odds are
        not backfillable: if the capture window is missed, they are gone.
        """
        payload = await self._get("/odds", params={"fixture": fixture_ref})

        rows = []
        for entry in payload.get("response", []):
            for bookmaker in entry.get("bookmakers", []):
                match_winner = next(
                    (
                        b
                        for b in bookmaker.get("bets", [])
                        if b.get("name") == "Match Winner"
                    ),
                    None,
                )
                if not match_winner:
                    continue
                prices = {
                    v.get("value"): _as_float(v.get("odd"))
                    for v in match_winner.get("values", [])
                }
                rows.append(
                    NormalizedOdds(
                        fixture_external_ref=str(fixture_ref),
                        bookmaker=bookmaker.get("name") or "unknown",
                        home=prices.get("Home"),
                        draw=prices.get("Draw"),
                        away=prices.get("Away"),
                    )
                )
        return rows


def _as_float(value) -> Optional[float]:
    """Odds arrive as strings ("2.60"). A malformed one should cost that
    price, not the whole fixture's odds."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
