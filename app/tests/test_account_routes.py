"""Self-serve API key management - the account dashboard's backend.

Two things matter here beyond ordinary CRUD: a plaintext secret must never
be returned anywhere except the create response, and one account must
never be able to see or revoke another's keys even by guessing an id.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.user_auth import require_firebase_user
from app.db.database import get_session
from app.db.models.user import User

pytestmark = pytest.mark.asyncio


async def _make_user(test_session, email: str = "owner@example.com") -> User:
    user = User(firebase_uid=f"uid-{email}", email=email)
    test_session.add(user)
    await test_session.commit()
    await test_session.refresh(user)
    return user


@pytest.fixture
async def owner(test_session) -> User:
    return await _make_user(test_session)


@pytest.fixture
async def client(test_session, owner):
    """Bypasses real Firebase verification - require_firebase_user is
    overridden to return `owner` directly. The token-verification chain
    itself is covered separately, in TestRequireFirebaseUser below."""
    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_session] = lambda: test_session
    app.dependency_overrides[require_firebase_user] = lambda: owner

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestCreateKey:
    async def test_returns_the_plaintext_secret_once(self, client):
        r = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "my-app"
        assert body["secret"].startswith("mk_live_")
        assert body["key_prefix"] == body["secret"][: len(body["key_prefix"])]

    async def test_uses_the_self_serve_default_rate_limit(self, client):
        r = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        assert (
            r.json()["requests_per_minute"] == settings.SELF_SERVE_RATE_LIMIT_PER_MINUTE
        )

    async def test_the_generated_key_actually_authenticates(self, client, test_session):
        """The point of the whole feature: what create_key hands back must
        be usable as a real X-Gateway-Key, not just a database row."""
        from app.core.api_keys import find_db_key

        r = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        plaintext = r.json()["secret"]

        matched = await find_db_key(test_session, plaintext)
        assert matched is not None
        assert matched.name == "my-app"

    async def test_refuses_past_the_per_user_cap(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_API_KEYS_PER_USER", 2)

        for i in range(2):
            r = await client.post("/api/v1/account/keys", json={"name": f"key-{i}"})
            assert r.status_code == 200

        r = await client.post("/api/v1/account/keys", json={"name": "one-too-many"})
        assert r.status_code == 422

    async def test_a_revoked_key_does_not_count_against_the_cap(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(settings, "MAX_API_KEYS_PER_USER", 1)

        first = await client.post("/api/v1/account/keys", json={"name": "first"})
        key_id = first.json()["id"]
        await client.delete(f"/api/v1/account/keys/{key_id}")

        r = await client.post("/api/v1/account/keys", json={"name": "second"})
        assert r.status_code == 200


class TestListKeys:
    async def test_lists_without_ever_including_the_secret(self, client):
        await client.post("/api/v1/account/keys", json={"name": "my-app"})

        r = await client.get("/api/v1/account/keys")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert "secret" not in body["items"][0]
        assert body["items"][0]["key_prefix"].startswith("mk_live_")

    async def test_revoked_keys_no_longer_appear(self, client):
        created = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        key_id = created.json()["id"]
        await client.delete(f"/api/v1/account/keys/{key_id}")

        r = await client.get("/api/v1/account/keys")
        assert r.json() == {"items": [], "total": 0}

    async def test_empty_for_an_account_with_no_keys(self, client):
        r = await client.get("/api/v1/account/keys")
        assert r.json() == {"items": [], "total": 0}


class TestRevokeKey:
    async def test_revoked_key_stops_authenticating(self, client, test_session):
        from app.core.api_keys import find_db_key

        created = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        key_id, plaintext = created.json()["id"], created.json()["secret"]

        await client.delete(f"/api/v1/account/keys/{key_id}")

        assert await find_db_key(test_session, plaintext) is None

    async def test_unknown_key_id_is_404(self, client):
        r = await client.delete(
            "/api/v1/account/keys/00000000-0000-0000-0000-000000000000"
        )
        assert r.status_code == 404

    async def test_one_account_cannot_revoke_another_accounts_key(
        self, test_session, owner
    ):
        other_user = await _make_user(test_session, email="other@example.com")

        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_session] = lambda: test_session
        app.dependency_overrides[require_firebase_user] = lambda: owner

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as owner_client:
            created = await owner_client.post(
                "/api/v1/account/keys", json={"name": "owners-key"}
            )
        key_id = created.json()["id"]

        app.dependency_overrides[require_firebase_user] = lambda: other_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as other_client:
            r = await other_client.delete(f"/api/v1/account/keys/{key_id}")

        assert r.status_code == 404


class TestRotateKey:
    async def test_old_key_stops_working_new_one_starts(self, client, test_session):
        from app.core.api_keys import find_db_key

        created = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        key_id, old_plaintext = created.json()["id"], created.json()["secret"]

        rotated = await client.post(f"/api/v1/account/keys/{key_id}/rotate")
        assert rotated.status_code == 200
        new_plaintext = rotated.json()["secret"]

        assert new_plaintext != old_plaintext
        assert await find_db_key(test_session, old_plaintext) is None
        assert (await find_db_key(test_session, new_plaintext)) is not None

    async def test_carries_over_name_and_rate_limit(self, client):
        created = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        key_id = created.json()["id"]

        rotated = await client.post(f"/api/v1/account/keys/{key_id}/rotate")
        assert rotated.json()["name"] == "my-app"
        assert (
            rotated.json()["requests_per_minute"] == created.json()["requests_per_minute"]
        )

    async def test_does_not_count_twice_against_the_cap(self, client, monkeypatch):
        monkeypatch.setattr(settings, "MAX_API_KEYS_PER_USER", 1)

        created = await client.post("/api/v1/account/keys", json={"name": "my-app"})
        key_id = created.json()["id"]

        # At the cap already (1/1 live). Rotating must still work - the
        # old key stops being live in the same commit the new one starts.
        rotated = await client.post(f"/api/v1/account/keys/{key_id}/rotate")
        assert rotated.status_code == 200

        listed = await client.get("/api/v1/account/keys")
        assert len(listed.json()["items"]) == 1

    async def test_unknown_key_id_is_404(self, client):
        r = await client.post(
            "/api/v1/account/keys/00000000-0000-0000-0000-000000000000/rotate"
        )
        assert r.status_code == 404

    async def test_one_account_cannot_rotate_another_accounts_key(
        self, test_session, owner
    ):
        other_user = await _make_user(test_session, email="other-rotate@example.com")

        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_session] = lambda: test_session
        app.dependency_overrides[require_firebase_user] = lambda: owner

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as owner_client:
            created = await owner_client.post(
                "/api/v1/account/keys", json={"name": "owners-key"}
            )
        key_id = created.json()["id"]

        app.dependency_overrides[require_firebase_user] = lambda: other_user
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as other_client:
            r = await other_client.post(f"/api/v1/account/keys/{key_id}/rotate")

        assert r.status_code == 404


class TestRequireFirebaseUser:
    """The token-verification chain itself, not bypassed by the `client`
    fixture above - this is what actually protects the endpoints."""

    async def test_missing_bearer_token_is_401(self, test_session):
        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_session] = lambda: test_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get("/api/v1/account/keys")
        assert r.status_code == 401

    async def test_valid_token_creates_a_user_on_first_sign_in(
        self, test_session, monkeypatch
    ):
        from app.core import firebase as firebase_module

        monkeypatch.setattr(
            firebase_module,
            "_get_app",
            lambda: object(),
        )
        monkeypatch.setattr(
            firebase_module.firebase_auth,
            "verify_id_token",
            lambda token, app=None: {"uid": "new-uid", "email": "new@example.com"},
        )

        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_session] = lambda: test_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get(
                "/api/v1/account/keys", headers={"Authorization": "Bearer anything"}
            )

        assert r.status_code == 200

        from sqlmodel import select

        user = (
            await test_session.exec(
                select(User).where(User.firebase_uid == "new-uid")
            )
        ).first()
        assert user is not None
        assert user.email == "new@example.com"

    async def test_invalid_token_is_401(self, test_session, monkeypatch):
        from app.core import firebase as firebase_module

        monkeypatch.setattr(firebase_module, "_get_app", lambda: object())

        def _raise(token, app=None):
            raise ValueError("bad token")

        monkeypatch.setattr(firebase_module.firebase_auth, "verify_id_token", _raise)

        app = FastAPI()
        app.include_router(api_router)
        app.dependency_overrides[get_session] = lambda: test_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            r = await ac.get(
                "/api/v1/account/keys", headers={"Authorization": "Bearer bad"}
            )
        assert r.status_code == 401
