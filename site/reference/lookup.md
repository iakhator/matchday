# Lookup

<MethodBadge method="GET" path="/api/v1/lookup/{entity_type}" />
<MethodBadge method="GET" path="/api/v1/lookup/{entity_type}/{internal_id}/aliases" />

<EndpointMeta :stats="[
  { label: 'Auth', value: 'X-Gateway-Key' },
]" />

Translate another provider's ids into this gateway's own. Exists so a
consumer already keyed to a different provider (api-sports.io, say) can
adopt gateway ids gradually - ask which gateway row is api-sports' team
57, store that, and migrate at its own pace, instead of re-keying its
whole history in one step.

## Query parameters (`/lookup/{entity_type}`)

<ParamCard name="source" type="string" :required="true">
Which provider the ids belong to, e.g. <code>football_data_org</code> or
<code>api_sports</code>.
</ParamCard>

<ParamCard name="external_id" type="string" :required="true">
Provider id, or several separated by commas (up to 500 per request -
batched deliberately, since matching a season of fixtures one at a time
would be hundreds of round trips against a rate-limited API).
</ParamCard>

`entity_type` is one of `league`, `team`, `fixture`.

## Request

::: code-group

```bash [curl]
curl "https://api.matchday.example/api/v1/lookup/team?source=football_data_org&external_id=57,61" \
  -H "X-Gateway-Key: $MATCHDAY_KEY"
```

```js [JavaScript]
const params = new URLSearchParams({
  source: "football_data_org",
  external_id: "57,61",
});
const mapped = await fetch(
  `https://api.matchday.example/api/v1/lookup/team?${params}`,
  { headers: { "X-Gateway-Key": process.env.MATCHDAY_KEY } },
).then((r) => r.json());
```

```python [Python]
mapped = httpx.get(
    "https://api.matchday.example/api/v1/lookup/team",
    params={"source": "football_data_org", "external_id": "57,61"},
    headers={"X-Gateway-Key": os.environ["MATCHDAY_KEY"]},
).json()
```

:::

## Response

**`/lookup/{entity_type}`**

```json
{
  "entity_type": "team",
  "source": "football_data_org",
  "resolved": { "57": 10000001, "61": 10000002 },
  "unresolved": []
}
```

**Unresolved ids are reported explicitly, not silently dropped.**
`resolved` maps only what it recognizes; anything it doesn't ends up in
`unresolved`, in the order you sent it, so a migration can see exactly
which of its entities this gateway doesn't know rather than discovering
holes later.

**`/lookup/{entity_type}/{internal_id}/aliases`** - the reverse: every
provider id known for one gateway row.

```json
{
  "entity_type": "team",
  "internal_id": 10000001,
  "aliases": [
    { "source": "football_data_org", "external_id": "57", "verified": true },
    { "source": "api_sports", "external_id": "42", "verified": true }
  ]
}
```

`verified: false` means the mapping was inferred (matching club names
across providers) rather than established from a provider's own
identifiers - treat it as a suggestion, not a fact.

<ErrorCode code="400" title="Unknown entity_type or empty external_id list">
Names the valid entity types rather than returning an empty result that
looks like "none of your ids are known".
</ErrorCode>

<ErrorCode code="404" title="No mappings found (aliases endpoint)">
The internal id doesn't exist, or has no known provider mappings yet.
</ErrorCode>
