import asyncio
import re
import unicodedata
from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from app.connectors.soccerdata_sofascore import _team_ref

# football-data.org competition code -> Understat league key. Same codes
# as the Sofascore fallback connector, same coverage limitation (only
# leagues Understat actually tracks).
_LEAGUE_MAP = {
    "PL": "ENG-Premier League",
    "PD": "ESP-La Liga",
    "BL1": "GER-Bundesliga",
    "SA": "ITA-Serie A",
    "FL1": "FRA-Ligue 1",
}

# Understat uses short, unaccented team names ("Atletico Madrid") while
# football-data.org gives full official names ("Club Atlético de
# Madrid") - an exact _team_ref slug match never lines up. Strip accents
# and common club-name filler words, then compare token sets instead of
# strings, so "Club Atlético de Madrid" and "Atletico Madrid" both reduce
# to {"atletico", "madrid"}.
_NAME_STOPWORDS = {
    "cf", "fc", "club", "de", "real", "afc", "cd", "sc", "ud", "rcd", "ac", "ca",
}


def _name_tokens(name: str) -> set:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    tokens = set(re.findall(r"[a-z0-9]+", ascii_name.lower()))
    reduced = tokens - _NAME_STOPWORDS
    return reduced or tokens  # don't return empty if every token was a stopword


def _names_match(a: str, b: str) -> bool:
    tokens_a, tokens_b = _name_tokens(a), _name_tokens(b)
    return tokens_a <= tokens_b or tokens_b <= tokens_a


def _val(row, key, default=None):
    """`row[key] or default` breaks on pandas NA - bool(pd.NA) raises
    rather than being falsy. Understat leaves plenty of fields NA (no
    assist on a shot, no position for some rows), so every field read
    from these dataframes goes through this instead of `or`."""
    import pandas as pd

    value = row.get(key)
    return default if pd.isna(value) else value


class NormalizedPlayerMatchStat(BaseModel):
    external_ref: str
    team_external_ref: str
    player_name: str
    position: Optional[str] = None
    minutes: int = 0
    goals: int = 0
    own_goals: int = 0
    shots: int = 0
    xg: float = 0
    xg_chain: float = 0
    xg_buildup: float = 0
    assists: int = 0
    xa: float = 0
    key_passes: int = 0
    yellow_cards: int = 0
    red_cards: int = 0


class NormalizedTeamMatchStat(BaseModel):
    team_external_ref: str
    points: int = 0
    expected_points: float = 0
    goals: int = 0
    xg: float = 0
    np_xg: float = 0
    np_xg_difference: float = 0
    ppda: float = 0
    deep_completions: int = 0


class NormalizedShotEvent(BaseModel):
    external_ref: str
    team_external_ref: str
    player_name: str
    assist_player_name: Optional[str] = None
    minute: int
    xg: float
    location_x: float
    location_y: float
    body_part: Optional[str] = None
    situation: Optional[str] = None
    result: str


class NormalizedMatchStats(BaseModel):
    player_stats: List[NormalizedPlayerMatchStat]
    team_stats: List[NormalizedTeamMatchStat]
    shots: List[NormalizedShotEvent]


class UnderstatConnector:
    """Post-match enrichment only: advanced analytics (xG, xA, PPDA,
    shot-map data) that api-sports.io doesn't offer at any tier. Scraped
    via the `soccerdata` library (Understat has no official API), using
    the same TLS-fingerprint-spoofing technique already accepted for the
    Sofascore fallback connector - see that connector's docstring for the
    tradeoff; the same reasoning applies here. Only importable when
    ENABLE_SOCCERDATA=true.

    Deliberately NOT a `Connector` (registry.py/base.py) - this operates
    on one already-known, already-finished fixture at a time, matched by
    kickoff date + team names (Understat's own match ids don't correspond
    to football-data.org's, same identity problem as the Sofascore
    connector), rather than "fetch everything for a competition" the way
    the standard interface does.
    """

    source = "understat"

    def __init__(self) -> None:
        from soccerdata import Understat

        self._Understat = Understat

    @staticmethod
    def _require_league(competition_code: str) -> str:
        league_key = _LEAGUE_MAP.get(competition_code)
        if not league_key:
            raise ValueError(
                f"'{competition_code}' isn't covered by the Understat "
                f"connector - supported: {', '.join(_LEAGUE_MAP)}"
            )
        return league_key

    async def fetch_match_stats(
        self,
        competition_code: str,
        season_year: int,
        match_date: date,
        home_team_name: str,
        away_team_name: str,
    ) -> Optional[NormalizedMatchStats]:
        """Runs the blocking soccerdata/pandas calls in a thread so a slow
        scrape never blocks the event loop for other requests."""
        return await asyncio.to_thread(
            self._fetch_match_stats_sync,
            competition_code,
            season_year,
            match_date,
            home_team_name,
            away_team_name,
        )

    def _fetch_match_stats_sync(
        self,
        competition_code: str,
        season_year: int,
        match_date: date,
        home_team_name: str,
        away_team_name: str,
    ) -> Optional[NormalizedMatchStats]:
        league_key = self._require_league(competition_code)
        reader = self._Understat(leagues=league_key, seasons=season_year)

        schedule = reader.read_schedule().reset_index()

        match_row = None
        for _, row in schedule.iterrows():
            if (
                row["date"].date() == match_date
                and _names_match(row["home_team"], home_team_name)
                and _names_match(row["away_team"], away_team_name)
            ):
                match_row = row
                break

        if match_row is None or not bool(_val(match_row, "has_data", False)):
            return None

        game_id = int(match_row["game_id"])
        # Understat's own team ids for this specific match, mapped back to
        # the real team names so results can be resolved to our stable
        # Team rows the same way the schedule match itself was.
        team_name_by_understat_id = {
            int(match_row["home_team_id"]): home_team_name,
            int(match_row["away_team_id"]): away_team_name,
        }

        player_df = reader.read_player_match_stats(match_id=game_id).reset_index()
        team_df = reader.read_team_match_stats()
        team_df = team_df[team_df["game_id"] == game_id].reset_index()
        shots_df = reader.read_shot_events(match_id=game_id).reset_index()

        player_stats = [
            NormalizedPlayerMatchStat(
                external_ref=str(row["player_id"]),
                team_external_ref=_team_ref(
                    team_name_by_understat_id.get(int(row["team_id"]), "")
                ),
                player_name=row["player"],
                position=_val(row, "position"),
                minutes=int(_val(row, "minutes", 0)),
                goals=int(_val(row, "goals", 0)),
                own_goals=int(_val(row, "own_goals", 0)),
                shots=int(_val(row, "shots", 0)),
                xg=float(_val(row, "xg", 0)),
                xg_chain=float(_val(row, "xg_chain", 0)),
                xg_buildup=float(_val(row, "xg_buildup", 0)),
                assists=int(_val(row, "assists", 0)),
                xa=float(_val(row, "xa", 0)),
                key_passes=int(_val(row, "key_passes", 0)),
                yellow_cards=int(_val(row, "yellow_cards", 0)),
                red_cards=int(_val(row, "red_cards", 0)),
            )
            for _, row in player_df.iterrows()
        ]

        team_stats = []
        if not team_df.empty:
            row = team_df.iloc[0]
            for side, team_name in (("home", home_team_name), ("away", away_team_name)):
                team_stats.append(
                    NormalizedTeamMatchStat(
                        team_external_ref=_team_ref(team_name),
                        points=int(_val(row, f"{side}_points", 0)),
                        expected_points=float(_val(row, f"{side}_expected_points", 0)),
                        goals=int(_val(row, f"{side}_goals", 0)),
                        xg=float(_val(row, f"{side}_xg", 0)),
                        np_xg=float(_val(row, f"{side}_np_xg", 0)),
                        np_xg_difference=float(
                            _val(row, f"{side}_np_xg_difference", 0)
                        ),
                        ppda=float(_val(row, f"{side}_ppda", 0)),
                        deep_completions=int(_val(row, f"{side}_deep_completions", 0)),
                    )
                )

        shots = [
            NormalizedShotEvent(
                external_ref=str(row["shot_id"]),
                team_external_ref=_team_ref(
                    team_name_by_understat_id.get(int(row["team_id"]), "")
                ),
                player_name=row["player"],
                assist_player_name=_val(row, "assist_player"),
                minute=int(row["minute"]),
                xg=float(row["xg"]),
                location_x=float(row["location_x"]),
                location_y=float(row["location_y"]),
                body_part=_val(row, "body_part"),
                situation=_val(row, "situation"),
                result=row["result"],
            )
            for _, row in shots_df.iterrows()
        ]

        return NormalizedMatchStats(
            player_stats=player_stats, team_stats=team_stats, shots=shots
        )
