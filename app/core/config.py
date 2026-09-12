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

    # Keys allowed to call this gateway's API, comma separated, each as
    # `name:secret` or `name:secret:requests_per_minute`. A bare secret
    # with no name still works - see app/core/api_keys.py.
    #
    #   GATEWAY_API_KEYS="predify:s3cret:120,analytics:other:30"
    GATEWAY_API_KEYS: str = ""

    # Run without auth. Only for local development: with this false and no
    # keys configured, the gateway refuses every request rather than
    # serving itself openly to whoever finds it.
    GATEWAY_ALLOW_ANONYMOUS: bool = False

    # Applied to any key that does not state its own limit. Sized for an
    # app polling live scores, not for bulk export.
    DEFAULT_RATE_LIMIT_PER_MINUTE: int = 120

    # Upstream connector credentials
    FOOTBALL_DATA_ORG_API_KEY: Optional[str] = None
    FOOTBALL_DATA_ORG_BASE_URL: str = "https://api.football-data.org/v4"

    # Which leagues to track, using football-data.org competition codes.
    # PL = Premier League, PD = La Liga (Primera Division), BL1 = Bundesliga
    TRACKED_COMPETITIONS: str = "PL,PD,BL1"

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
