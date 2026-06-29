from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any

_logger = logging.getLogger(__name__)


class JobStatus:
    """Enumeration of possible job lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD = "dead"


class JobResult:
    """Stores the result or error of a completed job."""

    __slots__ = ("error", "value")

    def __init__(self, value: Any = None, error: BaseException | None = None) -> None:
        self.value = value
        self.error = error


class Job:
    """
    Represents a single enqueued background job.

    Tracks identity, payload, retry state, progress, and result.
    """

    def __init__(
        self,
        job_id: str,
        queue: str,
        func_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        max_retries: int,
    ) -> None:
        self.job_id = job_id
        self.queue = queue
        self.func_name = func_name
        self.args = args
        self.kwargs = kwargs
        self.max_retries = max_retries
        self.retry_count: int = 0
        self.status: str = JobStatus.PENDING
        self.result: JobResult | None = None
        self.progress: float = 0.0
        self.created_at: float = time.monotonic()
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "queue": self.queue,
            "func_name": self.func_name,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": str(self.result.error) if self.result and self.result.error else None,
        }


class QueueBackend(ABC):
    """Abstract base class for job queue storage backends."""

    @abstractmethod
    async def enqueue(self, job: Job) -> None:
        ...

    @abstractmethod
    async def dequeue(self, queue: str) -> Job | None:
        ...

    @abstractmethod
    async def size(self, queue: str) -> int:
        ...

    @abstractmethod
    async def get_job(self, job_id: str) -> Job | None:
        ...

    @abstractmethod
    async def update_job(self, job: Job) -> None:
        ...

    @abstractmethod
    async def enqueue_dead(self, job: Job) -> None:
        ...

    @abstractmethod
    async def dead_letter_size(self) -> int:
        ...

    @abstractmethod
    async def dead_letter_jobs(self) -> list[Job]:
        ...

    @abstractmethod
    async def requeue_dead(self, job_id: str) -> Job | None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class MemoryBackend(QueueBackend):
    """
    In-memory queue backend for development.

    Uses OrderedDict per-queue for FIFO ordering.
    Stores both active queues and a dead-letter queue.
    """

    def __init__(self, max_dead_letter: int = 1000) -> None:
        self._queues: dict[str, OrderedDict[str, Job]] = {}
        self._jobs: dict[str, Job] = {}
        self._dead_letter: OrderedDict[str, Job] = OrderedDict()
        self._max_dead_letter = max_dead_letter

    async def enqueue(self, job: Job) -> None:
        self._jobs[job.job_id] = job
        q = self._queues.setdefault(job.queue, OrderedDict())
        q[job.job_id] = job

    async def dequeue(self, queue: str) -> Job | None:
        q = self._queues.get(queue)
        if not q:
            return None
        while q:
            job_id, job = next(iter(q.items()))
            if job.status == JobStatus.PENDING:
                del q[job_id]
                return job
            del q[job_id]
        return None

    async def size(self, queue: str) -> int:
        q = self._queues.get(queue)
        if not q:
            return 0
        return sum(1 for j in q.values() if j.status == JobStatus.PENDING)

    async def get_job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def update_job(self, job: Job) -> None:
        self._jobs[job.job_id] = job

    async def enqueue_dead(self, job: Job) -> None:
        job.status = JobStatus.DEAD
        self._dead_letter[job.job_id] = job
        if len(self._dead_letter) > self._max_dead_letter:
            self._dead_letter.popitem(last=False)

    async def dead_letter_size(self) -> int:
        return len(self._dead_letter)

    async def dead_letter_jobs(self) -> list[Job]:
        return list(self._dead_letter.values())

    async def requeue_dead(self, job_id: str) -> Job | None:
        job = self._dead_letter.get(job_id)
        if job is None:
            return None
        del self._dead_letter[job_id]
        job.status = JobStatus.PENDING
        job.retry_count = 0
        job.result = None
        job.started_at = None
        job.finished_at = None
        await self.enqueue(job)
        return job

    async def close(self) -> None:
        self._queues.clear()
        self._jobs.clear()
        self._dead_letter.clear()


class RedisBackend(QueueBackend):
    """
    Optional Redis-backed queue for production.

    Uses redis.asyncio with connection pooling and JSON serialization.
    Requires the ``redis`` optional extra.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "forge:jobs:",
        max_connections: int = 10,
        max_dead_letter: int = 1000,
    ) -> None:
        self._url = redis_url
        self._prefix = key_prefix
        self._max_connections = max_connections
        self._max_dead_letter = max_dead_letter
        self._pool: Any = None
        self._client: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._pool = aioredis.ConnectionPool.from_url(
            self._url,
            max_connections=self._max_connections,
            decode_responses=True,
        )
        self._client = aioredis.Redis(connection_pool=self._pool)

    async def _ensure_connected(self) -> Any:
        if self._client is None:
            await self.connect()
        return self._client

    async def enqueue(self, job: Job) -> None:
        client = await self._ensure_connected()
        import json

        data = json.dumps(job.to_dict())
        await client.rpush(f"{self._prefix}queue:{job.queue}", job.job_id)
        await client.set(f"{self._prefix}job:{job.job_id}", data)

    async def dequeue(self, queue: str) -> Job | None:
        client = await self._ensure_connected()
        import json

        job_id = await client.lpop(f"{self._prefix}queue:{queue}")
        if not job_id:
            return None
        raw = await client.get(f"{self._prefix}job:{job_id}")
        if not raw:
            return None
        data = json.loads(raw)
        job = self._reconstruct_job(data)
        return job

    async def size(self, queue: str) -> int:
        client = await self._ensure_connected()
        return await client.llen(f"{self._prefix}queue:{queue}")  # type: ignore[no-any-return]

    async def get_job(self, job_id: str) -> Job | None:
        client = await self._ensure_connected()
        import json

        raw = await client.get(f"{self._prefix}job:{job_id}")
        if not raw:
            return None
        data = json.loads(raw)
        return self._reconstruct_job(data)

    async def update_job(self, job: Job) -> None:
        client = await self._ensure_connected()
        import json

        data = json.dumps(job.to_dict())
        await client.set(f"{self._prefix}job:{job.job_id}", data)

    async def enqueue_dead(self, job: Job) -> None:
        client = await self._ensure_connected()
        import json

        job.status = JobStatus.DEAD
        data = json.dumps(job.to_dict())
        key = f"{self._prefix}dead:{job.job_id}"
        await client.set(key, data)
        await client.rpush(f"{self._prefix}dead_letter", job.job_id)
        count = await client.llen(f"{self._prefix}dead_letter")
        if count > self._max_dead_letter:
            old_id = await client.lpop(f"{self._prefix}dead_letter")
            if old_id:
                await client.delete(f"{self._prefix}dead:{old_id}")

    async def dead_letter_size(self) -> int:
        client = await self._ensure_connected()
        return await client.llen(f"{self._prefix}dead_letter")  # type: ignore[no-any-return]

    async def dead_letter_jobs(self) -> list[Job]:
        client = await self._ensure_connected()
        import json

        ids = await client.lrange(f"{self._prefix}dead_letter", 0, -1)
        jobs: list[Job] = []
        for jid in ids:
            raw = await client.get(f"{self._prefix}dead:{jid}")
            if raw:
                data = json.loads(raw)
                jobs.append(self._reconstruct_job(data))
        return jobs

    async def requeue_dead(self, job_id: str) -> Job | None:
        client = await self._ensure_connected()
        import json

        key = f"{self._prefix}dead:{job_id}"
        raw = await client.get(key)
        if not raw:
            return None
        data = json.loads(raw)
        job = self._reconstruct_job(data)
        job.status = JobStatus.PENDING
        job.retry_count = 0
        job.result = None
        job.started_at = None
        job.finished_at = None
        await client.delete(key)
        await client.lrem(f"{self._prefix}dead_letter", 0, job_id)
        await self.enqueue(job)
        return job

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
        if self._pool:
            await self._pool.disconnect()
        self._client = None
        self._pool = None

    @staticmethod
    def _reconstruct_job(data: dict[str, Any]) -> Job:
        job = Job(
            job_id=data["job_id"],
            queue=data["queue"],
            func_name=data["func_name"],
            args=(),
            kwargs={},
            max_retries=data.get("max_retries", 0),
        )
        job.retry_count = data.get("retry_count", 0)
        job.status = data.get("status", JobStatus.PENDING)
        job.progress = data.get("progress", 0.0)
        job.created_at = data.get("created_at", 0.0)
        job.started_at = data.get("started_at")
        job.finished_at = data.get("finished_at")
        return job


class JobQueue:
    """
    High-level job queue manager.

    Coordinates enqueueing, processing, retries, concurrency,
    dead-letter handling, and progress tracking.
    """

    def __init__(
        self,
        backend: QueueBackend,
        default_retry: int = 3,
        concurrency: int = 10,
        retry_backoff_base: float = 1.0,
    ) -> None:
        self._backend = backend
        self._default_retry = default_retry
        self._concurrency = concurrency
        self._retry_backoff_base = retry_backoff_base
        self._registry: dict[str, Any] = {}
        self._semaphore: asyncio.Semaphore | None = None
        self._running: dict[str, asyncio.Task[None]] = {}
        self._started = False

    @property
    def backend(self) -> QueueBackend:
        return self._backend

    def register(self, func_name: str, func: Any) -> None:
        self._registry[func_name] = func

    async def start(self) -> None:
        self._semaphore = asyncio.Semaphore(self._concurrency)
        self._started = True

    async def stop(self) -> None:
        self._started = False
        for task in self._running.values():
            task.cancel()
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        self._running.clear()
        await self._backend.close()

    async def enqueue(
        self,
        queue: str,
        func_name: str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int | None = None,
    ) -> Job:
        job = Job(
            job_id=uuid.uuid4().hex,
            queue=queue,
            func_name=func_name,
            args=args,
            kwargs=kwargs or {},
            max_retries=max_retries if max_retries is not None else self._default_retry,
        )
        await self._backend.enqueue(job)
        _logger.info("Enqueued job %s on queue '%s'", job.job_id, queue)
        return job

    async def process(self, queue: str) -> None:
        if not self._started or self._semaphore is None:
            return
        while self._started:
            job = await self._backend.dequeue(queue)
            if job is None:
                await asyncio.sleep(0.05)
                continue
            task = asyncio.create_task(self._execute_job(job))
            self._running[job.job_id] = task
            task.add_done_callback(lambda _t, jid=job.job_id: self._running.pop(jid, None))  # type: ignore[misc]

    async def _execute_job(self, job: Job) -> None:
        if self._semaphore is None:
            return
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            job.started_at = time.monotonic()
            await self._backend.update_job(job)

            func = self._registry.get(job.func_name)
            if func is None:
                job.status = JobStatus.FAILED
                job.result = JobResult(error=RuntimeError(f"Job function '{job.func_name}' not registered"))
                job.finished_at = time.monotonic()
                await self._backend.enqueue_dead(job)
                _logger.error("Job %s: function '%s' not registered, sent to DLQ", job.job_id, job.func_name)
                return

            try:
                result = await func(*job.args, **job.kwargs)
                job.status = JobStatus.SUCCESS
                job.result = JobResult(value=result)
                job.finished_at = time.monotonic()
                await self._backend.update_job(job)
                _logger.info("Job %s completed successfully", job.job_id)
            except Exception as exc:
                job.retry_count += 1
                _logger.warning(
                    "Job %s failed (attempt %s/%s): %s",
                    job.job_id,
                    job.retry_count,
                    job.max_retries,
                    exc,
                )
                if job.retry_count < job.max_retries:
                    job.result = JobResult(error=exc)
                    job.status = JobStatus.PENDING
                    job.started_at = None
                    job.finished_at = None
                    await self._backend.update_job(job)
                    delay = self._retry_backoff_base * (2 ** (job.retry_count - 1))
                    await asyncio.sleep(delay)
                    await self._backend.enqueue(job)
                else:
                    job.status = JobStatus.FAILED
                    job.result = JobResult(error=exc)
                    job.finished_at = time.monotonic()
                    await self._backend.enqueue_dead(job)
                    _logger.exception(
                        "Job %s exhausted %s retries, sent to DLQ",
                        job.job_id,
                        job.max_retries,
                    )

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        job = await self._backend.get_job(job_id)
        if job is None:
            return None
        return job.to_dict()

    async def get_queue_size(self, queue: str) -> int:
        return await self._backend.size(queue)

    async def get_dead_letter_jobs(self) -> list[Job]:
        return await self._backend.dead_letter_jobs()

    async def get_dead_letter_size(self) -> int:
        return await self._backend.dead_letter_size()

    async def requeue_dead_letter(self, job_id: str) -> Job | None:
        return await self._backend.requeue_dead(job_id)

    async def update_progress(self, job_id: str, progress: float) -> None:
        job = await self._backend.get_job(job_id)
        if job is not None:
            job.progress = max(0.0, min(1.0, progress))
            await self._backend.update_job(job)

    @property
    def active_count(self) -> int:
        return len(self._running)
