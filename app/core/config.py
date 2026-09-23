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

    # Identity for the self-serve dashboard (account.py) - a *different*
    # auth plane from GATEWAY_API_KEYS/X-Gateway-Key above. Firebase
    # answers "who is this person"; this gateway still owns the API key
    # itself. The service account's raw JSON, not a file path, so this
    # works unchanged on platforms without mounted files (set it from a
    # secret manager at deploy time).
    FIREBASE_PROJECT_ID: Optional[str] = None
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None

    # Comma-separated origins allowed to call this API from a browser (the
    # docs site's signup/dashboard pages). Empty means no browser origin is
    # allowed - CORS is opt-in, not defaulted open.
    GATEWAY_CORS_ORIGINS: str = ""

    # Caps how many keys one self-serve account can hold, so a compromised
    # or careless account can only ever generate a bounded number of
    # buckets against this gateway's own (also bounded) upstream quota.
    MAX_API_KEYS_PER_USER: int = 5

    # Default limit for a self-serve-generated key. Deliberately lower than
    # DEFAULT_RATE_LIMIT_PER_MINUTE above (which is really an env-key
    # default, i.e. an operator who typed the config themselves) - an
    # unvetted signup gets a more conservative starting allowance.
    SELF_SERVE_RATE_LIMIT_PER_MINUTE: int = 60

    # api-football (api-sports.io). Supplies goal events and pre-match
    # odds, which football-data.org's free tier does not carry.
    API_FOOTBALL_KEY: Optional[str] = None
    API_FOOTBALL_BASE_URL: str = "https://v3.football.api-sports.io"

    # Their free plan allows 100 requests/day and there is no way to buy
    # more once spent. Kept slightly under the real cap so a manual admin
    # call is still possible after the scheduler has done its work.
    API_FOOTBALL_DAILY_BUDGET: int = 90

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
    def gateway_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.GATEWAY_CORS_ORIGINS.split(",") if o.strip()]

    @property
    def tracked_competitions(self) -> List[str]:
        return [c.strip() for c in self.TRACKED_COMPETITIONS.split(",") if c.strip()]


settings = Settings()
