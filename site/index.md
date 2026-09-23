---
layout: home

hero:
  name: Matchday
  text: Football data, one stable API.
  tagline: Leagues, fixtures, live scores, standings, goal events and odds - synced continuously, served through a contract that doesn't break under you.
  actions:
    - theme: brand
      text: Get an API key
      link: /account/signup
    - theme: alt
      text: Getting started
      link: /guide/getting-started
    - theme: alt
      text: API reference
      link: /reference/

features:
  - title: One stable contract
    details: Identifiers belong to this API, not to whichever upstream source the data came from. Changes within /api/v1 are additive only - see the versioning policy.
  - title: Continuously synced
    details: Fixtures and scores refresh on a 15-minute cycle, with a 60-second fast path while a match is live. Measured latency, not a promise - see How fresh is the data?
  - title: Simple auth, real limits
    details: One header, X-Gateway-Key. Over your limit returns 429 with a Retry-After header telling you exactly how long to wait.
---
