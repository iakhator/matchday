"""Measure how quickly this gateway reflects real-world match events.

"How fresh is your data?" is the first question anyone evaluating a
football data API asks, and the only honest answer is a measured one.
This probe watches the gateway's own API across a matchday and records
when each fixture's status and score actually change, relative to that
fixture's kickoff.

It deliberately does NOT poll the upstream provider to compare against.
The sampler would be competing with the gateway's own sync jobs for the
same rate limit - inducing 429s in the system under test and then
measuring the degradation it caused. Polling only the local API costs
nothing, and shows exactly what a consumer sees, which is the number that
matters.

It also deliberately knows nothing about any particular consumer. Timings
are relative to each fixture's own kickoff, so the result is absolute and
publishable rather than a statement about one app's sync cadence.

What it can answer:
  - does an in-play status ever appear (i.e. does the live job do
    anything), or do results only land at full time?
  - how long after kickoff does the first status change show up?
  - how long after full time does the score settle?

What it cannot answer: whether the scores are *correct*. That needs a
second source; see the fixture-level comparison in docs/.

Read-only. HTTP GETs against the gateway, writes one log file, makes no
upstream calls and touches no database.

    python scripts/latency_probe.py                     # until 22:00 UTC
    python scripts/latency_probe.py --until 23:30 --interval 30
    python scripts/latency_probe.py --report            # summarise a past run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

GATEWAY = os.environ.get("GATEWAY_URL", "http://localhost:8010")
OUT = Path(os.environ.get("LATENCY_OUT", "/tmp/matchday_latency.jsonl"))

# Discovered from the gateway rather than hardcoded.
#
# This used to hold football-data.org's own competition ids (2021, 2014,
# 2002). When the gateway moved to ids of its own, every request here
# started returning 404 - and the probe carried on regardless, logging
# 2,463 errors over seven hours and recording nothing. It broke exactly
# the way any consumer holding a provider's ids would have, which is the
# argument for the gateway owning its ids in the first place.
COMPETITIONS: list[int] = []

# Roughly 90 minutes plus half time and stoppage. Only used to label how
# far past a plausible full time a result arrived - never to decide that a
# match has ended.
TYPICAL_MATCH_MINUTES = 115


def now() -> datetime:
    return datetime.now(timezone.utc)


def log(msg: str) -> None:
    print(f"[{now():%H:%M:%S}] {msg}", flush=True)


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fetch(competition: int) -> list[dict]:
    url = f"{GATEWAY}/api/v1/leagues/{competition}/fixtures"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    key = os.environ.get("GATEWAY_API_KEY")
    if key:
        req.add_header("X-Gateway-Key", key)
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if isinstance(payload, list):
        return payload
    return payload.get("items", payload.get("data", []))


def discover_competitions() -> list[int]:
    """Ask the gateway which competitions it has."""
    req = urllib.request.Request(
        f"{GATEWAY}/api/v1/leagues", headers={"Accept": "application/json"}
    )
    key = os.environ.get("GATEWAY_API_KEY")
    if key:
        req.add_header("X-Gateway-Key", key)
    with urllib.request.urlopen(req, timeout=30) as response:
        payload = json.load(response)
    rows = payload if isinstance(payload, list) else payload.get("items", [])
    return [int(row["id"]) for row in rows]


def live_window(fixture: dict, at: datetime) -> bool:
    """Is this fixture plausibly in progress right now?

    Wide on purpose - the point is to watch a fixture through its whole
    window including a late finish, not to guess when it ended.
    """
    kickoff = parse_ts(fixture["kickoff_at"])
    return kickoff - timedelta(minutes=15) <= at <= kickoff + timedelta(minutes=240)


def state_of(fixture: dict) -> dict:
    return {
        "status": fixture.get("status"),
        "home_score": fixture.get("home_score"),
        "away_score": fixture.get("away_score"),
    }


def label(fixture: dict) -> str:
    return (
        f"{fixture['home_team'].get('short_name') or fixture['home_team']['name']}"
        f" v {fixture['away_team'].get('short_name') or fixture['away_team']['name']}"
    )


def record(event: dict) -> None:
    with OUT.open("a") as handle:
        handle.write(json.dumps(event) + "\n")


def watch(until: datetime, interval: int) -> int:
    competitions = COMPETITIONS or discover_competitions()
    if not competitions:
        log("gateway reports no competitions - nothing to watch")
        return 1

    log(f"watching {len(competitions)} competitions every {interval}s")
    log(f"until {until:%H:%M} UTC, writing to {OUT}")

    seen: dict[int, dict] = {}
    ticks = 0
    transitions = 0
    consecutive_errors = 0

    # Roughly ten minutes of every fetch failing at the default interval.
    max_consecutive_errors = max(20, int(600 / max(interval, 1)))

    while now() < until:
        ticks += 1
        at = now()
        tracked = 0

        for competition in competitions:
            try:
                fixtures = fetch(competition)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                # A blip must not end a run that can only be done on a
                # matchday - note it and carry on. But a *sustained* failure
                # is not a blip, and a probe that keeps politely retrying a
                # dead endpoint for hours produces a log file that looks
                # like data and contains none. Give up once it is clearly
                # not transient.
                consecutive_errors += 1
                log(f"competition {competition} fetch failed: {exc}")
                record(
                    {
                        "at": at.isoformat(),
                        "event": "fetch_error",
                        "competition": competition,
                        "detail": str(exc)[:200],
                    }
                )
                if consecutive_errors >= max_consecutive_errors:
                    log(
                        f"aborting: {consecutive_errors} consecutive fetch "
                        f"failures. Has the gateway moved, or its ids changed?"
                    )
                    report()
                    return 1
                continue

            consecutive_errors = 0

            for fixture in fixtures:
                if not fixture.get("kickoff_at") or not live_window(fixture, at):
                    continue
                tracked += 1

                state = state_of(fixture)
                previous = seen.get(fixture["id"])
                if previous == state:
                    continue
                seen[fixture["id"]] = state
                transitions += 1

                kickoff = parse_ts(fixture["kickoff_at"])
                minutes_in = (at - kickoff).total_seconds() / 60
                record(
                    {
                        "at": at.isoformat(),
                        "event": "transition",
                        "fixture_id": fixture["id"],
                        "fixture": label(fixture),
                        "competition": competition,
                        "kickoff_at": fixture["kickoff_at"],
                        "minutes_after_kickoff": round(minutes_in, 1),
                        "from": previous,
                        "to": state,
                    }
                )
                arrow = "first seen" if previous is None else f"{previous['status']} ->"
                log(
                    f"{label(fixture)[:34]:34} {arrow:>14} {state['status']:<12} "
                    f"{state['home_score']}-{state['away_score']}  "
                    f"({minutes_in:+.0f} min from KO)"
                )

        if ticks % 20 == 0:
            log(
                f"tick {ticks}, {tracked} fixture(s) in window, {transitions} transitions"
            )
        time.sleep(interval)

    log(f"finished after {ticks} ticks, {transitions} transitions -> {OUT}")
    report()
    return 0


def report() -> int:
    """Summarise a run. Safe to call on a partial log."""
    if not OUT.exists():
        log(f"no log at {OUT}")
        return 1

    events = [json.loads(line) for line in OUT.read_text().splitlines() if line.strip()]
    transitions = [e for e in events if e.get("event") == "transition"]
    errors = [e for e in events if e.get("event") == "fetch_error"]

    if not transitions:
        log("no transitions recorded")
        return 1

    by_fixture: dict[str, list[dict]] = {}
    for event in transitions:
        by_fixture.setdefault(event["fixture"], []).append(event)

    print("\n" + "=" * 72)
    print("GATEWAY REPORTING LATENCY")
    print("=" * 72)
    print(f"fixtures observed : {len(by_fixture)}")
    print(f"transitions       : {len(transitions)}")
    print(f"fetch errors      : {len(errors)}")

    in_play_seen = sorted(
        {
            e["to"]["status"]
            for e in transitions
            if e["to"]["status"] not in ("scheduled", "finished", "timed", "postponed")
        }
    )
    seen_label = in_play_seen or "NONE - results only at full time"
    print(f"non-terminal statuses seen: {seen_label}")

    print("\nper fixture:")
    for fixture, events_for in sorted(by_fixture.items()):
        print(f"\n  {fixture}")
        for event in events_for:
            state = event["to"]
            print(
                f"    {event['minutes_after_kickoff']:+7.0f} min  "
                f"{state['status']:<12} {state['home_score']}-{state['away_score']}"
            )
        finished = [e for e in events_for if e["to"]["status"] == "finished"]
        if finished:
            delay = finished[0]["minutes_after_kickoff"] - TYPICAL_MATCH_MINUTES
            print(f"    -> result visible ~{delay:+.0f} min vs a typical full time")

    print("\n" + "=" * 72)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--until", default="22:00", help="stop time, UTC HH:MM")
    parser.add_argument("--interval", type=int, default=30, help="seconds between polls")
    parser.add_argument("--report", action="store_true", help="summarise an existing log")
    args = parser.parse_args()

    if args.report:
        return report()

    hour, minute = (int(part) for part in args.until.split(":"))
    stop = now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if stop <= now():
        stop += timedelta(days=1)

    try:
        return watch(stop, args.interval)
    except KeyboardInterrupt:
        log("interrupted - summarising what was captured")
        return report()


if __name__ == "__main__":
    sys.exit(main())
