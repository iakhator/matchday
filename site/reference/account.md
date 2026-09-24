# Account

<MethodBadge method="POST" path="/api/v1/account/keys" />
<MethodBadge method="GET" path="/api/v1/account/keys" />
<MethodBadge method="DELETE" path="/api/v1/account/keys/{id}" />
<MethodBadge method="POST" path="/api/v1/account/keys/{id}/rotate" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'Bearer (Firebase)' },
  { label: 'Key cap', value: '5 per account (default)' },
]" />

Manage your own API keys. Gated by a Firebase sign-in token
(`Authorization: Bearer <token>`), **not** `X-Gateway-Key` - this is the
one part of the API answering "who is this person", not "is this a valid
gateway request". See [Getting started](/guide/getting-started) for the
full signup flow, or just use the [dashboard](/account/dashboard)
directly instead of calling these by hand.

## Create a key

<ParamCard name="name" type="string" :required="true">
1-100 characters. Yours to pick - used to tell your keys apart later, not
sent anywhere else.
</ParamCard>

::: code-group

```bash [curl]
curl -X POST https://api.matchday.example/api/v1/account/keys \
  -H "Authorization: Bearer $FIREBASE_ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app"}'
```

```js [JavaScript]
const key = await fetch("https://api.matchday.example/api/v1/account/keys", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${firebaseIdToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ name: "my-app" }),
}).then((r) => r.json());
```

```python [Python]
key = httpx.post(
    "https://api.matchday.example/api/v1/account/keys",
    headers={"Authorization": f"Bearer {firebase_id_token}"},
    json={"name": "my-app"},
).json()
```

:::

```json
{
  "id": "01991e3f-...",
  "name": "my-app",
  "key_prefix": "mk_live_A1b2C3",
  "secret": "mk_live_A1b2C3d4E5f6G7h8I9j0K1L2M3N4O5P6",
  "requests_per_minute": 60,
  "created_at": "2026-09-23T18:04:00Z"
}
```

**`secret` is returned exactly once, right here.** Every other response
from these endpoints - including calling this one again - only ever
returns `key_prefix`. Lose it, [rotate it](#rotate-a-key); there's no
"show it again."

<ErrorCode code="422" title="Key limit reached">
You already have the maximum number of active keys. Revoke one before
generating another.
</ErrorCode>

## List your keys

```json
{
  "items": [
    {
      "id": "01991e3f-...",
      "name": "my-app",
      "key_prefix": "mk_live_A1b2C3",
      "requests_per_minute": 60,
      "created_at": "2026-09-23T18:04:00Z",
      "last_used_at": "2026-09-23T18:10:22Z"
    }
  ],
  "total": 1
}
```

Only ever your live keys - revoking one deletes its row, so it simply
stops appearing here rather than lingering with a revoked flag set.

## Revoke a key

`DELETE /account/keys/{id}`. Deletes the key outright - permanent, not
reversible - and scoped to your own account: you can't revoke a key that
isn't yours, even if you guess its id correctly.

<ErrorCode code="401" title="Missing or invalid sign-in token">
The Firebase bearer token is missing, expired, or fails verification.
</ErrorCode>

<ErrorCode code="404" title="Key not found">
Either the key doesn't exist, or it belongs to a different account - both
look identical from the outside, on purpose.
</ErrorCode>

## Rotate a key

`POST /account/keys/{id}/rotate` - revokes the old key and generates its
replacement in one request, carrying over the name and rate limit. Same
result as calling revoke then create yourself, just one call instead of
two, and the new secret comes back the same way create's does.

```json
{
  "id": "01991e40-...",
  "name": "my-app",
  "key_prefix": "mk_live_Z9y8X7",
  "secret": "mk_live_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4",
  "requests_per_minute": 60,
  "created_at": "2026-09-23T19:22:00Z"
}
```

Doesn't count against your key limit - the old key stops being active in
the same request the new one starts, so rotating never changes how many
live keys you're holding.

<ErrorCode code="404" title="Key not found">
Same rule as revoke: doesn't exist, or isn't yours.
</ErrorCode>
