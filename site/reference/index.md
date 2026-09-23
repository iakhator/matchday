# Reference

All endpoints are under `/api/v1`. Every response carries `X-API-Version`.
Within `/api/v1`, changes are additive only - see
[API versioning](/guide/versioning) before writing a client that rejects
unknown fields.

Data endpoints (leagues, fixtures, standings, and so on) are gated by
`X-Gateway-Key` - see [Authentication and rate limits](/guide/authentication).
The [Account](/reference/account) endpoints are the one exception: they're
gated by a Firebase sign-in token instead, since they manage the keys
themselves rather than using one.

- [Leagues](/reference/leagues)
- [Teams](/reference/teams)
- [Fixtures](/reference/fixtures)
- [Standings](/reference/standings)
- [Season scorers](/reference/season-scorers)
- [Advanced match stats](/reference/advanced-stats)
- [Goal events](/reference/goals)
- [Odds](/reference/odds)
- [Lookup](/reference/lookup)
- [Account](/reference/account)
- [Health](/reference/health)
