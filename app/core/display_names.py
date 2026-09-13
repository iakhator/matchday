"""Club names fit to put in front of a user.

Upstream `short_name` is usually right - "Borussia Dortmund" shortens to
"Dortmund", which is exactly what a table wants. A handful are nicknames
or abbreviations that read as wrong instead: Atlético Madrid arrives as
"Atleti", Barcelona as "Barça", and Athletic Club as plain "Athletic".

The synced value is never overwritten. Rewriting upstream data in place
makes this API's output impossible to reconcile against its source, and
the next sync would undo the edit anyway. Instead `display_name` resolves
through this map first and falls back to what upstream said.

Keyed by the club's full registered name rather than by id. Ids are
assigned per deployment, so an id here would be meaningless in anyone
else's database, and a reviewer reading a diff can see what a change
actually does. The tradeoff is that a club renamed upstream stops
matching - which fails safe, falling back to `short_name`, and
`unmatched_overrides()` surfaces it rather than leaving it to be noticed.
"""

from typing import Dict, Iterable, List, Optional

# name as synced -> what to show instead.
#
# Deliberately short. Every entry is a judgement someone has to maintain,
# and most of what upstream sends needs none - `HSV`, `M'gladbach` and
# `Celta` are how those clubs are actually referred to, so they are left
# alone. The bar is "would this look like a mistake in a table?", not
# "could this be more formal".
DISPLAY_NAME_OVERRIDES: Dict[str, str] = {
    # Nicknames upstream sends as the short name.
    "Club Atlético de Madrid": "Atlético Madrid",
    "FC Barcelona": "Barcelona",
    # "Athletic" alone reads as a fragment, and is ambiguous next to
    # Atlético in the same league.
    "Athletic Club": "Athletic Bilbao",
    # "Santander" is the city and the bank; the club is Racing.
    "Real Racing Club de Santander": "Racing Santander",
    # The city, not the club - Nottingham Forest is the club.
    "Nottingham Forest FC": "Nottingham Forest",
    # Upstream gives "Brighton Hove", which is neither the full name nor
    # what anyone says.
    "Brighton & Hove Albion FC": "Brighton",
    # short_name comes back identical to name for these, so it shortens
    # nothing.
    "1. FC Köln": "Köln",
    "Sevilla FC": "Sevilla",
}


def display_name(name: str, short_name: Optional[str] = None) -> str:
    """The name to show. Override, else upstream's short name, else the
    full name - so there is always something to render."""
    override = DISPLAY_NAME_OVERRIDES.get(name)
    if override:
        return override
    return short_name or name


def unmatched_overrides(known_names: Iterable[str]) -> List[str]:
    """Overrides that no longer match any club.

    An override keyed on a name that upstream has since changed silently
    stops applying. This makes that visible - call it with the names
    currently synced to find entries worth revisiting.
    """
    known = set(known_names)
    return sorted(name for name in DISPLAY_NAME_OVERRIDES if name not in known)
