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
- [Data licensing and attribution](#data-licensing-and-attribution)
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

```text
Your app  -->  matchday-gateway (this repo)  -->  connector(s)  -->  upstream provider(s)
```

The connector layer is a plugin interface (`app/connectors/base.py`) -
swap or add upstream sources without touching your app at all. Today it
ships with exactly one registered connector (football-data.org); the
fallback-chain behavior described below is implemented and tested
(`SyncService._first_success`), but there's nothing to fall through to
yet until a second general-purpose connector is added to
`app/connectors/registry.py`. `understat.py` and `soccerdata_sofascore.py`
already exist but serve narrower purposes - see "Backfill fallback" below
- so they're deliberately not in that registry.

## What it does (and doesn't) solve

| Data | Handled here? |
| --- | --- |
| Leagues, teams | Yes - synced daily |
| Fixtures/schedule (including postponements/reschedules) | Yes - synced continuously |
| Scores/results | Yes - synced continuously |
| Standings, season scorers (goals/assists/appearances) | Yes - synced on their own cadence, see below |
| Advanced match stats (xG, xA, xG-chain/buildup, PPDA, shot maps) | Optional - via Understat, reactively enriched right when a fixture finishes. Off by default; see "Backfill fallback" below for the tradeoff |
| Head-to-head, "most predicted outcome" | **No** - these are derivable from your own app's historical match/prediction data. Compute them in your app, not here. |
| Betting odds | Not yet - genuinely needs its own upstream feed. Left as a future connector. |

## Data licensing and attribution

This gateway does not own any of the data it serves - it syncs it from an
upstream provider. That provider's terms travel with the data, and they
shape how this project can be deployed. Read this before pointing anything
at a public instance.

**Attribution is required.** Any app or site built on this gateway must
display, in a visible place:

> Data provided by football-data.org

**Self-host with your own key.** Each deployment registers its own
football-data.org key and syncs its own copy. There is deliberately no
public hosted instance of this gateway, because re-serving a provider's
data to third parties is a different thing from syncing it into your own
app, and permission for the former has not been granted.

**The cached data is not yours to keep.** football-data.org's terms state
that after a subscription ends, the customer may no longer reference the
football data obtained through their API - fixtures, results, tables,
squad data, top scorers - on their own site or service. This gateway's
database is a *cache*, not an archive. Losing access upstream means the
cache has to go too.

**Crests and logos are not covered.** `Team.logo` and `League.logo` hold
URLs to club crests. Those are trademarks belonging to the clubs, not to
the data provider, and football-data.org is explicit that you must arrange
proof of intellectual property yourself before displaying them. Treat
those fields as references, and clear them independently before putting a
crest in front of users.

**If you want to run a public instance,** ask first - the provider invites
contact at `daniel@football-data.org`, and a written answer is the only
thing that makes it safe. This note records what the published
documentation says; it is not legal advice, and the authoritative terms
are whatever the provider states directly.

Free-tier limits worth knowing before you build on them: 10 requests per
minute, 12 competitions, delayed scores, no player-level detail (lineups,
cards, substitutions), and historical data restricted to the current
season.

## Architecture

- `app/connectors/` - the plugin interface (`Connector` ABC) + a real
  implementation against [football-data.org](https://www.football-data.org)
  v4 (free tier, no credit card required). `understat.py` (advanced stats)
  and `soccerdata_sofascore.py` (results backfill) are separate,
  narrower-purpose connectors - see "Backfill fallback" below.
- `app/services/sync_service.py` - fetches from connectors (falling back to
  the next one in the registry on failure), normalizes, upserts into the DB.
- `app/scheduler/` - APScheduler jobs: league/team metadata daily,
  fixtures every 15 minutes, standings + season scorer stats every 30
  minutes, plus a fast live-score job every 60 seconds that only calls the
  upstream API when a competition actually has a fixture in its live
  window (cheap DB check first) - all configurable via `SchedulerConfig`.
  Each job stamps a heartbeat on success; `GET /health/scheduler` reports
  unhealthy the moment any job's heartbeat goes stale (see
  `app/core/heartbeat.py`) - point an uptime monitor at it.
- `app/services/id_mapper.py` - translates an upstream provider's ids into
  this gateway's. Consumers build against ids this gateway owns, so an
  upstream can be swapped without their data changing underneath them; the
  `external_ids` table is where two providers' different ids for the same
  club get reconciled.
- `app/api/v1/` - the REST API your app calls:
  - `GET /leagues`, `GET /leagues/{id}`
  - `GET /leagues/{id}/teams`
  - `GET /leagues/{id}/fixtures`, `GET /fixtures/{id}`
  - `GET /leagues/{id}/standings`
  - `GET /leagues/{id}/players` (season scorer stats)
  - `GET /fixtures/{id}/player-stats`, `GET /fixtures/{id}/team-stats`,
    `GET /fixtures/{id}/shots` (Understat data, empty unless
    `ENABLE_SOCCERDATA=true`)
  - `GET /lookup/{entity_type}?source=...&external_id=...` - translate
    another provider's ids into this gateway's. Takes several ids at once
    (comma-separated, up to 500) and returns `resolved` plus an explicit
    `unresolved` list, so a consumer can see exactly which of its entities
    are unrecognised rather than having them silently missing.
  - `GET /lookup/{entity_type}/{internal_id}/aliases` - the reverse: every
    provider id known for one gateway row.
  - `POST /admin/sync`, `POST /admin/backfill-results`,
    `POST /admin/enrich-fixture/{id}` (manual triggers)

  All gated by a simple `X-Gateway-Key` header (disabled by default in
  dev) - see `app/core/auth.py`.

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

Runs on `http://localhost:8010`. Liveness: `GET /health`. Scheduler health
(are the sync jobs actually still running): `GET /health/scheduler`.

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

### Tests

```bash
docker exec matchday_gateway_api_dev uv run pytest app/tests/
```

Unit tests against an in-memory SQLite DB (no Postgres needed) - connector
normalization (status mapping, standings table selection, field
fallbacks), sync upsert/idempotency and unknown-team-ref skipping, the
connector fallback chain, the Sofascore team-name slug matching, API-key
auth, and the scheduler heartbeat logic itself.

## Backfill fallback (optional, off by default)

One flag, `ENABLE_SOCCERDATA`, gates two separate `soccerdata`-powered
connectors:

- **Understat advanced stats** (`app/connectors/understat.py`) - runs
  automatically, reactively, the moment a fixture's status flips to
  finished during a normal sync. No manual step needed once the flag is
  on.
- **Sofascore results backfill** (`app/connectors/soccerdata_sofascore.py`,
  described below) - manual admin call only, never automatic.

If football-data.org is down while a match is played, its final score is
missed. The Sofascore connector can backfill it after the fact, via a
manual admin call - it is **not** part of the automatic sync chain. Three
reasons it's handled this way instead of being just another connector in
the registry:

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
# set ENABLE_SOCCERDATA=true in .env.local

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

Early / MVP, but the core loop is solid. Leagues, teams, fixtures,
scores, standings and season scorer stats all work end-to-end for the
Premier League, La Liga and Bundesliga via football-data.org, with a fast
60-second live-score job on top of the 15-minute full sync. Scheduler health is
monitored (`GET /health/scheduler`) so a silently-dead sync job can't go
unnoticed. Advanced match stats (xG/xA/PPDA/shot maps, via Understat) and
an emergency results backfill (via Sofascore) are both optional, off by
default - see "Backfill fallback" above. Unit-tested (`app/tests/`) -
connector normalization, sync upsert/idempotency, the fallback chain, and
the heartbeat monitoring itself.

**Not yet wired into Predify's backend** - that's the deliberate next
step, swapping `football_api.py` in `predify/server` to call this gateway
instead of api-sports.io directly, once this repo is fully hardened.
Odds are not built yet. The connector registry currently holds exactly
one connector (football-data.org) - the fallback-chain mechanism itself
is implemented and tested, but there's no second general-purpose source
registered to fall through to yet.
