from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from forge.jobs import (
    CronExpression,
    Job,
    JobQueue,
    JobStatus,
    JobsModule,
    MemoryBackend,
    RedisBackend,
    Scheduler,
    JobDefinition,
    ScheduleDefinition,
    job,
    schedule,
)
from forge.jobs._state import get_job_queue, set_job_queue
from forge.jobs.scheduler import ScheduledJob
from forge.config.module import ConfigModule
from forge.config.schema import ForgeConfig, JobsConfig
from forge.core.runtime import ForgeRuntime
from forge.core.module import HealthResult


# ── Job / JobStatus ──────────────────────────────────────────────────


def test_job_creation() -> None:
    j = Job(
        job_id="abc123",
        queue="emails",
        func_name="send_email",
        args=(1,),
        kwargs={"template": "welcome"},
        max_retries=3,
    )
    assert j.job_id == "abc123"
    assert j.queue == "emails"
    assert j.func_name == "send_email"
    assert j.args == (1,)
    assert j.kwargs == {"template": "welcome"}
    assert j.max_retries == 3
    assert j.retry_count == 0
    assert j.status == JobStatus.PENDING
    assert j.progress == 0.0


def test_job_status_values() -> None:
    assert JobStatus.PENDING == "pending"
    assert JobStatus.RUNNING == "running"
    assert JobStatus.SUCCESS == "success"
    assert JobStatus.FAILED == "failed"
    assert JobStatus.DEAD == "dead"


def test_job_to_dict() -> None:
    j = Job(
        job_id="abc",
        queue="q",
        func_name="f",
        args=(),
        kwargs={},
        max_retries=3,
    )
    d = j.to_dict()
    assert d["job_id"] == "abc"
    assert d["queue"] == "q"
    assert d["func_name"] == "f"
    assert d["retry_count"] == 0
    assert d["status"] == JobStatus.PENDING
    assert d["progress"] == 0.0


# ── CronExpression ───────────────────────────────────────────────────


class TestCronExpression:
    def test_wildcard(self) -> None:
        c = CronExpression("* * * * *")
        dt = datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert c.matches(dt)

    def test_exact_hour_and_minute(self) -> None:
        c = CronExpression("30 9 * * *")
        assert c.matches(datetime(2025, 1, 15, 9, 30, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc))

    def test_daily_at_9am(self) -> None:
        c = CronExpression("0 9 * * *")
        assert c.matches(datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 6, 1, 9, 1, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 6, 1, 8, 0, tzinfo=timezone.utc))

    def test_weekdays_only(self) -> None:
        c = CronExpression("0 9 * * 1-5")
        monday = datetime(2025, 6, 2, 9, 0, tzinfo=timezone.utc)
        sunday = datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc)
        assert c.matches(monday)
        assert not c.matches(sunday)

    def test_step(self) -> None:
        c = CronExpression("*/15 * * * *")
        assert c.matches(datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
        assert c.matches(datetime(2025, 1, 1, 0, 15, tzinfo=timezone.utc))
        assert c.matches(datetime(2025, 1, 1, 0, 30, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 1, 1, 0, 7, tzinfo=timezone.utc))

    def test_list(self) -> None:
        c = CronExpression("0 9,18 * * *")
        assert c.matches(datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc))
        assert c.matches(datetime(2025, 1, 1, 18, 0, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc))

    def test_month_names(self) -> None:
        c = CronExpression("0 0 1 JAN,MAY *")
        assert c.matches(datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
        assert c.matches(datetime(2025, 5, 1, 0, 0, tzinfo=timezone.utc))
        assert not c.matches(datetime(2025, 3, 1, 0, 0, tzinfo=timezone.utc))

    def test_invalid_expression(self) -> None:
        with pytest.raises(ValueError, match="must have 5 fields"):
            CronExpression("0 9 * *")


# ── MemoryBackend ────────────────────────────────────────────────────


class TestMemoryBackend:
    @pytest.mark.asyncio
    async def test_enqueue_dequeue(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (1,), {}, 3)
        await b.enqueue(job)
        assert await b.size("q") == 1
        dequeued = await b.dequeue("q")
        assert dequeued is not None
        assert dequeued.job_id == "id1"
        assert await b.size("q") == 0

    @pytest.mark.asyncio
    async def test_dequeue_empty(self) -> None:
        b = MemoryBackend()
        assert await b.dequeue("nonexistent") is None
        assert await b.size("nonexistent") == 0

    @pytest.mark.asyncio
    async def test_get_job(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (), {}, 3)
        await b.enqueue(job)
        found = await b.get_job("id1")
        assert found is not None
        assert found.job_id == "id1"
        assert await b.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_job(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (), {}, 3)
        await b.enqueue(job)
        job.status = JobStatus.RUNNING
        await b.update_job(job)
        updated = await b.get_job("id1")
        assert updated is not None
        assert updated.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_dead_letter(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (), {}, 3)
        await b.enqueue_dead(job)
        assert await b.dead_letter_size() == 1
        dead_jobs = await b.dead_letter_jobs()
        assert len(dead_jobs) == 1
        assert dead_jobs[0].job_id == "id1"
        assert dead_jobs[0].status == JobStatus.DEAD

    @pytest.mark.asyncio
    async def test_requeue_dead(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (), {}, 3)
        await b.enqueue_dead(job)
        requeued = await b.requeue_dead("id1")
        assert requeued is not None
        assert requeued.status == JobStatus.PENDING
        assert await b.dead_letter_size() == 0
        assert await b.size("q") == 1

    @pytest.mark.asyncio
    async def test_dead_letter_max_capacity(self) -> None:
        b = MemoryBackend(max_dead_letter=2)
        for i in range(3):
            job = Job(f"id{i}", "q", "f", (), {}, 3)
            await b.enqueue_dead(job)
        assert await b.dead_letter_size() == 2

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        b = MemoryBackend()
        job = Job("id1", "q", "f", (), {}, 3)
        await b.enqueue(job)
        await b.close()
        assert await b.size("q") == 0


# ── RedisBackend ─────────────────────────────────────────────────────


class TestRedisBackend:
    @pytest.mark.asyncio
    async def test_connect_requires_redis(self) -> None:
        b = RedisBackend(redis_url="redis://localhost:16379/0")
        with pytest.raises(Exception):
            await b.connect()
            await b.size("test")

    @pytest.mark.asyncio
    async def test_get_job_nonexistent(self) -> None:
        b = RedisBackend()
        assert await b.get_job("nonexistent") is None

    @pytest.mark.asyncio
    async def test_dead_letter_requeue_nonexistent(self) -> None:
        b = RedisBackend()
        assert await b.requeue_dead("nonexistent") is None


# ── JobQueue ─────────────────────────────────────────────────────────


class TestJobQueue:
    @pytest.mark.asyncio
    async def test_enqueue_and_get_job_status(self) -> None:
        async def my_func(x: int) -> int:
            return x * 2

        backend = MemoryBackend()
        q = JobQueue(backend=backend, default_retry=3, concurrency=10)
        q.register("my_func", my_func)
        await q.start()

        job = await q.enqueue("default", "my_func", args=(5,))
        assert job.queue == "default"
        assert job.max_retries == 3

        status = await q.get_job_status(job.job_id)
        assert status is not None
        assert status["status"] == JobStatus.PENDING
        await q.stop()

    @pytest.mark.asyncio
    async def test_process_successful_job(self) -> None:
        results: list[int] = []

        async def add(a: int, b: int) -> int:
            result = a + b
            results.append(result)
            return result

        backend = MemoryBackend()
        q = JobQueue(backend=backend, concurrency=10)
        q.register("add", add)
        await q.start()

        await q.enqueue("default", "add", args=(2, 3))
        await asyncio.sleep(0.2)

        # process a few ticks
        process_task = asyncio.create_task(q.process("default"))
        await asyncio.sleep(0.5)
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

        assert len(results) == 1
        assert results[0] == 5
        await q.stop()

    @pytest.mark.asyncio
    async def test_job_retry_and_dead_letter(self) -> None:
        call_count: int = 0

        async def flaky() -> None:
            nonlocal call_count
            call_count += 1
            msg = f"Attempt {call_count} failed"
            raise ValueError(msg)

        backend = MemoryBackend()
        q = JobQueue(backend=backend, default_retry=2, retry_backoff_base=0.01)
        q.register("flaky", flaky)
        await q.start()

        await q.enqueue("default", "flaky", max_retries=2)
        await asyncio.sleep(0.3)

        process_task = asyncio.create_task(q.process("default"))
        await asyncio.sleep(1.0)
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

        dead = await q.get_dead_letter_jobs()
        assert len(dead) == 1
        assert dead[0].status == JobStatus.DEAD
        assert call_count >= 2
        await q.stop()

    @pytest.mark.asyncio
    async def test_update_progress(self) -> None:
        backend = MemoryBackend()
        q = JobQueue(backend=backend)
        await q.start()

        job = await q.enqueue("default", "nonexistent")
        await q.update_progress(job.job_id, 0.5)
        status = await q.get_job_status(job.job_id)
        assert status is not None
        assert status["progress"] == 0.5
        await q.stop()

    @pytest.mark.asyncio
    async def test_get_queue_size(self) -> None:
        backend = MemoryBackend()
        q = JobQueue(backend=backend)
        await q.start()

        assert await q.get_queue_size("default") == 0
        await q.enqueue("default", "f")
        assert await q.get_queue_size("default") == 1
        await q.stop()

    @pytest.mark.asyncio
    async def test_enqueue_with_custom_retry(self) -> None:
        backend = MemoryBackend()
        q = JobQueue(backend=backend, default_retry=3)
        await q.start()

        job = await q.enqueue("default", "f", max_retries=5)
        assert job.max_retries == 5
        await q.stop()

    @pytest.mark.asyncio
    async def test_requeue_dead_letter_from_job_queue(self) -> None:
        backend = MemoryBackend()
        q = JobQueue(backend=backend, default_retry=1, retry_backoff_base=0.01)
        await q.start()

        job = await q.enqueue("default", "nonexistent_func", max_retries=0)
        # trigger immediate failure by processing
        process_task = asyncio.create_task(q.process("default"))
        await asyncio.sleep(0.5)
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

        dead = await q.get_dead_letter_jobs()
        if dead:
            requeued = await q.requeue_dead_letter(dead[0].job_id)
            assert requeued is not None
            assert requeued.status == JobStatus.PENDING

        assert await q.get_dead_letter_size() == 0
        await q.stop()

    @pytest.mark.asyncio
    async def test_active_count(self) -> None:
        backend = MemoryBackend()
        q = JobQueue(backend=backend, concurrency=5)
        await q.start()
        assert q.active_count == 0
        await q.stop()


# ── @job decorator ───────────────────────────────────────────────────


class TestJobDecorator:
    def test_job_decorator_with_args(self) -> None:
        @job(queue="emails", retry=3)
        async def send_email(user_id: int) -> str:
            return f"sent to {user_id}"

        assert isinstance(send_email, JobDefinition)
        assert send_email.queue == "emails"
        assert send_email.max_retries == 3
        assert send_email.__name__ == "send_email"

    def test_job_decorator_defaults(self) -> None:
        @job()
        async def my_job() -> None:
            pass

        assert isinstance(my_job, JobDefinition)
        assert my_job.queue == "default"
        assert my_job.max_retries == 3

    def test_job_decorator_no_parens(self) -> None:
        @job
        async def my_job() -> None:
            pass

        assert isinstance(my_job, JobDefinition)
        assert my_job.queue == "default"
        assert my_job.max_retries == 3

    @pytest.mark.asyncio
    async def test_job_call_directly(self) -> None:
        @job(queue="test")
        async def add(a: int, b: int) -> int:
            return a + b

        result = await add(2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_job_enqueue_without_runtime(self) -> None:
        set_job_queue(None)

        @job(queue="test")
        async def my_job() -> None:
            pass

        with pytest.raises(RuntimeError, match="not initialized"):
            await my_job.enqueue()


# ── @schedule decorator ──────────────────────────────────────────────


class TestScheduleDecorator:
    def test_schedule_decorator(self) -> None:
        @schedule(cron="0 9 * * *")
        async def daily_report() -> str:
            return "report generated"

        assert isinstance(daily_report, ScheduleDefinition)

    def test_schedule_decorator_defaults(self) -> None:
        @schedule()
        async def my_task() -> None:
            pass

        assert isinstance(my_task, ScheduleDefinition)

    @pytest.mark.asyncio
    async def test_schedule_call_directly(self) -> None:
        @schedule(cron="* * * * *")
        async def my_task() -> str:
            return "done"

        result = await my_task()
        assert result == "done"


# ── Scheduler ────────────────────────────────────────────────────────


class TestScheduler:
    @pytest.mark.asyncio
    async def test_register_and_status(self) -> None:
        s = Scheduler()
        s.register("test_job", "0 9 * * *", lambda: None)
        assert "test_job" in s.jobs
        assert s.jobs["test_job"].queue == "scheduled"

    def test_get_status(self) -> None:
        s = Scheduler()
        s.register("job1", "*/5 * * * *", lambda: None)
        s.register("job2", "0 0 * * *", lambda: None)
        status = s.get_status()
        assert len(status) == 2
        names = {entry["name"] for entry in status}
        assert names == {"job1", "job2"}

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        s = Scheduler()
        s.register("daily", "0 9 * * *", lambda: None)
        start_task = asyncio.create_task(s.start())
        await asyncio.sleep(0.2)
        await s.stop()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
        assert not s._started


# ── JobsModule ───────────────────────────────────────────────────────


class TestJobsModule:
    @pytest.mark.asyncio
    async def test_module_health_check_not_initialized(self) -> None:
        module = JobsModule()
        result = module.health_check()
        assert result.status == HealthResult.ERROR

    @pytest.mark.asyncio
    async def test_module_operations_without_init(self) -> None:
        module = JobsModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            await module.get_job_status("test")

        with pytest.raises(RuntimeError, match="not initialized"):
            await module.get_queue_size()

    @pytest.mark.asyncio
    async def test_register_job_and_schedule(self) -> None:
        module = JobsModule()

        @job(queue="testq", retry=2)
        async def my_job(x: int) -> int:
            return x + 1

        @schedule(cron="0 * * * *")
        async def my_task() -> None:
            pass

        module.register_job(my_job)
        module.register_schedule(my_task)
        assert len(module._job_defs) == 1
        assert len(module._schedule_defs) == 1

    @pytest.mark.asyncio
    async def test_integration_with_runtime(self) -> None:
        config_module = ConfigModule()
        jobs_module = JobsModule()

        runtime = ForgeRuntime()
        runtime.register(config_module)
        runtime.register(jobs_module)
        await runtime.init()

        assert jobs_module.health_check().status == HealthResult.OK

        status = await jobs_module.get_queue_size()
        assert status == 0

        dead_size = await jobs_module.get_dead_letter_size()
        assert dead_size == 0

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_queue_property(self) -> None:
        module = JobsModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = module.queue

    @pytest.mark.asyncio
    async def test_scheduler_property(self) -> None:
        module = JobsModule()
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = module.scheduler_instance

    @pytest.mark.asyncio
    async def test_enqueue_and_get_job_status_via_module(self) -> None:
        config_module = ConfigModule()
        jobs_module = JobsModule()

        runtime = ForgeRuntime()
        runtime.register(config_module)
        runtime.register(jobs_module)
        await runtime.init()

        job = await jobs_module.enqueue("my_func", args=(1,))
        assert job.queue == "default"

        status = await jobs_module.get_job_status(job.job_id)
        assert status is not None
        assert status["status"] == "pending"

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_update_progress_via_module(self) -> None:
        config_module = ConfigModule()
        jobs_module = JobsModule()

        runtime = ForgeRuntime()
        runtime.register(config_module)
        runtime.register(jobs_module)
        await runtime.init()

        job = await jobs_module.enqueue("some_func")
        await jobs_module.update_progress(job.job_id, 0.75)

        status = await jobs_module.get_job_status(job.job_id)
        assert status is not None
        assert status["progress"] == 0.75

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_memory_backend_default(self) -> None:
        config_module = ConfigModule()
        jobs_module = JobsModule()

        runtime = ForgeRuntime()
        runtime.register(config_module)
        runtime.register(jobs_module)
        await runtime.init()

        assert jobs_module._queue_backend is not None
        assert isinstance(jobs_module._queue_backend, MemoryBackend)

        await runtime.teardown()

    @pytest.mark.asyncio
    async def test_redis_backend_config(self) -> None:
        jobs_module = JobsModule(backend="redis")
        assert jobs_module._backend_type == "redis"

    @pytest.mark.asyncio
    async def test_health_check_via_runtime(self) -> None:
        config_module = ConfigModule()
        jobs_module = JobsModule()

        runtime = ForgeRuntime()
        runtime.register(config_module)
        runtime.register(jobs_module)
        await runtime.init()

        hr = jobs_module.health_check()
        assert hr.status == HealthResult.OK

        await runtime.teardown()
