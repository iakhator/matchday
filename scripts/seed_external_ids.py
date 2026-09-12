"""Seed the id map from a provider that only gives us names.

Three steps, with a file in between so the review is an artefact rather
than a decision someone made once in a terminal:

    propose   match names against known teams, write unverified mappings
              and emit a review file
    review    open the file, check each row, set approved=true
    approve   import the reviewed file

Input for `propose` is JSON - a list of the other provider's teams:

    [{"external_id": "42", "name": "Brighton & Hove Albion"}, ...]

Usage:

    python scripts/seed_external_ids.py propose \\
        --source api_sports --input their_teams.json --out review.json

    # edit review.json, setting approved=true on rows you have checked

    python scripts/seed_external_ids.py approve --input review.json
    python scripts/seed_external_ids.py pending
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import async_session  # noqa: E402
from app.services.external_id_seeder import (  # noqa: E402
    ExternalIdSeeder,
    to_review_document,
)


async def cmd_propose(args) -> int:
    entries = json.loads(Path(args.input).read_text())
    if not isinstance(entries, list):
        print("Input must be a JSON list of {external_id, name} objects")
        return 1

    async with async_session() as session:
        seeder = ExternalIdSeeder(session)
        proposals = await seeder.propose_team_mappings(args.source, entries)

    document = to_review_document(args.source, proposals)
    Path(args.out).write_text(json.dumps(document, indent=2) + "\n")

    summary = document["summary"]
    print(f"  {len(entries)} entries from '{args.source}'")
    print(f"  {summary['confirm']:>4}  matched, awaiting confirmation")
    print(f"  {summary['needs_choice']:>4}  ambiguous - more than one candidate")
    print(f"  {summary['needs_manual_match']:>4}  no match, need a manual id")
    print(f"\n  review file: {args.out}")
    print("  Nothing is trusted until you approve it - the sync path")
    print("  ignores unverified mappings entirely.")
    return 0


async def cmd_approve(args) -> int:
    document = json.loads(Path(args.input).read_text())
    source = document["source"]

    approved_refs = []
    unmatched_but_approved = []
    for section in ("confirm", "needs_choice", "needs_manual_match"):
        for row in document.get(section, []):
            if not row.get("approved"):
                continue
            if row.get("matched_id") is None:
                unmatched_but_approved.append(row["external_name"])
                continue
            approved_refs.append(row["external_id"])

    if unmatched_but_approved:
        # Approving a row without choosing a target is almost certainly a
        # mistake, and silently skipping it would leave the reviewer
        # thinking it was handled.
        print("  Approved but no matched_id set - fill these in or unapprove:")
        for name in unmatched_but_approved:
            print(f"    - {name}")
        return 1

    async with async_session() as session:
        seeder = ExternalIdSeeder(session)
        count = await seeder.approve(source, approved_refs)

    print(f"  approved {count} mappings for '{source}'")
    return 0


async def cmd_pending(args) -> int:
    async with async_session() as session:
        rows = await ExternalIdSeeder(session).pending(args.source)

    if not rows:
        print("  no mappings awaiting review")
        return 0

    print(f"  {len(rows)} mapping(s) awaiting review:")
    for row in rows:
        print(f"    {row.source:<20} {row.external_id:<12} -> {row.internal_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("propose", help="match names and emit a review file")
    p.add_argument("--source", required=True, help="name of the other provider")
    p.add_argument("--input", required=True, help="JSON list of their teams")
    p.add_argument("--out", default="external_id_review.json")
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("approve", help="import a reviewed file")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("pending", help="list mappings awaiting review")
    p.add_argument("--source", default=None)
    p.set_defaults(func=cmd_pending)

    args = parser.parse_args()
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
