# Data licensing and attribution

Matchday does not own any of the data it serves - it syncs it from an
upstream provider. That provider's terms travel with the data, and they
shape how this project can be deployed. Read this before pointing anything
at a public instance.

**Attribution is required.** Any app or site built on this gateway must
display, in a visible place:

> Data provided by football-data.org

**Self-host with your own key.** Each deployment registers its own
football-data.org key and syncs its own copy. There is deliberately no
public hosted instance of this gateway, because re-serving a provider's
data to third parties is a different thing from syncing it into your own
app, and permission for the former has not been granted.

**The cached data is not yours to keep.** football-data.org's terms state
that after a subscription ends, the customer may no longer reference the
football data obtained through their API - fixtures, results, tables,
squad data, top scorers - on their own site or service. This gateway's
database is a *cache*, not an archive. Losing access upstream means the
cache has to go too.

**Crests and logos are not covered.** `Team.logo` and `League.logo` hold
URLs to club crests. Those are trademarks belonging to the clubs, not to
the data provider, and football-data.org is explicit that you must arrange
proof of intellectual property yourself before displaying them. Treat
those fields as references, and clear them independently before putting a
crest in front of users.

**If you want to run a public instance,** ask first - the provider invites
contact at `daniel@football-data.org`, and a written answer is the only
thing that makes it safe. This note records what the published
documentation says; it is not legal advice, and the authoritative terms
are whatever the provider states directly.

Free-tier limits worth knowing before you build on them: 10 requests per
minute, 12 competitions, delayed scores, no player-level detail (lineups,
cards, substitutions), and historical data restricted to the current
season.
