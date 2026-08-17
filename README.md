<div align="center">
  <img src="docs/assets/banner.svg" alt="Matchday" width="600">

  <p><strong>A self-hosted football (soccer) data gateway.</strong></p>

  ![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)
  ![Status](https://img.shields.io/badge/status-early%20%2F%20MVP-yellow)
  ![FastAPI](https://img.shields.io/badge/api-FastAPI-009688)
</div>

Matchday continuously syncs leagues, teams, fixtures and scores from
pluggable upstream connectors, normalizes them into a stable schema, and
serves them through its own REST API - so the app that depends on it (like
[Predify](../predify)) only ever talks to *your* API, not directly to a
third-party vendor.

## Contents

- [Why this exists](#why-this-exists)
- [What it does (and doesn't) solve](#what-it-does-and-doesnt-solve)
- [Architecture](#architecture)
- [Adding a connector](#adding-a-connector)
- [Local development](#local-development)
- [Backfill fallback](#backfill-fallback-optional-off-by-default)
- [Consuming this from another app](#consuming-this-from-another-app)
- [Status](#status)

## Why this exists

Third-party football data APIs (api-sports.io, Sportmonks, etc.) work, but
they're a single point of failure and a recurring cost. This gateway sits
between your app and the upstream data source(s):

```
Your app  -->  matchday-gateway (this repo)  -->  connector(s)  -->  upstream provider(s)
```

The connector layer is a plugin interface (`app/connectors/base.py`) - swap
or add upstream sources without touching your app at all. Ship with one
connector, add more later (a second free API as a fallback, a scraper, a
static seasonal dataset), and the gateway falls through to the next one on
failure automatically.

## What it does (and doesn't) solve

| Data | Handled here? |
|---|---|
| Leagues, teams | Yes - synced daily |
| Fixtures/schedule (including postponements/reschedules) | Yes - synced continuously |
| Scores/results | Yes - synced continuously |
| Head-to-head, standings, "most predicted outcome" | **No** - these are derivable from your own app's historical match/prediction data. Compute them in your app, not here. |
| Player stats, betting odds | Not yet - genuinely needs its own upstream feed. Left as a future connector; see below. |

## Architecture

- `app/connectors/` - the plugin interface (`Connector` ABC) + one real
  implementation against [football-data.org](https://www.football-data.org)
  v4 (free tier, no credit card required).
- `app/services/sync_service.py` - fetches from connectors (falling back to
  the next one in the registry on failure), normalizes, upserts into the DB.
- `app/scheduler/` - APScheduler jobs: league/team metadata daily, fixtures
  every 15 minutes, plus a fast live-score job every 60 seconds that only
  calls the upstream API when a competition actually has a fixture in its
  live window (cheap DB check first) - all configurable via
  `SchedulerConfig`.
- `app/api/v1/` - the REST API your app calls: `/leagues`,
  `/leagues/{id}/teams`, `/leagues/{id}/fixtures`, `/fixtures/{id}`.
  Gated by a simple `X-Gateway-Key` header (disabled by default in dev).

## Adding a connector

Implement `app/connectors/base.py::Connector` (three methods:
`fetch_league`, `fetch_teams`, `fetch_fixtures`, each returning the
normalized Pydantic models defined in the same file), then add it to
`app/connectors/registry.py::get_connectors()`. The sync service, scheduler
and REST API don't need to change.

## Local development

```bash
cp .env.example .env.local
# then fill in FOOTBALL_DATA_ORG_API_KEY - free signup at
# https://www.football-data.org/client/register

docker compose -f docker-compose.dev.yml up -d
```

Runs on `http://localhost:8010`. Health check: `GET /health`.

Trigger a manual sync (don't wait for the scheduler):

```bash
curl -X POST http://localhost:8010/api/v1/admin/sync
```

### Migrations

```bash
docker exec matchday_gateway_api_dev uv run alembic upgrade head
# after changing a model:
docker exec matchday_gateway_api_dev uv run alembic revision --autogenerate -m "description"
```

## Backfill fallback (optional, off by default)

If football-data.org is down while a match is played, its final score is
missed. `app/connectors/soccerdata_sofascore.py` can backfill it after the
fact from Sofascore, via a manual admin call - it is **not** part of the
automatic sync chain. Three reasons it's handled this way instead of being
just another connector in the registry:

1. It can only see FINISHED and NOT-YET-STARTED matches - Sofascore's
   live/in-play state isn't exposed by the library at all, so it can't
   serve live scores, only after-the-fact results.
2. Fetching a season's schedule costs roughly one HTTP request per round
   (~40 requests) - too expensive to run automatically on a schedule.
3. **It uses TLS fingerprint spoofing to get past Sofascore's bot
   detection.** The `soccerdata` library's HTTP layer (`tls_requests`,
   built on `bogdanfinn/tls-client`) replicates a real browser's TLS
   handshake so Sofascore's detection can't tell the difference. That's a
   materially different thing from calling a documented API with a key -
   it's deliberate evasion of an access control the site put up on
   purpose, even though the data itself (public match scores) is
   harmless. Enable this only if you're comfortable with that tradeoff for
   your own deployment.

To use it:

```bash
uv sync --extra soccerdata
# set ENABLE_SOCCERDATA_FALLBACK=true in .env.local

curl -X POST "http://localhost:8010/api/v1/admin/backfill-results?competition_code=PL"
```

It only ever **updates** fixtures the gateway already knows about (matched
by kickoff date + team name, since Sofascore doesn't share football-data
.org's IDs) - it never creates new fixtures or teams, so it can't produce
duplicate rows.

## Consuming this from another app

Both this repo and Predify join the same Docker network in dev
(`predify_predify-network`), so from inside Predify's API container this
gateway is reachable at `http://matchday_gateway_api_dev:8010`. Set
`GATEWAY_API_KEYS` here and pass the matching key as `X-Gateway-Key` from
the consuming app once you're ready to lock it down.

## Status

Early / MVP. Leagues, teams, fixtures and scores work end-to-end for
Premier League and La Liga via football-data.org, with a fast 60-second
live-score job on top of the 15-minute full sync. An optional, off-by-
default backfill fallback (Sofascore, via `soccerdata`) can fill in missed
final scores after an outage - see "Backfill fallback" above. Not yet
wired into Predify's backend (that's the next step - swapping
`football_api.py` in `predify/server` to call this gateway instead of
api-sports.io directly). Player stats and odds connectors are not built
yet.
