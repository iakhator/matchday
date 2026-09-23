# Fixtures

<MethodBadge method="GET" path="/api/v1/leagues/{id}/fixtures" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: '15 min · 60s while live' },
]" />

The schedule and scores for a league's season - including postponements,
reschedules and results, all as status changes on the same fixture row
rather than separate events to reconcile.

## Query parameters (list only)

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

`GET /leagues/{id}/fixtures` returns `{ items, total }`. `GET /fixtures/{id}`
returns one `item` object directly.

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

<ErrorCode code="404" title="No league or fixture with that id">
Both endpoints 404 the same way - an unknown league id on the list
endpoint, or an unknown fixture id on the single-fixture one.
</ErrorCode>
