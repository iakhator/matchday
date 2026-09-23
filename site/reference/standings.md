# Standings

<MethodBadge method="GET" path="/api/v1/leagues/{id}/standings" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: '30 min' },
]" />

The league table for a season.

## Query parameters

<ParamCard name="season" type="integer">
Defaults to the league's current season.
</ParamCard>

## Request

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/leagues/2021/standings \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const table = await fetch(
  "https://api.matchday.example/api/v1/leagues/2021/standings",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
table = httpx.get(
    "https://api.matchday.example/api/v1/leagues/2021/standings",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

```json
{
  "items": [
    {
      "id": "01991e3a-...",
      "league_id": 2021,
      "season_year": 2026,
      "team": { "id": 65, "name": "Manchester City FC", "display_name": "Man City", "...": "..." },
      "rank": 1,
      "points": 68,
      "played": 29,
      "won": 21,
      "drawn": 5,
      "lost": 3,
      "goals_for": 64,
      "goals_against": 24,
      "form": "WWDWL",
      "last_synced_at": "2026-09-20T13:31:00Z"
    }
  ],
  "total": 20
}
```

`form` is the five most recent results, most recent last - `W`/`D`/`L`.
`team` is a full [team](/reference/teams) object.

Head-to-head and "most predicted outcome" aren't here, and won't be
added - those are derivable from your own app's historical match/
prediction data, not something an upstream feed provides.
