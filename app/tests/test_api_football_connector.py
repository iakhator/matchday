"""Parsing api-football's payloads.

Weighted toward what it sends that does not mean what it looks like.
"""

import pytest

from app.connectors.api_football import ApiFootballConnector


class _Conn(ApiFootballConnector):
    """Bypasses __init__ so parsing can be tested without a key or a
    network call."""

    def __init__(self, payload):
        self._payload = payload

    async def _get(self, path, params=None):
        return self._payload


pytestmark = pytest.mark.asyncio


def _event(detail, type_="Goal", minute=10, team=192, player="A. Player"):
    return {
        "time": {"elapsed": minute},
        "team": {"id": team, "name": "Club"},
        "player": {"name": player},
        "assist": {"name": None},
        "type": type_,
        "detail": detail,
    }


class TestGoalEvents:
    async def test_a_normal_goal_is_a_goal(self):
        [goal] = await _Conn({"response": [_event("Normal Goal")]}).fetch_goal_events("1")
        assert goal.kind == "goal"

    async def test_own_goals_and_penalties_are_distinguished(self):
        events = await _Conn(
            {"response": [_event("Own Goal", minute=7), _event("Penalty", minute=8)]}
        ).fetch_goal_events("1")
        assert [e.kind for e in events] == ["own_goal", "penalty"]

    async def test_a_missed_penalty_is_not_a_goal(self):
        """api-football files this under type "Goal" with detail "Missed
        Penalty". Counting it turned a real 1-1 into a derived 2-1."""
        assert await _Conn(
            {"response": [_event("Missed Penalty")]}
        ).fetch_goal_events("1") == []

    async def test_an_unrecognised_detail_is_discarded_not_assumed(self):
        """The bug was the default. Anything not on the allow-list should
        cost us that event, never corrupt a scoreline."""
        assert await _Conn(
            {"response": [_event("Something New Upstream")]}
        ).fetch_goal_events("1") == []

    async def test_cards_and_subs_are_ignored(self):
        payload = {"response": [_event("Yellow Card", type_="Card"),
                                _event("Substitution 1", type_="subst")]}
        assert await _Conn(payload).fetch_goal_events("1") == []

    async def test_assist_is_carried_when_present(self):
        event = _event("Normal Goal")
        event["assist"] = {"name": "E. Skhiri"}
        [goal] = await _Conn({"response": [event]}).fetch_goal_events("1")
        assert goal.assist_player_name == "E. Skhiri"


class TestOdds:
    async def test_every_bookmaker_is_kept(self):
        """They arrive in one response, so several cost no extra requests
        and let a consumer see a spread rather than one house's view."""
        payload = {"response": [{"bookmakers": [
            {"name": "A", "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.60"}, {"value": "Draw", "odd": "2.80"},
                {"value": "Away", "odd": "3.00"}]}]},
            {"name": "B", "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "2.50"}]}]},
        ]}]}
        rows = await _Conn(payload).fetch_odds("1")
        assert [r.bookmaker for r in rows] == ["A", "B"]
        assert rows[0].home == 2.60 and rows[0].draw == 2.80

    async def test_a_malformed_price_costs_that_price_only(self):
        payload = {"response": [{"bookmakers": [
            {"name": "A", "bets": [{"name": "Match Winner", "values": [
                {"value": "Home", "odd": "not-a-number"},
                {"value": "Draw", "odd": "2.80"}]}]}]}]}
        [row] = await _Conn(payload).fetch_odds("1")
        assert row.home is None
        assert row.draw == 2.80

    async def test_other_bet_types_are_ignored(self):
        payload = {"response": [{"bookmakers": [
            {"name": "A", "bets": [{"name": "Both Teams Score", "values": []}]}]}]}
        assert await _Conn(payload).fetch_odds("1") == []

    async def test_a_finished_fixture_has_no_odds(self):
        """Verified upstream: odds exist only before kickoff, and there is
        no backfilling them."""
        assert await _Conn({"response": []}).fetch_odds("1") == []
