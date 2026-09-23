# Endpoints

All endpoints are under `/api/v1`. Every response carries `X-API-Version`.
Within `/api/v1`, changes are additive only - see
[API versioning](/guide/versioning) before writing a client that rejects
unknown fields.

## Leagues

<MethodBadge method="GET" path="/api/v1/leagues" />
<MethodBadge method="GET" path="/api/v1/leagues/{id}" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: 'Daily' },
]" />

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

<MethodBadge method="GET" path="/api/v1/leagues/{id}/teams" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: 'Daily' },
]" />

Each team carries both `short_name` as synced and a `display_name` fit to
render. Upstream short names are usually right ("Borussia Dortmund" ->
"Dortmund") but a handful are nicknames ("Atleti", "Barça"); those are
corrected by a small curated map. The synced value is never overwritten,
so you can always reconcile against the source.

## Fixtures

<MethodBadge method="GET" path="/api/v1/leagues/{id}/fixtures" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: '15 min · 60s while live' },
]" />

### Query parameters

<ParamCard name="season" type="integer">
Defaults to the league's current season.
</ParamCard>

<ParamCard name="matchday" type="integer">
Filter to a single matchday/gameweek.
</ParamCard>

<ParamCard
  name="status"
  type="string (enum)"
  :enum-values="['scheduled', 'live', 'finished', 'postponed', 'suspended', 'cancelled']"
>
Filter fixtures by their current status.
</ParamCard>

::: code-group

```bash [curl]
curl "https://api.matchday.example/api/v1/leagues/2021/fixtures?status=live" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const fixtures = await fetch(
  "https://api.matchday.example/api/v1/leagues/2021/fixtures?status=live",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
fixtures = httpx.get(
    "https://api.matchday.example/api/v1/leagues/2021/fixtures",
    params={"status": "live"},
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Standings

<MethodBadge method="GET" path="/api/v1/leagues/{id}/standings" />

<ParamCard name="season" type="integer">
Defaults to the league's current season.
</ParamCard>

## Season scorers

<MethodBadge method="GET" path="/api/v1/leagues/{id}/players" />

<ParamCard name="season" type="integer">
Defaults to the league's current season.
</ParamCard>

<ParamCard name="team_id" type="array of integers">
Filter to one or more teams, e.g. for a head-to-head pick.
</ParamCard>

<ParamCard name="limit" type="integer" default="50">
Maximum rows returned, up to 100.
</ParamCard>

## Advanced match stats

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/player-stats" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}/team-stats" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}/shots" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Source', value: 'Understat (optional)' },
]" />

Understat-derived data (xG, xA, shot maps). Empty unless the gateway
operator has `ENABLE_SOCCERDATA=true` set - see the README's note on that
tradeoff if you're self-hosting.

## Goal events

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/goals" />

Scorer, assister and minute. Check the `enriched` flag before reading an
empty list as a goalless match: 0-0 and "no data" both return nothing
otherwise. Own goals are credited to the team they count for, not the team
of the player who scored them.

## Odds

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/odds" />

Pre-match 1X2 per bookmaker, each with the `captured_at` it was read.
`available` distinguishes "nobody priced this" from "never captured" -
and since odds cannot be fetched after kickoff, an empty list on a
finished fixture is permanent.

## Lookup

<MethodBadge method="GET" path="/api/v1/lookup/{entity_type}" />
<MethodBadge method="GET" path="/api/v1/lookup/{entity_type}/{internal_id}/aliases" />

Translate another provider's ids into this gateway's own - useful if
you're migrating from api-sports.io or another source and don't want to
re-key your own history in one step.

<ParamCard name="source" type="string" :required="true">
Which provider the ids belong to, e.g. <code>football_data_org</code>.
</ParamCard>

<ParamCard name="external_id" type="string" :required="true">
Provider id, or several separated by commas (up to 500 per request).
</ParamCard>

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

**Error responses**

<ErrorCode code="400" title="Unknown entity_type or empty external_id list">
Names the valid entity types rather than returning an empty result that
looks like "none of your ids are known".
</ErrorCode>

<ErrorCode code="404" title="No mappings found (aliases endpoint)">
The internal id doesn't exist, or has no known provider mappings yet.
</ErrorCode>

## Account (manage your own keys)

<MethodBadge method="POST" path="/api/v1/account/keys" />
<MethodBadge method="GET" path="/api/v1/account/keys" />
<MethodBadge method="DELETE" path="/api/v1/account/keys/{id}" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'Bearer (Firebase)' },
  { label: 'Key cap', value: '5 per account (default)' },
]" />

Gated by a Firebase sign-in token (`Authorization: Bearer <token>`), not
`X-Gateway-Key` - see [Getting started](/guide/getting-started) for the
full signup flow. `POST` returns the plaintext secret exactly once; it is
never shown again.

<ErrorCode code="401" title="Missing or invalid sign-in token">
The Firebase bearer token is missing, expired, or fails verification.
</ErrorCode>

<ErrorCode code="422" title="Key limit reached">
Revoke an existing key before generating another.
</ErrorCode>

<ErrorCode code="404" title="Key not found (revoke)">
Either the key doesn't exist, or it belongs to a different account -
both look identical from the outside, on purpose.
</ErrorCode>

## Health

<MethodBadge method="GET" path="/health" />
<MethodBadge method="GET" path="/health/scheduler" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'None' },
]" />

Both unauthenticated so an uptime monitor needs no credentials.
`/health` is liveness. `/health/scheduler` reports `503` the moment any
background sync job's heartbeat has gone stale - useful if you're
self-hosting and want to monitor your own instance.
