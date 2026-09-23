# Leagues

<MethodBadge method="GET" path="/api/v1/leagues" />
<MethodBadge method="GET" path="/api/v1/leagues/{id}" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
  { label: 'Updates', value: 'Daily' },
]" />

Every competition this gateway tracks. `id` is this gateway's own -
stable across upstream provider changes, not football-data.org's or
api-football's id. See [Lookup](/reference/lookup) if you're migrating
from another provider and need to translate ids you already hold.

## Request

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

## Response

`GET /leagues` returns a bare array. `GET /leagues/{id}` returns one
object of the same shape.

```json
[
  {
    "id": 2021,
    "name": "Premier League",
    "country": "England",
    "logo": "https://crests.football-data.org/PL.png",
    "current_season_year": 2026,
    "updated_at": "2026-08-17T05:17:01.677769Z"
  },
  {
    "id": 2014,
    "name": "Primera Division",
    "country": "Spain",
    "logo": "https://crests.football-data.org/laliga.png",
    "current_season_year": 2026,
    "updated_at": "2026-08-17T05:17:06.148380Z"
  }
]
```

`logo` points to the upstream provider's crest URL - see
[Data licensing and attribution](/guide/licensing) before displaying it;
crests are the clubs' trademarks, not covered by football-data.org's own
terms.

<ErrorCode code="404" title="No league with that id">
Returned by <code>GET /leagues/{id}</code> only.
</ErrorCode>
