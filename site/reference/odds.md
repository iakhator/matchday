# Odds

<MethodBadge method="GET" path="/api/v1/fixtures/{id}/odds" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Source', value: 'api-football' },
]" />

Pre-match 1X2 prices, one entry per bookmaker.

## Request

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/fixtures/500001/odds \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const odds = await fetch(
  "https://api.matchday.example/api/v1/fixtures/500001/odds",
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
odds = httpx.get(
    "https://api.matchday.example/api/v1/fixtures/500001/odds",
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

```json
{
  "fixture_id": 500001,
  "available": true,
  "source": "api_football",
  "items": [
    {
      "bookmaker": "Bet365",
      "home": 1.85,
      "draw": 3.9,
      "away": 4.2,
      "captured_at": "2026-09-20T08:00:00Z"
    }
  ],
  "total": 1
}
```

**`available` distinguishes "nobody priced this fixture" from "never
captured"** - both produce an empty `items` list, but only `available`
tells you whether that's expected or a gap.

**Odds cannot be fetched after kickoff.** Prices are captured while a
fixture is still upcoming; once a match starts, an empty list on that
fixture is permanent - there's no backfill path, upstream simply stops
serving them.
