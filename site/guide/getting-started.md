# Getting started

Three steps: sign up, generate a key, make a request.

## 1. Sign up

Head to [the signup page](/account/signup) and sign in - no separate
password to remember, no email verification wait.

## 2. Generate a key

From [your dashboard](/account/dashboard), click **New key**, give it a
name (so you can tell it apart from any others you create later), and
copy the secret shown. **It's shown exactly once** - if you lose it,
revoke it and generate a new one, the same way you'd rotate any other API
credential.

Prefer the API directly over the dashboard? The same thing, one request:

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

console.log(key.secret); // mk_live_... - shown once, save it now
```

```python [Python]
import httpx

resp = httpx.post(
    "https://api.matchday.example/api/v1/account/keys",
    headers={"Authorization": f"Bearer {firebase_id_token}"},
    json={"name": "my-app"},
)
key = resp.json()
print(key["secret"])  # mk_live_... - shown once, save it now
```

:::

`$FIREBASE_ID_TOKEN` is what you get back from signing in through the
Firebase client SDK on the dashboard - this endpoint identifies *you*
(a human, proving who you are), separately from the API key it hands
back (which identifies *your app*, to every other endpoint below).

## 3. Make your first request

Every other endpoint uses the key you just generated, as `X-Gateway-Key` -
not the Firebase token from step 2, which only works for managing your
account.

::: code-group

```bash [curl]
curl https://api.matchday.example/api/v1/leagues \
  -H "X-Gateway-Key: mk_live_your_new_key"
```

```js [JavaScript]
const leagues = await fetch("https://api.matchday.example/api/v1/leagues", {
  headers: { "X-Gateway-Key": "mk_live_your_new_key" },
}).then((r) => r.json());
```

```python [Python]
leagues = httpx.get(
    "https://api.matchday.example/api/v1/leagues",
    headers={"X-Gateway-Key": "mk_live_your_new_key"},
).json()
```

:::

That's it - see the [endpoint reference](/reference/endpoints) for
everything else available, or
[authentication and rate limits](/guide/authentication) for what happens
when you go over your limit.
