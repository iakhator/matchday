# Endpoints

All endpoints are under `/api/v1` and require an `X-Gateway-Key` header -
see [Authentication and rate limits](/guide/authentication). `GET /health`
and `GET /health/scheduler` are the only ungated routes, so an uptime
monitor needs no credentials.

Every response carries `X-API-Version`. Within `/api/v1`, changes are
additive only - see [API versioning](/guide/versioning) before writing a
client that rejects unknown fields.

## Leagues

**`GET /leagues`** · **`GET /leagues/{id}`**

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/leagues \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const leagues = await fetch("https://api.matchday.example/api/v1/leagues", {
  headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY },
}).then((r) => r.json());
```

```python [Python]
import os, httpx

leagues = httpx.get(
    "https://api.matchday.example/api/v1/leagues",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Teams

**`GET /leagues/{id}/teams`**

Each team carries both `short_name` as synced and a `display_name` fit to
render. Upstream short names are usually right ("Borussia Dortmund" ->
"Dortmund") but a handful are nicknames ("Atleti", "Barça"); those are
corrected by a small curated map. The synced value is never overwritten,
so you can always reconcile against the source.

## Fixtures

**`GET /leagues/{id}/fixtures`** · **`GET /fixtures/{id}`**

::: code-group

```bash [curl]
curl "https://api.matchday.example/api/v1/leagues/2021/fixtures" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const fixtures = await fetch(
  "https://api.matchday.example/api/v1/leagues/2021/fixtures",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
fixtures = httpx.get(
    "https://api.matchday.example/api/v1/leagues/2021/fixtures",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Standings

**`GET /leagues/{id}/standings`**

## Season scorers

**`GET /leagues/{id}/players`**

## Advanced match stats

**`GET /fixtures/{id}/player-stats`** · **`GET /fixtures/{id}/team-stats`**
· **`GET /fixtures/{id}/shots`**

Understat-derived data (xG, xA, shot maps). Empty unless the gateway
operator has `ENABLE_SOCCERDATA=true` set - see the README's note on that
tradeoff if you're self-hosting.

## Goal events

**`GET /fixtures/{id}/goals`**

Scorer, assister and minute. Check the `enriched` flag before reading an
empty list as a goalless match: 0-0 and "no data" both return nothing
otherwise. Own goals are credited to the team they count for, not the team
of the player who scored them.

## Odds

**`GET /fixtures/{id}/odds`**

Pre-match 1X2 per bookmaker, each with the `captured_at` it was read.
`available` distinguishes "nobody priced this" from "never captured" -
and since odds cannot be fetched after kickoff, an empty list on a
finished fixture is permanent.

## Lookup (migrating from another provider)

**`GET /lookup/{entity_type}?source=...&external_id=...`**

Translate another provider's ids into this gateway's own. Takes several
ids at once (comma-separated, up to 500) and returns `resolved` plus an
explicit `unresolved` list, so you can see exactly which of your entities
aren't recognized rather than having them silently missing.

::: code-group

```bash [curl]
curl "https://api.matchday.example/api/v1/lookup/team?source=football_data_org&external_id=57,61" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const params = new URLSearchParams({
  source: "football_data_org",
  external_id: "57,61",
});
const mapped = await fetch(
  `https://api.matchday.example/api/v1/lookup/team?${params}`,
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
mapped = httpx.get(
    "https://api.matchday.example/api/v1/lookup/team",
    params={"source": "football_data_org", "external_id": "57,61"},
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

**`GET /lookup/{entity_type}/{internal_id}/aliases`** - the reverse: every
provider id known for one gateway row.

## Account (manage your own keys)

**`POST /account/keys`** · **`GET /account/keys`** ·
**`DELETE /account/keys/{id}`**

Gated by a Firebase sign-in token (`Authorization: Bearer <token>`), not
`X-Gateway-Key` - see [Getting started](/guide/getting-started) for the
full signup flow. `POST` returns the plaintext secret exactly once; it is
never shown again.

## Health

**`GET /health`** · **`GET /health/scheduler`**

Both unauthenticated. `/health` is liveness. `/health/scheduler` reports
`503` the moment any background sync job's heartbeat has gone stale -
useful if you're self-hosting and want to monitor your own instance.
