import re
from datetime import timezone
from typing import List, Optional

from app.connectors.base import (
    Connector,
    NormalizedFixture,
    NormalizedLeague,
    NormalizedPlayerStat,
    NormalizedStanding,
    NormalizedTeam,
)

# football-data.org competition code -> (Sofascore league key, country name).
# Only leagues Sofascore's soccerdata module actually covers - see
# Sofascore.available_leagues(). Codes not listed here aren't supported by
# this fallback (e.g. Champions League - Sofascore doesn't expose it via
# this library).
_LEAGUE_MAP = {
    "PL": ("ENG-Premier League", "England"),
    "PD": ("ESP-La Liga", "Spain"),
    "BL1": ("GER-Bundesliga", "Germany"),
    "SA": ("ITA-Serie A", "Italy"),
    "FL1": ("FRA-Ligue 1", "France"),
}


def _team_ref(name: str) -> str:
    """Sofascore's schedule data exposes team names, not stable numeric IDs,
    so this connector's own team identity is a slug of the name. Used both
    when building this connector's own NormalizedTeam rows and by
    SyncService.backfill_finished_results to match against existing teams
    from the primary connector (by slugging their names the same way)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return f"name:{slug}"


class SoccerDataSofascoreConnector(Connector):
    """Backfill-only fallback for FINISHED results, scraped from Sofascore
    via the `soccerdata` library. Deliberately NOT registered in
    `app/connectors/registry.py` / the automatic sync chain - see
    `SyncService.backfill_finished_results`, the only caller, for why this
    is a manually-triggered admin action instead of an automatic fallback:

    - It cannot see live match state at all. soccerdata's Sofascore reader
      only ever returns matches that are FINISHED or NOT YET STARTED
      (Sofascore status codes 100 / 0 - see soccerdata's sofascore.py), so
      it can't fill the live-score gap this was originally considered for.
    - A single season's schedule costs roughly one HTTP request per round
      (~40 for a 38-round league) - too expensive to run on every
      scheduler tick, live window or not.
    - soccerdata's HTTP layer spoofs TLS fingerprints (via `tls_requests` /
      bogdanfinn/tls-client) to get past Sofascore's bot detection. That's
      a materially different risk than calling a documented API with a
      key. Only importable when ENABLE_SOCCERDATA_FALLBACK=true - see
      README for the tradeoff before enabling it.
    """

    source = "soccerdata_sofascore"

    def __init__(self) -> None:
        # Imported lazily so the dependency - and its native TLS-spoofing
        # binary - is never pulled in or downloaded unless this connector
        # is actually instantiated.
        from soccerdata import Sofascore

        self._Sofascore = Sofascore

    def _reader(self, competition_code: str, season_year: int):
        league_key, _ = self._require_league(competition_code)
        return self._Sofascore(leagues=league_key, seasons=season_year)

    @staticmethod
    def _require_league(competition_code: str) -> tuple:
        mapped = _LEAGUE_MAP.get(competition_code)
        if not mapped:
            raise ValueError(
                f"'{competition_code}' isn't covered by the Sofascore "
                f"fallback - supported: {', '.join(_LEAGUE_MAP)}"
            )
        return mapped

    async def fetch_league(self, competition_code: str) -> NormalizedLeague:
        # Sofascore (via `soccerdata`) has no stable numeric competition id
        # to satisfy NormalizedLeague.external_id, and this connector is
        # never actually asked to create/update League rows in practice -
        # it's never in the active registry (see registry.py), and
        # backfill_finished_results takes an already-synced League in,
        # rather than fetching one itself. See class docstring.
        raise NotImplementedError(
            "SoccerDataSofascoreConnector only backfills finished fixture results"
        )

    async def fetch_teams(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedTeam]:
        reader = self._reader(competition_code, season_year)
        table = reader.read_league_table()
        names = sorted(set(table["team"]))
        return [
            NormalizedTeam(external_ref=_team_ref(name), name=name) for name in names
        ]

    async def fetch_fixtures(
        self,
        competition_code: str,
        season_year: int,
        matchday: Optional[int] = None,
    ) -> List[NormalizedFixture]:
        import pandas as pd

        reader = self._reader(competition_code, season_year)
        df = reader.read_schedule()

        fixtures = []
        for _, row in df.reset_index().iterrows():
            # read_schedule() only ever returns FINISHED or NOT-STARTED rows
            # - never live (see class docstring). Not-started rows have NaN
            # scores; skip them rather than emitting "scheduled" duplicates
            # of data the primary connector already owns - this fallback
            # only ever contributes finished results.
            if pd.isna(row["home_score"]) or pd.isna(row["away_score"]):
                continue
            if matchday is not None and int(row["round"]) != matchday:
                continue

            kickoff_at = row["date"]
            if kickoff_at.tzinfo is None:
                kickoff_at = kickoff_at.replace(tzinfo=timezone.utc)

            fixtures.append(
                NormalizedFixture(
                    external_ref=str(row["game_id"]),
                    matchday=int(row["round"]),
                    home_team_external_ref=_team_ref(row["home_team"]),
                    away_team_external_ref=_team_ref(row["away_team"]),
                    kickoff_at=kickoff_at,
                    status="finished",
                    raw_status="Ended",
                    home_score=int(row["home_score"]),
                    away_score=int(row["away_score"]),
                )
            )
        return fixtures

    async def fetch_standings(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedStanding]:
        # Backfill-only, for FINISHED fixture results - see class docstring.
        # Standings/player-stats aren't part of that job, so this connector
        # (never in the active registry anyway) doesn't support them.
        raise NotImplementedError(
            "SoccerDataSofascoreConnector only backfills finished fixture results"
        )

    async def fetch_player_stats(
        self, competition_code: str, season_year: int
    ) -> List[NormalizedPlayerStat]:
        raise NotImplementedError(
            "SoccerDataSofascoreConnector only backfills finished fixture results"
        )
