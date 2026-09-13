"""Curated club names.

The point is that a table never shows "Atleti" or "Barça", without
rewriting what upstream sent. The risks worth covering are the two ends:
an override that does not apply, and an override applied where none was
wanted.
"""

import pytest

from app.connectors.base import NormalizedTeam
from app.core.display_names import (
    DISPLAY_NAME_OVERRIDES,
    display_name,
    unmatched_overrides,
)
from app.services.sync_service import SyncService
from app.tests.test_sync_service import FakeConnector, make_league_normalized


class TestResolution:
    def test_override_wins_over_upstream_short_name(self):
        assert display_name("FC Barcelona", "Barça") == "Barcelona"

    def test_short_name_is_used_when_there_is_no_override(self):
        """Most of what upstream sends is already right and must be left
        alone - "Borussia Dortmund" -> "Dortmund" needs no help."""
        assert display_name("Borussia Dortmund", "Dortmund") == "Dortmund"

    def test_falls_back_to_the_full_name(self):
        """There is always something to render, even for a club upstream
        gave no short name for."""
        assert display_name("Some New Club", None) == "Some New Club"

    def test_an_empty_short_name_is_not_treated_as_a_name(self):
        assert display_name("Some New Club", "") == "Some New Club"


class TestOverrideSet:
    def test_no_override_is_a_no_op(self):
        """An entry mapping a name to itself is dead weight - it reads as a
        decision while changing nothing."""
        assert [k for k, v in DISPLAY_NAME_OVERRIDES.items() if k == v] == []

    def test_no_override_is_empty(self):
        assert all(v.strip() for v in DISPLAY_NAME_OVERRIDES.values())

    def test_overrides_that_no_longer_match_are_reported(self):
        """A club renamed upstream makes its override silently stop
        applying. Failing safe is right; failing silently is not."""
        stale = unmatched_overrides(["FC Barcelona"])
        assert "FC Barcelona" not in stale
        assert "Club Atlético de Madrid" in stale

    def test_nothing_is_reported_when_every_override_matches(self):
        assert unmatched_overrides(DISPLAY_NAME_OVERRIDES.keys()) == []


@pytest.mark.asyncio
class TestPersistedOnWrite:
    """display_name is stored, not computed at serialisation.

    Stored so it can be searched, sorted and filtered on - a computed
    property cannot appear in a WHERE clause - and so anything else reading
    this database sees the same name the API serves.
    """

    async def test_sync_resolves_and_stores_the_override(
        self, test_session, monkeypatch
    ):
        connector = FakeConnector(
            "football_data_org",
            league=make_league_normalized(),
            teams=[
                NormalizedTeam(
                    external_ref="81", name="FC Barcelona", short_name="Barça"
                ),
                NormalizedTeam(
                    external_ref="4", name="Borussia Dortmund", short_name="Dortmund"
                ),
            ],
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        teams = {t.name: t for t in await service.sync_teams(league, 2026)}

        assert teams["FC Barcelona"].display_name == "Barcelona"
        # Upstream's value is kept, so the row still reconciles to source.
        assert teams["FC Barcelona"].short_name == "Barça"
        # Everything without an override just carries upstream's short name.
        assert teams["Borussia Dortmund"].display_name == "Dortmund"

    async def test_editing_the_map_takes_effect_on_the_next_sync(
        self, test_session, monkeypatch
    ):
        """Stored values would otherwise go stale when an override changes.
        sync_teams re-resolves existing rows, so a map edit self-heals
        within a sync cycle instead of needing a backfill."""
        team = NormalizedTeam(external_ref="99", name="Example FC", short_name="Ex")
        connector = FakeConnector(
            "football_data_org", league=make_league_normalized(), teams=[team]
        )
        monkeypatch.setattr(
            "app.services.sync_service.get_connectors", lambda: [connector]
        )
        service = SyncService(test_session)
        league = await service.sync_league("PL")
        [synced] = await service.sync_teams(league, 2026)
        assert synced.display_name == "Ex"

        monkeypatch.setitem(DISPLAY_NAME_OVERRIDES, "Example FC", "Example United")
        [resynced] = await service.sync_teams(league, 2026)
        assert resynced.display_name == "Example United"
