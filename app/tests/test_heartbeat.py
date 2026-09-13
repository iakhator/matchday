from datetime import timedelta

import pytest

from app.core.heartbeat import (
    JOB_GRACE_SECONDS,
    get_job_health,
    get_stale_jobs,
    record_heartbeat,
    seed_heartbeats_on_startup,
)
from app.db.models import SchedulerHeartbeat
from app.utils.datetime_utils import utcnow

JOB_ID = "sync_fixtures"  # a real configured job id


class TestRecordHeartbeat:
    async def test_creates_row_on_first_call(self, test_session):
        await record_heartbeat(test_session, JOB_ID)
        row = await test_session.get(SchedulerHeartbeat, JOB_ID)
        assert row is not None

    async def test_second_call_updates_in_place_not_duplicates(self, test_session):
        await record_heartbeat(test_session, JOB_ID)
        first_stamp = (await test_session.get(SchedulerHeartbeat, JOB_ID)).last_run_at

        await record_heartbeat(test_session, JOB_ID)

        from sqlmodel import select

        rows = (
            await test_session.exec(
                select(SchedulerHeartbeat).where(SchedulerHeartbeat.job_id == JOB_ID)
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].last_run_at >= first_stamp

    async def test_unknown_job_id_is_a_noop_not_a_crash(self, test_session):
        # A typo'd job id in a heartbeat call site should never take the
        # scheduler down - it should just fail to record anything.
        await record_heartbeat(test_session, "not_a_real_job")
        row = await test_session.get(SchedulerHeartbeat, "not_a_real_job")
        assert row is None


class TestGetStaleJobs:
    async def test_job_that_never_ran_is_stale(self, test_session):
        stale = await get_stale_jobs(test_session)
        assert set(stale) == set(JOB_GRACE_SECONDS)

    async def test_freshly_recorded_job_is_not_stale(self, test_session):
        for job_id in JOB_GRACE_SECONDS:
            test_session.add(SchedulerHeartbeat(job_id=job_id, last_run_at=utcnow()))
        await test_session.commit()

        assert await get_stale_jobs(test_session) == []

    async def test_job_past_its_grace_period_is_stale(self, test_session):
        for job_id, grace_seconds in JOB_GRACE_SECONDS.items():
            too_old = utcnow() - timedelta(seconds=grace_seconds + 60)
            test_session.add(SchedulerHeartbeat(job_id=job_id, last_run_at=too_old))
        await test_session.commit()

        stale = await get_stale_jobs(test_session)
        assert set(stale) == set(JOB_GRACE_SECONDS)

    async def test_only_the_lapsed_job_is_reported(self, test_session):
        for job_id in JOB_GRACE_SECONDS:
            test_session.add(SchedulerHeartbeat(job_id=job_id, last_run_at=utcnow()))
        await test_session.commit()

        stale_row = await test_session.get(SchedulerHeartbeat, JOB_ID)
        stale_row.last_run_at = utcnow() - timedelta(
            seconds=JOB_GRACE_SECONDS[JOB_ID] + 60
        )
        test_session.add(stale_row)
        await test_session.commit()

        assert await get_stale_jobs(test_session) == [JOB_ID]


class TestSeedHeartbeatsOnStartup:
    async def test_seeds_missing_jobs(self, test_session):
        await seed_heartbeats_on_startup(test_session)
        assert await get_stale_jobs(test_session) == []

    async def test_does_not_overwrite_an_existing_genuinely_stale_job(
        self, test_session
    ):
        # A restart must never launder a job that's actually been dead for
        # a while back into looking healthy.
        too_old = utcnow() - timedelta(seconds=JOB_GRACE_SECONDS[JOB_ID] + 60)
        test_session.add(SchedulerHeartbeat(job_id=JOB_ID, last_run_at=too_old))
        await test_session.commit()

        await seed_heartbeats_on_startup(test_session)

        assert await get_stale_jobs(test_session) == [JOB_ID]


class TestJobHealthDetail:
    """Per-job detail, so an alert says how stale and against what."""

    async def test_reports_age_and_threshold_for_each_job(self, test_session):
        await record_heartbeat(test_session, JOB_ID)
        jobs = {j["job_id"]: j for j in await get_job_health(test_session)}

        assert set(jobs) == set(JOB_GRACE_SECONDS)
        fresh = jobs[JOB_ID]
        assert fresh["stale"] is False
        assert fresh["age_seconds"] < 5
        assert fresh["threshold_seconds"] == JOB_GRACE_SECONDS[JOB_ID]
        assert fresh["last_run_at"] is not None

    async def test_a_job_that_never_ran_has_no_age(self, test_session):
        jobs = {j["job_id"]: j for j in await get_job_health(test_session)}
        never = jobs[JOB_ID]
        assert never["stale"] is True
        assert never["last_run_at"] is None
        # Not 0 - that would read as "ran just now" in an alert.
        assert never["age_seconds"] is None

    async def test_stale_list_agrees_with_the_detail(self, test_session):
        await record_heartbeat(test_session, JOB_ID)
        jobs = await get_job_health(test_session)
        assert sorted(await get_stale_jobs(test_session)) == sorted(
            j["job_id"] for j in jobs if j["stale"]
        )


class TestSchedulerHealthEndpoint:
    """The status code is the part monitors actually read."""

    @pytest.fixture(autouse=True)
    def _clear_overrides(self):
        """`app` is module-level and shared, so an override left behind
        would point later tests at this test's session."""
        from app.main import app

        yield
        app.dependency_overrides.clear()

    @staticmethod
    def _client(test_session):
        """Drive the real app with the session overridden.

        Copying route objects into a fresh FastAPI instance does not work -
        the routes keep their original dependency wiring, so the overridden
        session is ignored and the endpoint queries the real database.
        Overriding on the app that actually handles the request is the only
        thing that takes effect.

        ASGITransport does not run the lifespan, so the scheduler stays out
        of it.
        """
        from httpx import ASGITransport, AsyncClient

        from app.db.database import get_session
        from app.main import app

        app.dependency_overrides[get_session] = lambda: test_session
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_stale_scheduler_returns_503(self, test_session):
        """This returned 200 with an "unhealthy" body, so an uptime monitor
        watching status codes would never have fired - the exact failure
        the endpoint exists to catch."""
        async with self._client(test_session) as client:
            response = await client.get("/health/scheduler")

        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"

    async def test_healthy_scheduler_returns_200(self, test_session):
        for job_id in JOB_GRACE_SECONDS:
            await record_heartbeat(test_session, job_id)

        async with self._client(test_session) as client:
            response = await client.get("/health/scheduler")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["stale_jobs"] == []

    async def test_one_stale_job_is_enough_to_report_unhealthy(self, test_session):
        for job_id in JOB_GRACE_SECONDS:
            await record_heartbeat(test_session, job_id)
        lapsed = await test_session.get(SchedulerHeartbeat, JOB_ID)
        lapsed.last_run_at = utcnow() - timedelta(
            seconds=JOB_GRACE_SECONDS[JOB_ID] + 60
        )
        test_session.add(lapsed)
        await test_session.commit()

        async with self._client(test_session) as client:
            response = await client.get("/health/scheduler")

        assert response.status_code == 503
        assert response.json()["stale_jobs"] == [JOB_ID]

    async def test_liveness_stays_200_when_the_scheduler_is_stale(self, test_session):
        """/health is what the container healthcheck uses. A stale sync job
        means the data is going stale, not that the process is broken -
        restarting it would fix nothing and loop."""
        async with self._client(test_session) as client:
            assert (await client.get("/health")).status_code == 200
