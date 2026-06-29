"""
Background jobs and scheduling module.

Provides queue-backed async job execution with automatic retry,
concurrency control, dead-letter queue, progress tracking, and
cron-like scheduled tasks.

Usage::

    from forge.jobs import job, schedule, JobsModule

    @job(queue="emails", retry=3)
    async def send_welcome_email(user_id: int):
        ...

    await send_welcome_email.enqueue(user_id=123)

    @schedule(cron="0 9 * * *")
    async def daily_report():
        ...
"""

from forge.jobs.module import (
    JobDefinition,
    JobsModule,
    ScheduleDefinition,
    job,
    schedule,
)
from forge.jobs.queue import (
    Job,
    JobQueue,
    JobResult,
    JobStatus,
    MemoryBackend,
    QueueBackend,
    RedisBackend,
)
from forge.jobs.scheduler import CronExpression, ScheduledJob, Scheduler

__all__ = [
    "CronExpression",
    "Job",
    "JobDefinition",
    "JobQueue",
    "JobResult",
    "JobStatus",
    "JobsModule",
    "MemoryBackend",
    "QueueBackend",
    "RedisBackend",
    "ScheduleDefinition",
    "ScheduledJob",
    "Scheduler",
    "job",
    "schedule",
]
