# How fresh is the data?

Measured, not asserted. `scripts/latency_probe.py` watches the gateway's
own API across a matchday and records when each fixture's status and score
actually change, relative to that fixture's kickoff. Re-runnable, so the
number below can be checked rather than trusted.

Measured on 12 September 2026, free tier, Premier League + La Liga +
Bundesliga:

| | |
| --- | --- |
| Kickoff -> status becomes `live` | **7-10 minutes** (10 fixtures) |
| Goal scored -> new score visible | **7-8 minutes** (5 fixtures) |

The two agree, which is the useful part: both point at a roughly
seven-minute delay between something happening and the gateway being able
to see it.

**That delay is upstream, not here.** The live-score job polls every 60
seconds, so the gateway can add at most about a minute of its own.
football-data.org's free tier advertises *delayed scores*, and this is
what that means in practice.

Worth knowing before building on it: a seven-minute lag is fine for
standings, schedules and post-match results. It is not fine for anything
that needs to react as a match unfolds - live odds, in-play notifications,
a second-screen experience. Those need a paid tier or a different
upstream, and no amount of polling fixes that from this side.

Sample sizes are small and from a single matchday, so treat the figures as
an order of magnitude rather than an SLA.
