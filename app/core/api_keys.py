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
"""

import re
from dataclasses import dataclass
from typing import List, Optional

# What may appear before the first colon for the entry to count as named.
# Anything else means the whole string is a secret that happens to contain
# a colon, rather than a name - the reading that keeps old configs working.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

UNNAMED = "unnamed"


@dataclass(frozen=True)
class ApiKey:
    name: str
    secret: str
    requests_per_minute: int

    def __str__(self) -> str:
        """Safe for logs - deliberately never includes the secret."""
        return f"{self.name} ({self.requests_per_minute}/min)"


# Identity used when auth is switched off for local development. Having a
# real object here rather than None means callers never have to special
# case it.
ANONYMOUS = ApiKey(name="anonymous", secret="", requests_per_minute=0)


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
        keys.append(ApiKey(name=name, secret=secret, requests_per_minute=rpm))

    return keys


def find_key(keys: List[ApiKey], presented: Optional[str]) -> Optional[ApiKey]:
    """The configured key matching what the caller presented, if any."""
    if not presented:
        return None
    for key in keys:
        if key.secret == presented:
            return key
    return None
