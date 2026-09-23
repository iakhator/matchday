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
- [API versioning and stability](#api-versioning-and-stability)
- [Authentication and rate limits](#authentication-and-rate-limits)
- [How fresh is the data?](#how-fresh-is-the-data)
- [Adding a connector](#adding-a-connector)
- [Mapping ids from another provider](#mapping-ids-from-another-provider)
- [Local development](#local-development)
- [Deploying](#deploying)
- [Optional connectors, and the tradeoff they carry](#optional-connectors-and-the-tradeoff-they-carry)
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
| Scores/results | Yes - synced continuously, with a ~7 minute upstream delay on the free tier ([measured](#how-fresh-is-the-data)) |
| Standings, season scorers (goals/assists/appearances) | Yes - synced on their own cadence, see below |
| Advanced match stats (xG, xA, xG-chain/buildup, PPDA, shot maps) | Optional - via Understat, reactively enriched right when a fixture finishes. Off by default; see "Backfill fallback" below for the tradeoff |
| Goal events (scorer, assist, minute) | Yes - real events from api-football's free plan, including own goals and penalties. Falls back to Understat-derived goals for fixtures api-football has no mapping for |
| Head-to-head, "most predicted outcome" | **No** - these are derivable from your own app's historical match/prediction data. Compute them in your app, not here. |
| Betting odds | Yes - pre-match 1X2 from several bookmakers, via api-football's free plan. Captured before kickoff and **not backfillable**: upstream serves odds only while a fixture is upcoming |

## Data licensing and attribution

This gateway does not own any of the data it serves - it syncs it from an
upstream provider, and that provider's terms shape how this project can be
deployed: attribution is required, self-host with your own key (there is
deliberately no public hosted instance of this specific deployment
pattern), the cached data is not yours to keep once a subscription ends,
and crests/logos are not covered by football-data.org's own terms.

Full terms, and what they mean in practice: [Data licensing and
attribution](site/guide/licensing.md).

## Architecture

- `app/connectors/` - the plugin interface (`Connector` ABC) + a real
  implementation against [football-data.org](https://www.football-data.org)
  v4 (free tier, no credit card required), and
  [api-football](https://www.api-football.com) for goal events and odds,
  which football-data.org's free tier does not carry. The second is
  complementary rather than a fallback: it supplies different data, not the
  same data from elsewhere. Its free plan allows 100 requests/day, so the
  connector counts what it spends and refuses work it cannot finish. `understat.py` (advanced stats)
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
- `app/api/v1/` - the REST API your app calls: leagues, teams, fixtures,
  standings, season scorers, advanced match stats, goal events, odds,
  cross-provider lookup, and admin triggers. Gated by an `X-Gateway-Key`
  header - see "Authentication and rate limits" below. `GET /health` and
  `GET /health/scheduler` are deliberately ungated so an uptime monitor
  needs no credentials. Full endpoint-by-endpoint reference, including
  request/response examples: [site/reference/](site/reference/).

## API versioning and stability

What this API offers is a contract: code written against `/api/v1` keeps
working. Within a version, changes are additive only (new endpoints,
fields, params); breaking changes ship as a new version path (`/api/v2`)
served alongside the old one, never in place of it; anything being retired
carries `Deprecation`/`Sunset` headers with a minimum 6 months' notice.

Full policy, including the exact `Deprecation`/`Sunset` header contract:
[API versioning and stability](site/guide/versioning.md).

## Authentication and rate limits

Operator-configured keys are set as `name:secret` or
`name:secret:requests_per_minute`:

```bash
GATEWAY_API_KEYS="predify:s3cret:120,analytics:other-secret:30"
```

**The gateway fails closed.** With no keys configured (env or self-serve,
see #25) and no explicit opt-out, it refuses every request with a `503`
naming the setting that fixes it. For local development, opt out on
purpose - `docker-compose.dev.yml` already sets this:

```bash
GATEWAY_ALLOW_ANONYMOUS=true
```

Self-serve keys (a customer generating their own, via
[the dashboard](site/account/dashboard.md)) are a second, separate tier -
see [Firebase Auth for self-serve account access](https://github.com/iakhator/matchday/issues/45)
for how that's wired.

Full contract - the 429 response shape, `Retry-After` semantics, the
per-worker rate-limiting caveat: [Authentication and rate
limits](site/guide/authentication.md).

## How fresh is the data?

Measured, not asserted - roughly a seven-minute delay between something
happening and this gateway being able to see it, on football-data.org's
free tier. Full measured numbers and what they mean for what you can build
on this: [How fresh is the data?](site/guide/data-freshness.md).

Re-measure it on your own deployment with `scripts/latency_probe.py`:

```bash
python scripts/latency_probe.py --until 22:00   # capture a matchday
python scripts/latency_probe.py --report        # summarise the log
```

The probe asks the gateway which competitions exist rather than holding a
list of its own - an earlier version hardcoded the upstream provider's
competition ids, and when the gateway moved to ids of its own, every
request 404'd and the probe carried on for seven hours recording nothing.

## Adding a connector

Implement `app/connectors/base.py::Connector` (three methods:
`fetch_league`, `fetch_teams`, `fetch_fixtures`, each returning the
normalized Pydantic models defined in the same file), then add it to
`app/connectors/registry.py::get_connectors()`. The sync service, scheduler
and REST API don't need to change.

If the new source hands over its own identifiers, nothing else is needed -
the sync path records them in `external_ids` automatically. If it only
gives names, see below.

## Mapping ids from another provider

A source that identifies clubs by name rather than by id has to be matched
against what this gateway already knows, and matching names across
providers is not reliable enough to do unattended. Comparing this gateway
to another provider's dataset, a reasonable normalizer matched 36 of 40
fixtures and silently missed 4 - all one club, `Brighton` against
`Brighton & Hove Albion FC`. That failed safe by finding nothing; a looser
rule matches the *wrong* club just as quietly, and every consumer's
reference is then wrong with nothing to indicate it.

So mapping is proposed automatically and confirmed by hand:

```bash
# 1. propose - match names, write unverified mappings, emit a review file
python scripts/seed_external_ids.py propose \
    --source api_sports --input their_teams.json --out review.json

# 2. review - open review.json, check each row, set "approved": true

# 3. approve - import the reviewed file
python scripts/seed_external_ids.py approve --input review.json

python scripts/seed_external_ids.py pending   # what is still unreviewed
```

`their_teams.json` is just the other provider's teams:

```json
[{"external_id": "42", "name": "Brighton & Hove Albion"}]
```

The review file groups rows by what you actually have to do - confirm a
match, choose between candidates, or find one by hand - and is stable for
the same input, so a re-run diffs cleanly against the last one. Being a
file rather than a prompt means the review is committable and
attributable: when a mapping later turns out to be wrong, "who approved
this and what did it look like?" has an answer.

**Unverified mappings are invisible to the sync path.** A guessed mapping
is fine for a lookup, where a human is reading the answer and the
`verified` flag travels with it. It is not fine for writing fixtures, so
`SyncService` resolves with `verified_only=True` and skips anything
unconfirmed - the same behaviour it already has for a team it has never
seen. Nothing that is merely plausible ends up in data consumers depend
on.

Only confident matches are written at all. Weak, ambiguous and unmatched
rows are reported for review but deliberately not stored: an absent
mapping is honest about not knowing, while a weak guess sitting in the
table looks like knowledge.

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

### Docs site

```bash
cd site
npm install
npm run dev
```

The public-facing docs (getting started, endpoint reference, auth/
versioning/licensing policy, and the self-serve signup/dashboard pages) -
a separate VitePress project, not part of the Python app. See
`site/.env.example` for the Firebase config the signup/dashboard pages
need to actually authenticate anyone; without it they render a clear
"not configured" message instead of hanging.

## Deploying

Build the production image - `Dockerfile`, not `Dockerfile.dev`, which
runs with `--reload`, installs test dependencies and runs as root:

```bash
docker build -t matchday-gateway:latest .
```

It is a two-stage build: no build toolchain, no dev dependencies, runs as
an unprivileged user that does not own `/app`.

### Migrations belong to the release phase

The image takes a command:

```bash
docker run ... matchday-gateway:latest migrate   # apply migrations, exit
docker run ... matchday-gateway:latest serve     # run the API (default)
```

`serve` deliberately does **not** migrate on start. With more than one
replica, every container racing to migrate the same database makes "a
container restarted" and "the schema changed" the same event, which is not
something to discover mid-incident. And a failed migration inside the app
process looks like a crash loop, so the platform keeps restarting it
instead of stopping the deploy.

So run `migrate` as a release/pre-deploy step, before the new `serve`
containers start.

**Do not apply migrations by hand.** A database migrated ahead of the code
that is deployed will fail the next release phase on a revision it cannot
find, and you get to work that out while a deploy is half-done. Let the
pipeline own it.

### What must be set

| | |
| --- | --- |
| `DATABASE_URL` | Postgres, `postgresql+asyncpg://...` |
| `GATEWAY_API_KEYS` | at least one, as `name:secret` - see [Authentication](#authentication-and-rate-limits) |
| `FOOTBALL_DATA_ORG_API_KEY` | your own key |
| `GATEWAY_ALLOW_ANONYMOUS` | leave unset. `true` disables auth entirely |

Secrets come from the environment. `.env` files are excluded from the
image by `.dockerignore`, so a stray local config cannot be baked in.

Optional: `PORT` (default 8010) and `WEB_CONCURRENCY` (default 1). Raise
workers only having read the rate-limit note above - limits are counted
per process, so N workers allow N times the configured rate.

### Health and monitoring

Two endpoints, both unauthenticated so a monitor needs no credentials.

**`GET /health`** - liveness. Is the process up? This is what the image's
`HEALTHCHECK` uses.

**`GET /health/scheduler`** - is the data still being kept up to date?
Returns **503** when any job's heartbeat has gone stale, and 200 otherwise:

```json
{
  "status": "unhealthy",
  "stale_jobs": ["sync_standings_and_players"],
  "jobs": [
    {"job_id": "sync_fixtures", "last_run_at": "2026-09-13T07:48:11+00:00",
     "age_seconds": 186, "threshold_seconds": 1800, "stale": false},
    {"job_id": "sync_standings_and_players", "last_run_at": "...",
     "age_seconds": 40219, "threshold_seconds": 3600, "stale": true}
  ]
}
```

The status code matters more than the body. Uptime monitors alert on it by
default, and this endpoint used to return 200 while saying "unhealthy" -
so a monitor pointed at it would have stayed quiet forever while the
scheduler was dead. That is the precise failure it exists to catch.

Each job is measured against twice its own interval, so one slow cycle
never trips it. A fresh deploy seeds heartbeats rather than reporting
every job stale until it first runs; a restart does **not** reset a
genuinely stale job back to healthy.

### Wiring up a monitor

Point any uptime service at `https://your-gateway/health/scheduler` and
alert on non-2xx. Suggested check interval: 5 minutes - the tightest
threshold is 5 minutes (the live-score job), so anything faster only adds
noise.

```bash
# Or without a service, from anywhere with cron:
*/5 * * * * curl -fsS https://your-gateway/health/scheduler \
  || echo "matchday scheduler unhealthy" | mail -s "matchday" you@example.com
```

`curl -f` exits non-zero on 503, so the alert fires on exactly the
condition the endpoint reports.

**Route the alert somewhere you will actually see it.** An alert into a
channel nobody reads is indistinguishable from no alert, and a silently
dead sync job is what this whole mechanism is for.

**`/health/scheduler` is deliberately not the container healthcheck.** A
stale job means the data is going stale, not that the container is broken.
Restarting would neither fix the sync nor stop the restart loop - it would
just add an outage to a staleness problem.

## Optional connectors, and the tradeoff they carry

One flag, `ENABLE_SOCCERDATA`, gates two `soccerdata`-powered connectors.
It is **off by default**, and `soccerdata` is not installed unless you ask
for it (`uv sync --extra soccerdata`), so nothing below happens unless you
opt in twice.

> **Both connectors reach their sources through TLS fingerprint spoofing.**
>
> `soccerdata`'s HTTP layer (`tls_requests`, built on
> `bogdanfinn/tls-client`) replicates a real browser's TLS handshake so
> that bot detection cannot distinguish it from Chrome. That is a
> materially different thing from calling a documented API with a key: it
> is deliberate evasion of an access control the site put up on purpose,
> even though the data itself - public match scores and shot locations -
> is harmless.
>
> This applies to **both** connectors, not just Sofascore. `Understat`
> extends the same `BaseRequestsReader`, whose `_init_session` returns a
> `tls_requests.Client`. Enabling the flag for advanced stats alone does
> not avoid it.
>
> Enable this only if you are comfortable with that on your own
> deployment. It is off by default precisely so that choice is yours to
> make explicitly rather than inherit by installing this project.
>
> **Not for a hosted service.** Running this on your own machine for your
> own data is one decision; serving data obtained this way to paying
> customers is a materially different one, and it puts the liability on
> the operator rather than on the person who chose to enable a flag. Keep
> `ENABLE_SOCCERDATA=false` on anything you host for others.

Note that `GET /fixtures/{id}/goals` is derived from Understat shot data,
so goal events are part of what this flag gates - football-data.org
exposes none at the free tier.

The two connectors:

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
3. It shares the TLS-spoofing HTTP layer described above - as does the
   Understat connector. That is a property of `soccerdata` itself, not of
   this particular reader.

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
