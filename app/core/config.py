from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "matchday-gateway"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = (
        "postgresql+asyncpg://gateway_user:dev_password@localhost:5433/matchday_gateway_dev"
    )

    # Comma-separated list of keys allowed to call this gateway's API.
    # Leave empty in development to disable auth entirely.
    GATEWAY_API_KEYS: str = ""

    # Upstream connector credentials
    FOOTBALL_DATA_ORG_API_KEY: Optional[str] = None
    FOOTBALL_DATA_ORG_BASE_URL: str = "https://api.football-data.org/v4"

    # Which leagues to track, using football-data.org competition codes.
    # PL = Premier League, PD = La Liga (Primera Division)
    TRACKED_COMPETITIONS: str = "PL,PD"

    # Off by default. Enables the Sofascore backfill fallback
    # (app/connectors/soccerdata_sofascore.py), a manually-triggered admin
    # action for filling in finished results if football-data.org was down
    # while they were played. Uses the `soccerdata` library, which spoofs
    # TLS fingerprints to get past Sofascore's bot detection - a real
    # tradeoff, not just an extra data source. Requires the optional
    # `soccerdata` dependency group. See README before enabling.
    ENABLE_SOCCERDATA: bool = False

    @property
    def gateway_api_keys(self) -> List[str]:
        return [k.strip() for k in self.GATEWAY_API_KEYS.split(",") if k.strip()]

    @property
    def tracked_competitions(self) -> List[str]:
        return [c.strip() for c in self.TRACKED_COMPETITIONS.split(",") if c.strip()]


settings = Settings()
