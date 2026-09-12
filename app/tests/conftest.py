from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Import every model so SQLModel.metadata knows about all of them before
# create_all runs - importing app.db.models alone isn't enough since some
# modules are only pulled in lazily elsewhere (e.g. connectors).
from app.db.models import (  # noqa: F401
    Fixture,
    League,
    PlayerMatchStat,
    PlayerStat,
    SchedulerHeartbeat,
    ShotEvent,
    Standing,
    Team,
    TeamMatchStat,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Fresh in-memory SQLite DB per test - fast, no Docker/Postgres
    dependency, and isolated (no state leaking between tests)."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async_session_maker = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_maker() as session:
        yield session
