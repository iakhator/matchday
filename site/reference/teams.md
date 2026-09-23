# Teams

<MethodBadge method="GET" path="/api/v1/leagues/{id}/teams" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: 'Daily' },
]" />

Every team currently in a league's season roster.

## Request

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/leagues/2021/teams \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const teams = await fetch(
  "https://api.matchday.example/api/v1/leagues/2021/teams",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
teams = httpx.get(
    "https://api.matchday.example/api/v1/leagues/2021/teams",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

```json
[
  {
    "id": 57,
    "league_id": 2021,
    "season_year": 2026,
    "name": "Arsenal FC",
    "short_name": "Arsenal",
    "display_name": "Arsenal",
    "code": "ARS",
    "logo": "https://crests.football-data.org/57.png",
    "venue": "Emirates Stadium"
  },
  {
    "id": 65,
    "league_id": 2021,
    "season_year": 2026,
    "name": "Manchester City FC",
    "short_name": "Man City",
    "display_name": "Man City",
    "code": "MCI",
    "logo": "https://crests.football-data.org/65.png",
    "venue": "Etihad Stadium"
  }
]
```

`short_name` is exactly what the upstream provider sent - never
overwritten, so you can always reconcile against the source. `display_name`
is what to actually render: it matches `short_name` for almost every club,
but a handful of upstream short names are nicknames rather than usable
labels ("Atleti", "Barça"), and those are corrected by a small curated map.

<ErrorCode code="404" title="No league with that id">
The league itself doesn't exist - not to be confused with an empty
result, which just means no roster has synced yet.
</ErrorCode>
