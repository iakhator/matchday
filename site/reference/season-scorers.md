# Season scorers

<MethodBadge method="GET" path="/api/v1/leagues/{id}/players" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: '30 min' },
]" />

Season-aggregate goals/assists/appearances - the top scorers table, not a
per-match breakdown (see [Advanced match stats](/reference/advanced-stats)
for that).

## Query parameters

<ParamCard name="season" type="integer">
Defaults to the league's current season.
</ParamCard>

<ParamCard name="team_id" type="array of integers">
Filter to one or more teams, e.g. for a head-to-head pick.
</ParamCard>

<ParamCard name="limit" type="integer" default="50">
Maximum rows returned, up to 100.
</ParamCard>

## Request

::: code-group

```bash [curl]
curl "https://api.matchday.example/api/v1/leagues/2021/players?limit=5" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const scorers = await fetch(
  "https://api.matchday.example/api/v1/leagues/2021/players?limit=5",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
scorers = httpx.get(
    "https://api.matchday.example/api/v1/leagues/2021/players",
    params={"limit": 5},
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

```json
{
  "items": [
    {
      "id": "01991e3b-...",
      "team_id": 57,
      "season_year": 2026,
      "name": "Bukayo Saka",
      "photo": "https://crests.football-data.org/persons/1234.png",
      "position": "Right Winger",
      "goals": 14,
      "assists": 9,
      "appearances": 27,
      "last_synced_at": "2026-09-20T13:31:00Z"
    }
  ],
  "total": 1
}
```

Sorted by goals, then assists, descending.
