"""The consumer-facing half of the id mapping.

These endpoints exist so someone already keyed to another provider can
adopt gateway ids gradually. The cases worth protecting are the ones that
make a migration silently wrong: an unknown id being indistinguishable
from a known one, and a typo'd entity type looking like "none of your ids
are recognised".
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import EntityType
from app.services.id_mapper import IdMapper

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client(test_session):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def mapped(test_session):
    mapper = IdMapper(test_session)
    await mapper.link(EntityType.TEAM, "football_data_org", "57", 10_000_001)
    await mapper.link(EntityType.TEAM, "api_sports", "42", 10_000_001)
    await mapper.link(EntityType.TEAM, "football_data_org", "61", 10_000_002)
    await test_session.commit()


class TestLookup:
    async def test_resolves_a_known_ref(self, client, mapped):
        r = await client.get(
            "/api/v1/lookup/team",
            params={"source": "football_data_org", "external_id": "57"},
        )
        assert r.status_code == 200
        assert r.json()["resolved"] == {"57": 10_000_001}
        assert r.json()["unresolved"] == []

    async def test_unknown_refs_are_reported_not_dropped(self, client, mapped):
        """The failure that matters: a consumer must be able to see which
        of its entities this gateway does not recognise. Omitting them
        silently is how a migration ends up with holes."""
        r = await client.get(
            "/api/v1/lookup/team",
            params={"source": "football_data_org", "external_id": "57,999"},
        )
        assert r.json()["resolved"] == {"57": 10_000_001}
        assert r.json()["unresolved"] == ["999"]

    async def test_batches_in_one_request(self, client, mapped):
        r = await client.get(
            "/api/v1/lookup/team",
            params={"source": "football_data_org", "external_id": "57,61"},
        )
        assert r.json()["resolved"] == {"57": 10_000_001, "61": 10_000_002}

    async def test_different_sources_resolve_to_the_same_row(self, client, mapped):
        """Two providers, two ids, one club - the reason the mapping exists."""
        a = await client.get(
            "/api/v1/lookup/team",
            params={"source": "football_data_org", "external_id": "57"},
        )
        b = await client.get(
            "/api/v1/lookup/team", params={"source": "api_sports", "external_id": "42"}
        )
        assert a.json()["resolved"]["57"] == b.json()["resolved"]["42"]

    async def test_unknown_source_resolves_nothing(self, client, mapped):
        r = await client.get(
            "/api/v1/lookup/team",
            params={"source": "nobody", "external_id": "57"},
        )
        assert r.json()["resolved"] == {}
        assert r.json()["unresolved"] == ["57"]

    async def test_bad_entity_type_is_rejected_not_answered_emptily(self, client):
        """A typo must not look like a valid question with no matches."""
        r = await client.get(
            "/api/v1/lookup/player",
            params={"source": "football_data_org", "external_id": "57"},
        )
        assert r.status_code == 400
        assert "team" in r.json()["detail"]

    async def test_empty_ref_list_is_rejected(self, client):
        r = await client.get(
            "/api/v1/lookup/team",
            params={"source": "football_data_org", "external_id": ",,,"},
        )
        assert r.status_code == 400

    async def test_oversized_batch_is_rejected(self, client):
        r = await client.get(
            "/api/v1/lookup/team",
            params={
                "source": "football_data_org",
                "external_id": ",".join(str(i) for i in range(600)),
            },
        )
        assert r.status_code == 400
        assert "500" in r.json()["detail"]


class TestAliases:
    async def test_lists_every_known_ref_for_a_row(self, client, mapped):
        r = await client.get("/api/v1/lookup/team/10000001/aliases")
        assert r.status_code == 200
        assert {(a["source"], a["external_id"]) for a in r.json()["aliases"]} == {
            ("football_data_org", "57"),
            ("api_sports", "42"),
        }

    async def test_unmapped_row_is_404_not_an_empty_list(self, client, mapped):
        """An empty list would read as "this row has no aliases", which is a
        different claim from "this row does not exist here"."""
        r = await client.get("/api/v1/lookup/team/99999999/aliases")
        assert r.status_code == 404
