# API versioning and stability

What this API offers is a contract: code written against `/api/v1` keeps
working. Which upstream provided the data, what the schema looks like
underneath, which connectors are registered - all of that is deliberately
invisible and free to change.

## Within a version, changes are additive only

Safe to expect, and shipped without notice:

- new endpoints
- new fields on an existing response
- new optional query parameters
- new enum values in a field documented as open-ended

**Parse responses tolerantly.** A new field appearing is not a breaking
change, and a client that rejects unknown fields will break on one.

These are breaking, and will never happen inside `/api/v1`:

- removing or renaming a field
- changing a field's type, or making an optional one required
- removing an endpoint, or changing what an existing one means
- changing the meaning of an identifier

## Breaking changes ship as a new version

A breaking change means a new path - `/api/v2` - served **alongside**
`/api/v1`, never replacing it in place. Nothing you have written stops
working the day it launches.

## Deprecation

Anything being retired carries headers before it goes, so this is
detectable in code rather than only in a changelog:

```http
Deprecation: true
Sunset: Fri, 01 Jan 2027 00:00:00 GMT
Link: </api/v1/replacement>; rel="successor-version"
```

`Sunset` is [RFC 8594](https://www.rfc-editor.org/rfc/rfc8594) and parses
with any standard HTTP-date helper. Alert on `Deprecation` in your own
logging and you will hear about a retirement without reading anything.

**Minimum notice: 6 months** between the first deprecated response and the
endpoint being withdrawn. A deprecated endpoint keeps working normally for
the whole of that period - "going away" is not "already gone".

Every response carries `X-API-Version`, so a captured response can be
traced to the contract that produced it without reconstructing the request.

## What is not covered

The upstream data itself. If a provider corrects a score, renames a club or
withdraws a competition, that flows through - this policy governs the shape
of the API, not the accuracy or availability of what a third party
publishes. See [How fresh is the data?](/guide/data-freshness) for what
can be relied on there.
