# Fixtures

<MethodBadge method="GET" path="/api/v1/leagues/{id}/fixtures" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}" />
<MethodBadge method="GET" path="/api/v1/teams/{id}/fixtures" />
<MethodBadge method="GET" path="/api/v1/fixtures" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: '15 min · 60s while live' },
]" />

The schedule and scores for a league's season - including postponements,
reschedules and results, all as status changes on the same fixture row
rather than separate events to reconcile.

## Query parameters (list endpoints only)

<ParamCard name="season" type="integer">
Defaults to the league's current season on `/leagues/{id}/fixtures`, or the
team's current league's current season on `/teams/{id}/fixtures`.
</ParamCard>

<ParamCard name="matchday" type="integer">
Filter to a single matchday/gameweek. `/leagues/{id}/fixtures` only - a
team's fixtures aren't scoped to one competition's matchday numbering.
</ParamCard>

<ParamCard
  name="status"
  type="string (enum)"
  :enum-values="['scheduled', 'live', 'finished', 'postponed', 'suspended', 'cancelled']"
>
Filter fixtures by their current status. Supported on every list endpoint.
</ParamCard>

<ParamCard name="date_from" type="date (YYYY-MM-DD)">
`/fixtures` only. Inclusive, UTC. Must be given together with `date_to` -
see below.
</ParamCard>

<ParamCard name="date_to" type="date (YYYY-MM-DD)">
`/fixtures` only. Inclusive, UTC, at most 31 days after `date_from`.
</ParamCard>

## Cross-league discovery: `GET /fixtures`

The other list endpoints are scoped to one league or team, which bounds
the result on its own. `/fixtures` has no such boundary, so it requires
either a date range (`date_from` + `date_to`, capped at 31 days) or
`status=live` - live fixtures are inherently a small set, so that one is
allowed with no date range at all. Requesting neither, or only one half of
a date range, is a `400`.

::: code-group

```bash [curl - what's on this week]
curl "https://api.matchday.example/api/v1/fixtures?date_from=2026-09-22&date_to=2026-09-28" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```bash [curl - what's live right now]
curl "https://api.matchday.example/api/v1/fixtures?status=live" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

:::

## Request

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

## Response

`GET /leagues/{id}/fixtures` and `GET /teams/{id}/fixtures` both return
`{ items, total }`, in the same shape - `/teams/{id}/fixtures` returns every
fixture where the team played home or away, across whichever league it was
in at the time, ordered by kickoff. `GET /fixtures/{id}` returns one `item`
object directly.

```json
{
  "items": [
    {
      "id": 500001,
      "league_id": 2021,
      "season_year": 2026,
      "matchday": 29,
      "home_team": { "id": 57, "name": "Arsenal FC", "display_name": "Arsenal", "...": "..." },
      "away_team": { "id": 65, "name": "Manchester City FC", "display_name": "Man City", "...": "..." },
      "kickoff_at": "2026-09-20T14:00:00Z",
      "status": "live",
      "home_score": 2,
      "away_score": 1,
      "last_synced_at": "2026-09-20T15:08:12Z"
    }
  ],
  "total": 1
}
```

`home_team`/`away_team` are full [team](/reference/teams) objects, not
just ids - one request gets you the whole picture instead of a second
round trip per fixture. `status` is one of the six values above;
`last_synced_at` is when the gateway itself last confirmed this row
against upstream, not when the match happened - see
[How fresh is the data?](/guide/data-freshness) for what that lag
actually looks like in practice.

<ErrorCode code="404" title="No league, team or fixture with that id">
All three endpoints 404 the same way - an unknown league or team id on
their respective list endpoints, or an unknown fixture id on the
single-fixture one.
</ErrorCode>
