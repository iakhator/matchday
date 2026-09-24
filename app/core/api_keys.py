"""Named API keys, parsed from configuration.

A single shared secret is enough when one known app calls the gateway. It
stops being enough as soon as there are two: you cannot tell them apart in
the logs, revoke one without breaking the other, or stop a runaway client
starving everyone else - including the sync jobs, which share this
process.

Keys are configured as `name:secret` or `name:secret:requests_per_minute`:

    GATEWAY_API_KEYS="predify:s3cret:120,analytics:other:30"

A bare secret with no name still works, so existing deployments keep
running after an upgrade. It just gets no name in the logs and the default
limit.

That covers admin/service keys an operator hand-configures, which is a
different thing from a self-serve customer generating their own - see
`generate_secret`/`find_db_key` below for that second, DB-backed tier.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.api_key import ApiKeyRecord
from app.utils.datetime_utils import utcnow

# What may appear before the first colon for the entry to count as named.
# Anything else means the whole string is a secret that happens to contain
# a colon, rather than a name - the reading that keeps old configs working.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

UNNAMED = "unnamed"

# Prefix on generated (self-serve) secrets, so one found in a log or a repo
# is identifiable at a glance and secret-scanners can match on it. Not
# applied to env-configured keys - those are whatever the operator chose.
SECRET_PREFIX = "mk_live_"


@dataclass(frozen=True)
class ApiKey:
    name: str
    secret: str
    requests_per_minute: int
    # What the rate limiter buckets this key by. Env-configured keys use
    # their name (one operator curates every name, so collisions can't
    # happen by accident). DB-issued keys use their own record id instead -
    # two different self-serve customers could otherwise both call a key
    # "predify" and end up sharing (and starving each other on) one bucket.
    rate_limit_key: str

    def __str__(self) -> str:
        """Safe for logs - deliberately never includes the secret."""
        return f"{self.name} ({self.requests_per_minute}/min)"


# Identity used when auth is switched off for local development. Having a
# real object here rather than None means callers never have to special
# case it.
ANONYMOUS = ApiKey(
    name="anonymous", secret="", requests_per_minute=0, rate_limit_key="anonymous"
)


def parse_api_keys(raw: str, default_rpm: int) -> List[ApiKey]:
    """Read the configured keys.

    Malformed entries are skipped rather than raising: one bad entry
    should not take the whole gateway down at startup, and the remaining
    keys are still valid. A skipped entry means that consumer gets a 401,
    which is a visible failure rather than a silent one.
    """
    keys: List[ApiKey] = []

    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue

        parts = entry.split(":")
        name, secret, rpm = UNNAMED, entry, default_rpm

        if len(parts) >= 2 and NAME_PATTERN.match(parts[0]):
            name = parts[0]
            secret = parts[1]
            if len(parts) >= 3:
                try:
                    rpm = int(parts[2])
                except ValueError:
                    # Keep the key, fall back to the default limit - a typo
                    # in a rate limit should not revoke someone's access.
                    rpm = default_rpm

        if not secret:
            continue
        keys.append(
            ApiKey(name=name, secret=secret, requests_per_minute=rpm, rate_limit_key=name)
        )

    return keys


def find_key(keys: List[ApiKey], presented: Optional[str]) -> Optional[ApiKey]:
    """The configured key matching what the caller presented, if any."""
    if not presented:
        return None
    for key in keys:
        if key.secret == presented:
            return key
    return None


def generate_secret() -> Tuple[str, str, str]:
    """A new self-serve secret. Returns (plaintext, prefix, hashed).

    The plaintext is returned once, here, and never stored - same contract
    as a GitHub PAT or a Stripe key. Only `hashed` goes in the DB; `prefix`
    is what the owner sees afterward to tell their keys apart without it
    being possible to reconstruct the secret from it.
    """
    plaintext = SECRET_PREFIX + secrets.token_urlsafe(32)
    prefix = plaintext[: len(SECRET_PREFIX) + 6]
    return plaintext, prefix, hash_secret(plaintext)


def hash_secret(plaintext: str) -> str:
    """SHA-256 is enough here - these are high-entropy generated secrets,
    not user-chosen passwords, so there's nothing for a slow hash
    (bcrypt/argon2 exist to blunt brute-forcing low-entropy input) to
    protect against that the secret's own entropy doesn't already."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


async def find_db_key(
    session: AsyncSession, presented: Optional[str]
) -> Optional[ApiKey]:
    """The self-serve key matching what the caller presented, if any.

    Only ever checked once the env-var path (`find_key`) has already
    missed - self-serve keys are a second tier, not a replacement for the
    admin/service keys configured via GATEWAY_API_KEYS.
    """
    if not presented:
        return None

    record = (
        await session.exec(
            select(ApiKeyRecord).where(
                ApiKeyRecord.hashed_secret == hash_secret(presented),
            )
        )
    ).first()
    if record is None:
        return None

    record.last_used_at = utcnow()
    session.add(record)
    await session.commit()

    return ApiKey(
        name=record.name,
        secret=presented,
        requests_per_minute=record.requests_per_minute,
        rate_limit_key=str(record.id),
    )


async def has_any_db_keys(session: AsyncSession) -> bool:
    """Whether at least one live self-serve key exists.

    Decides whether an empty GATEWAY_API_KEYS should fail closed - a
    gateway with no env keys configured but real self-serve customers must
    not refuse them just because the env var was never set.
    """
    result = await session.exec(select(ApiKeyRecord.id).limit(1))
    return result.first() is not None
