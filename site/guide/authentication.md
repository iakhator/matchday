# Authentication and rate limits

Every request needs one header:

```
X-Gateway-Key: <your key>
```

Don't have one yet? [Sign up and generate one](/account/signup) - it's
free, self-serve, and takes under a minute.

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/leagues \
  -H "X-Gateway-Key: mk_live_your_key_here"
```

```js [JavaScript]
const res = await fetch("https://api.matchday.example/api/v1/leagues", {
  headers: { "X-Gateway-Key": "mk_live_your_key_here" },
});
const leagues = await res.json();
```

```python [Python]
import httpx

res = httpx.get(
    "https://api.matchday.example/api/v1/leagues",
    headers={"X-Gateway-Key": "mk_live_your_key_here"},
)
leagues = res.json()
```

:::

## The gateway fails closed

No key, or an invalid one, gets a `401`. A gateway with no keys configured
at all refuses every request with a `503` naming the setting that fixes
it, rather than quietly serving itself open to anyone who finds it.

## The 429 contract

Over your limit returns `429` with a `Retry-After` header in seconds, and
a body naming your limit:

```json
{ "detail": "Rate limit exceeded for 'your-app' (60 requests/minute)" }
```

The window slides rather than resetting on a clock boundary, so
`Retry-After` is the time until the oldest request in your current window
expires - often well under a minute, rather than a flat 60. Waiting
exactly that long is enough; a client that honors the header will not be
refused twice for the same reason.

```js [JavaScript]
if (res.status === 429) {
  const retryAfter = Number(res.headers.get("Retry-After"));
  await new Promise((r) => setTimeout(r, retryAfter * 1000));
}
```

```python [Python]
if res.status_code == 429:
    retry_after = int(res.headers["Retry-After"])
    time.sleep(retry_after)
```

Self-serve keys start at a conservative default limit. Need more? Reach
out once you know your real usage - this is a young project, and limits
are set from expected load, not a hard ceiling.

## Rotating a key

Revoke the old one and generate a new one from your
[dashboard](/account/dashboard) - there's no separate "rotate" action,
because a rotation is just a revoke and a create, and doing it as two
explicit steps means you're never holding a key you can't account for.

## Operating your own instance?

If you're self-hosting Matchday rather than consuming a hosted instance,
keys can also be configured directly via the `GATEWAY_API_KEYS`
environment variable - see the
[README](https://github.com/iakhator/matchday#authentication-and-rate-limits)
for that operator-facing path.
