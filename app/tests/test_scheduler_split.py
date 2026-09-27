from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient


class TestApiNeverRunsScheduler:
    """serve (app/main.py) must never start the scheduler - only the
    standalone `scheduler` process does (app/scheduler/main.py), the same
    way only `migrate` runs migrations, never `serve`. Guards against the
    scheduler being reintroduced into the API process."""

    def test_main_module_has_no_scheduler_start_stop_functions(self):
        import app.main as main_module

        assert not hasattr(main_module, "start_scheduler")
        assert not hasattr(main_module, "stop_scheduler")

    async def test_lifespan_still_seeds_heartbeats_for_the_health_view(
        self, monkeypatch
    ):
        """/health/scheduler is a read-only view on the heartbeat table
        (see app/core/heartbeat.py) - it must stay accurate here even
        though this process never runs the jobs it reports on."""
        import app.main as main_module

        seed = AsyncMock()
        monkeypatch.setattr(main_module, "seed_heartbeats_on_startup", seed)
        monkeypatch.setattr(
            main_module,
            "async_session",
            lambda: AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()),
        )

        async with main_module.lifespan(main_module.app):
            pass

        seed.assert_called_once()


class TestStandaloneSchedulerProcess:
    """app/scheduler/main.py: the process a split deployment runs instead
    of the in-process scheduler. ASGITransport does not run the lifespan
    (see test_heartbeat.py), so this only exercises the liveness route,
    not start_scheduler() itself."""

    async def test_health_reports_ok(self):
        from app.scheduler.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "matchday-scheduler"}
