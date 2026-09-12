from datetime import timedelta

from app.core.heartbeat import (
    JOB_GRACE_SECONDS,
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
