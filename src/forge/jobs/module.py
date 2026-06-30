from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
from typing import TYPE_CHECKING, Any, ClassVar

from forge.core.module import ForgeModule, HealthResult
from forge.jobs.queue import JobQueue, MemoryBackend, QueueBackend, RedisBackend
from forge.jobs.scheduler import CronExpression, ScheduledJob, Scheduler

if TYPE_CHECKING:
    from collections.abc import Callable

    from forge.core.runtime import ForgeRuntime

_logger = logging.getLogger(__name__)


class JobDefinition:
    """
    Wrapper returned by the ``@job`` decorator.

    Holds the original async function and metadata. Calling
    ``.enqueue(...)`` pushes a job onto the queue.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        queue: str,
        max_retries: int,
    ) -> None:
        self._func = func
        self.queue = queue
        self.max_retries = max_retries
        functools.update_wrapper(self, func)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._func(*args, **kwargs)

    async def enqueue(self, *args: Any, **kwargs: Any) -> Any:
        from forge.jobs._state import get_job_queue

        jq = get_job_queue()
        if jq is None:
            raise RuntimeError(
                "Jobs module is not initialized. "
                "Ensure the JobsModule is registered with the runtime and "
                "await runtime.init() has been called."
            )
        job = await jq.enqueue(
            queue=self.queue,
            func_name=self._func.__qualname__,
            args=args,
            kwargs=kwargs,
            max_retries=self.max_retries,
        )
        return job


class ScheduleDefinition:
    """
    Wrapper returned by the ``@schedule`` decorator.

    Registers the function with the Scheduler on runtime init.
    The decorated function is still callable directly.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        cron: str,
        queue: str,
    ) -> None:
        self._func = func
        self._cron = cron
        self._queue = queue
        self._cron_expr: CronExpression | None = None
        self._scheduled_job: ScheduledJob | None = None
        functools.update_wrapper(self, func)

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        result = self._func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result


def job(
    _func: Callable[..., Any] | None = None,
    *,
    queue: str = "default",
    retry: int = 3,
) -> Any:
    """
    Decorator for defining an async background job.

    Parameters
    ----------
    queue:
        Name of the queue this job belongs to.
    retry:
        Maximum number of retry attempts on failure.

    Usage::

        @job(queue="emails", retry=3)
        async def send_welcome_email(user_id: int):
            ...

        await send_welcome_email.enqueue(user_id=123)
    """

    def decorator(fn: Callable[..., Any]) -> JobDefinition:
        return JobDefinition(func=fn, queue=queue, max_retries=retry)

    if _func is not None:
        return decorator(_func)
    return decorator


def schedule(
    _func: Callable[..., Any] | None = None,
    *,
    cron: str = "* * * * *",
    queue: str = "scheduled",
) -> Any:
    """
    Decorator for cron-like scheduled tasks.

    Parameters
    ----------
    cron:
        Standard five-field cron expression.
    queue:
        Queue name for tracking.

    Usage::

        @schedule(cron="0 9 * * *")
        async def daily_report():
            ...
    """

    def decorator(fn: Callable[..., Any]) -> ScheduleDefinition:
        return ScheduleDefinition(func=fn, cron=cron, queue=queue)

    if _func is not None:
        return decorator(_func)
    return decorator


class JobsModule(ForgeModule):
    """
    Background jobs and scheduling module.

    Provides queue-backed async job execution with automatic retry,
    concurrency control, dead-letter queue, progress tracking, and
    cron-like scheduled tasks.
    """

    name = "jobs"
    dependencies: ClassVar[list[str]] = ["config"]

    def __init__(
        self,
        *,
        backend: str = "memory",
        default_retry: int = 3,
        concurrency: int = 10,
        retry_backoff_base: float = 1.0,
        redis_url: str | None = None,
        redis_key_prefix: str = "forge:jobs:",
        redis_max_connections: int = 10,
    ) -> None:
        super().__init__()
        self._backend_type = backend
        self._default_retry = default_retry
        self._concurrency = concurrency
        self._retry_backoff_base = retry_backoff_base
        self._redis_url = redis_url
        self._redis_key_prefix = redis_key_prefix
        self._redis_max_connections = redis_max_connections
        self._queue: JobQueue | None = None
        self._scheduler: Scheduler | None = None
        self._queue_backend: QueueBackend | None = None
        self._job_defs: list[JobDefinition] = []
        self._schedule_defs: list[ScheduleDefinition] = []
        self._worker_task: asyncio.Task[None] | None = None
        self._scheduler_task: asyncio.Task[None] | None = None

    async def setup(self, runtime: ForgeRuntime) -> None:
        from forge.config.module import ConfigModule
        from forge.jobs._state import set_job_queue

        config_module: ConfigModule = runtime.get(ConfigModule)  # type: ignore[assignment]
        jobs_cfg = getattr(config_module.config, "jobs", None)

        backend = self._backend_type
        default_retry = self._default_retry
        concurrency = self._concurrency
        retry_backoff_base = self._retry_backoff_base
        redis_url = self._redis_url
        redis_key_prefix = self._redis_key_prefix
        redis_max_connections = self._redis_max_connections

        if jobs_cfg is not None:
            backend = getattr(jobs_cfg, "backend", backend)
            default_retry = getattr(jobs_cfg, "default_retry", default_retry)
            concurrency = getattr(jobs_cfg, "concurrency", concurrency)
            retry_backoff_base = getattr(jobs_cfg, "retry_backoff_base", retry_backoff_base)
            redis_cfg = getattr(jobs_cfg, "redis", None)
            if redis_cfg is not None:
                redis_url = getattr(redis_cfg, "url", redis_url)
                redis_key_prefix = getattr(redis_cfg, "key_prefix", redis_key_prefix)
                redis_max_connections = getattr(redis_cfg, "max_connections", redis_max_connections)

        if backend == "redis":
            b = RedisBackend(
                redis_url=redis_url or "redis://localhost:6379/0",
                key_prefix=redis_key_prefix,
                max_connections=redis_max_connections,
            )
            await b.connect()
            self._queue_backend = b
        else:
            self._queue_backend = MemoryBackend()

        self._queue = JobQueue(
            backend=self._queue_backend,
            default_retry=default_retry,
            concurrency=concurrency,
            retry_backoff_base=retry_backoff_base,
        )

        for jd in self._job_defs:
            self._queue.register(jd._func.__qualname__, jd._func)

        await self._queue.start()
        set_job_queue(self._queue)

        self._scheduler = Scheduler()
        for sd in self._schedule_defs:
            self._scheduler.register(
                name=sd._func.__qualname__,
                cron_expression=sd._cron,
                func=sd._func,
                queue=sd._queue,
            )

        self._worker_task = asyncio.create_task(self._queue.process("default"))
        self._scheduler_task = asyncio.create_task(self._scheduler.start())

        _logger.info("Jobs module initialized (backend=%s, concurrency=%d)", backend, concurrency)

    async def teardown(self) -> None:
        from forge.jobs._state import set_job_queue

        if self._scheduler_task is not None:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task
            self._scheduler_task = None

        if self._scheduler is not None:
            await self._scheduler.stop()
            self._scheduler = None

        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

        if self._queue is not None:
            await self._queue.stop()
            self._queue = None

        set_job_queue(None)

    def health_check(self) -> HealthResult:
        if self._queue is None:
            return HealthResult.error("Jobs module not initialized")
        return HealthResult.ok()

    def register_job(self, job_def: JobDefinition) -> None:
        self._job_defs.append(job_def)

    def register_schedule(self, schedule_def: ScheduleDefinition) -> None:
        self._schedule_defs.append(schedule_def)

    async def enqueue(
        self,
        func_name: str,
        queue: str = "default",
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int | None = None,
    ) -> Any:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.enqueue(
            queue=queue,
            func_name=func_name,
            args=args,
            kwargs=kwargs or {},
            max_retries=max_retries,
        )

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.get_job_status(job_id)

    async def get_queue_size(self, queue: str = "default") -> int:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.get_queue_size(queue)

    async def get_dead_letter_jobs(self) -> list[Any]:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.get_dead_letter_jobs()

    async def get_dead_letter_size(self) -> int:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.get_dead_letter_size()

    async def requeue_dead_letter(self, job_id: str) -> Any:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return await self._queue.requeue_dead_letter(job_id)

    async def update_progress(self, job_id: str, progress: float) -> None:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        await self._queue.update_progress(job_id, progress)

    @property
    def queue(self) -> JobQueue:
        if self._queue is None:
            raise RuntimeError("Jobs module not initialized")
        return self._queue

    @property
    def scheduler_instance(self) -> Scheduler:
        if self._scheduler is None:
            raise RuntimeError("Jobs module not initialized")
        return self._scheduler
