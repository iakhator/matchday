# Advanced match stats

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/player-stats" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}/team-stats" />
<MethodBadge method="GET" path="/api/v1/fixtures/{id}/shots" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Source', value: 'Understat (optional)' },
]" />

Per-match xG, xA, PPDA and shot-level data. Understat-derived, and empty
on every deployment unless the gateway operator has set
`ENABLE_SOCCERDATA=true` - see the README's note on that tradeoff
(TLS-fingerprint spoofing to reach Understat) if you're self-hosting and
deciding whether to turn it on.

## Request

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/fixtures/500001/player-stats \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const stats = await fetch(
  "https://api.matchday.example/api/v1/fixtures/500001/player-stats",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
stats = httpx.get(
    "https://api.matchday.example/api/v1/fixtures/500001/player-stats",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Responses

**`/player-stats`**

```json
{
  "items": [
    {
      "id": "01991e3c-...",
      "fixture_id": 500001,
      "team_id": 57,
      "player_name": "Bukayo Saka",
      "position": "RW",
      "minutes": 90,
      "goals": 1,
      "own_goals": 0,
      "shots": 3,
      "xg": 0.62,
      "xg_chain": 0.81,
      "xg_buildup": 0.19,
      "assists": 1,
      "xa": 0.34,
      "key_passes": 2,
      "yellow_cards": 0,
      "red_cards": 0
    }
  ],
  "total": 1
}
```

**`/team-stats`**

```json
{
  "items": [
    {
      "id": "01991e3d-...",
      "fixture_id": 500001,
      "team_id": 57,
      "points": 3,
      "expected_points": 2.1,
      "goals": 2,
      "xg": 1.84,
      "np_xg": 1.61,
      "np_xg_difference": 0.72,
      "ppda": 9.4,
      "deep_completions": 11
    }
  ],
  "total": 1
}
```

**`/shots`**

```json
{
  "items": [
    {
      "id": "01991e3e-...",
      "fixture_id": 500001,
      "team_id": 57,
      "player_name": "Bukayo Saka",
      "assist_player_name": "Martin Ødegaard",
      "minute": 54,
      "xg": 0.38,
      "location_x": 0.89,
      "location_y": 0.47,
      "body_part": "right_foot",
      "situation": "open_play",
      "result": "goal"
    }
  ],
  "total": 1
}
```

`location_x`/`location_y` are normalized `0-1`, not pixel/pitch
coordinates - multiply by your own render surface's dimensions.
`np_xg` (non-penalty xG) and `ppda` (passes allowed per defensive action,
lower means more aggressive pressing) are the two team-level numbers
without an obvious plain-English name if you haven't seen them before.
