# Pagination

Every list endpoint that can grow without bound - fixtures, standings and
season scorers - takes the same two query parameters:

<ParamCard name="limit" type="integer" default="50">
Max items per page, up to 100.
</ParamCard>

<ParamCard name="offset" type="integer" default="0">
Items to skip, for the next page.
</ParamCard>

```json
{
  "items": [ "..." ],
  "total": 247
}
```

`total` is the count of every row your filters match, not just the ones on
the current page - it doesn't shrink as you paginate through, so you can
use it to know when to stop:

```js [JavaScript]
let offset = 0;
const limit = 100;
const all = [];

while (true) {
  const page = await fetch(
    `https://api.matchday.example/api/v1/leagues/2021/fixtures?limit=${limit}&offset=${offset}`,
    { headers: { "X-Gateway-Key": "mk_live_your_key_here" } },
  ).then((r) => r.json());

  all.push(...page.items);
  offset += limit;
  if (offset >= page.total) break;
}
```

```python [Python]
import httpx

offset, limit = 0, 100
items = []

while True:
    page = httpx.get(
        "https://api.matchday.example/api/v1/leagues/2021/fixtures",
        params={"limit": limit, "offset": offset},
        headers={"X-Gateway-Key": "mk_live_your_key_here"},
    ).json()
    items.extend(page["items"])
    offset += limit
    if offset >= page["total"]:
        break
```

A request for `limit` above 100 is a `422`, not a silently clamped value -
a client that thinks it received everything when it didn't is worse than
one told plainly that its request was rejected.

Endpoints that return a bounded set by construction - a single fixture's
goals, shots, odds, or player/team match stats - aren't paginated. There's
no unbounded growth to protect against within one match.
