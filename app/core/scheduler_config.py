from app.core.config import settings


class SchedulerConfig:
    """Sync cadence for the gateway's background jobs.

    Leagues/teams change rarely (roughly once a season) so they're synced
    on a slow cadence. Fixtures/scores are the whole point of running a
    continuous scheduler - matches get postponed, rescheduled, and scored,
    so that job runs frequently.
    """

    TRACKED_COMPETITIONS = settings.tracked_competitions

    # How often to re-sync league/team metadata (minutes).
    LEAGUE_TEAM_SYNC_INTERVAL_MINUTES = 60 * 24  # once a day is plenty

    # How often to re-sync fixtures/scores for tracked competitions (minutes).
    FIXTURE_SYNC_INTERVAL_MINUTES = 15

    # How often to re-sync standings/player stats (minutes). These change
    # whenever a match finishes, same trigger as fixtures, but don't need
    # fixtures' 15-minute freshness - a slower dedicated cadence keeps this
    # well within football-data.org's free-tier 10 requests/minute budget.
    STANDINGS_AND_PLAYERS_SYNC_INTERVAL_MINUTES = 30

    # Fast-cadence live-score refresh (seconds). Only actually calls the
    # upstream API when a competition has a fixture in its live window (see
    # SyncService.has_live_window_fixtures) - not a blind poll around the
    # clock. football-data.org's free tier allows 10 requests/minute; at
    # this cadence even 5 simultaneous leagues cost 5 calls/min, well within
    # budget with headroom for the slower jobs and manual admin syncs.
    LIVE_FIXTURE_SYNC_INTERVAL_SECONDS = 60

    # How far back from "now" a fixture's kickoff still counts as "in its
    # live window" for the fast-cadence job - covers 90 minutes + stoppage
    # + halftime + a buffer for delayed kickoffs.
    LIVE_WINDOW_HOURS = 3
