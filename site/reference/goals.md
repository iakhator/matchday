# Goal events

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/goals" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Source', value: 'api-football, falls back to Understat' },
]" />

Scorer, assister and minute for every goal in a match.

## Request

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/fixtures/500001/goals \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const goals = await fetch(
  "https://api.matchday.example/api/v1/fixtures/500001/goals",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
goals = httpx.get(
    "https://api.matchday.example/api/v1/fixtures/500001/goals",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

```json
{
  "fixture_id": 500001,
  "enriched": true,
  "source": "api_football",
  "items": [
    {
      "minute": 23,
      "player_name": "Bukayo Saka",
      "assist_player_name": "Martin Ødegaard",
      "team_id": 57,
      "player_team_id": 57,
      "is_own_goal": false,
      "xg": 0.38
    },
    {
      "minute": 67,
      "player_name": "Gabriel Magalhães",
      "assist_player_name": null,
      "team_id": 65,
      "player_team_id": 57,
      "is_own_goal": true,
      "xg": 0.0
    }
  ],
  "total": 2
}
```

**Check `enriched` before reading an empty `items` list as a goalless
match** - `0-0` and "we have no goal data for this fixture yet" both
produce an empty array, and only `enriched` tells them apart.

**Own goals are credited to the team they count for**, not the scorer's
own team - `team_id` is the side the goal counts for, `player_team_id` is
who actually took the shot. In the example above, Gabriel (Arsenal,
`player_team_id: 57`) scored an own goal that counts for Manchester City
(`team_id: 65`).
