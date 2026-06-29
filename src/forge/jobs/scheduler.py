from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

_logger = logging.getLogger(__name__)


class CronExpression:
    """
    Standard five-field cron expression parser.

    Fields: minute hour day-of-month month day-of-week

    Supported syntax:
    - ``*`` — any value
    - ``5`` — exact value
    - ``1,15`` — list of values
    - ``1-5`` — range (inclusive)
    - ``*/15`` — step (every N)
    - ``0 9 * * *`` — daily at 09:00
    - ``*/5 * * * 1-5`` — every 5 minutes on weekdays
    """

    MONTH_NAMES: ClassVar[dict[str, int]] = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4,
        "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }
    DOW_NAMES: ClassVar[dict[str, int]] = {
        "SUN": 0, "MON": 1, "TUE": 2, "WED": 3,
        "THU": 4, "FRI": 5, "SAT": 6,
    }

    _CRON_FIELD_COUNT = 5
    _MONTH_MAX = 12
    _DOW_MAX = 6

    def __init__(self, expression: str) -> None:
        self._raw = expression
        parts = expression.strip().split()
        if len(parts) != self._CRON_FIELD_COUNT:
            raise ValueError(
                f"Cron expression must have {self._CRON_FIELD_COUNT} fields, got {len(parts)}: '{expression}'"
            )
        self._minute = self._parse_field(parts[0], 0, 59)
        self._hour = self._parse_field(parts[1], 0, 23)
        self._dom = self._parse_field(parts[2], 1, 31)
        self._month = self._parse_field(parts[3], 1, 12)
        self._dow = self._parse_field(parts[4], 0, 6)

    def matches(self, dt: datetime) -> bool:
        dow = (dt.weekday() + 1) % 7
        return (
            dt.minute in self._minute
            and dt.hour in self._hour
            and dt.day in self._dom
            and dt.month in self._month
            and dow in self._dow
        )

    def next_after(self, dt: datetime) -> datetime:
        candidate = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(525600):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise RuntimeError(f"No matching time found for cron '{self._raw}' within 1 year")

    def _parse_field(self, field: str, min_val: int, max_val: int) -> set[int]:
        result: set[int] = set()
        for part in field.split(","):
            result |= self._parse_part(part.strip(), min_val, max_val)
        return result

    def _parse_part(self, part: str, min_val: int, max_val: int) -> set[int]:
        base_min, base_max = min_val, max_val

        part = part.upper()
        if min_val == 1 and max_val == self._MONTH_MAX:
            for name, val in self.MONTH_NAMES.items():
                part = part.replace(name, str(val))
        if min_val == 0 and max_val == self._DOW_MAX:
            for name, val in self.DOW_NAMES.items():
                part = part.replace(name, str(val))
            part = part.replace("7", "0")

        step = 1
        if "/" in part:
            range_part, step_str = part.split("/", 1)
            step = int(step_str)
            part = range_part

        if part == "*":
            return set(range(base_min, base_max + 1, step))

        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            return set(range(start, end + 1, step))

        value = int(part)
        if step > 1:
            return set(range(value, max_val + 1, step))
        return {value}

    def __repr__(self) -> str:
        return f"CronExpression({self._raw!r})"


class ScheduledJob:
    """A job that runs on a cron schedule."""

    def __init__(
        self,
        name: str,
        cron: CronExpression,
        func: Callable[..., Any],
        queue: str = "scheduled",
    ) -> None:
        self.name = name
        self.cron = cron
        self.func = func
        self.queue = queue
        self.last_run: datetime | None = None
        self.next_run: datetime | None = None
        self.run_count: int = 0
        self.last_error: str | None = None


class Scheduler:
    """
    Cron-like scheduler that evaluates scheduled jobs at minute boundaries.

    Runs a loop that checks every ~1 second whether the current minute
    matches any registered schedule and executes matching jobs.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, ScheduledJob] = {}
        self._running: dict[str, asyncio.Task[None]] = {}
        self._started = False

    def register(
        self,
        name: str,
        cron_expression: str,
        func: Callable[..., Any],
        queue: str = "scheduled",
    ) -> ScheduledJob:
        cron = CronExpression(cron_expression)
        job = ScheduledJob(name=name, cron=cron, func=func, queue=queue)
        self._jobs[name] = job
        return job

    async def start(self) -> None:
        self._started = True
        _logger.info("Scheduler started with %d job(s)", len(self._jobs))
        _last_minute: int = -1
        try:
            while self._started:
                now = datetime.now(tz=UTC)
                current_minute = now.minute + now.hour * 60 + now.day * 60 * 24
                if current_minute != _last_minute:
                    _last_minute = current_minute
                    await self._check_and_fire(now)
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        self._started = False
        for task in self._running.values():
            task.cancel()
        if self._running:
            await asyncio.gather(*self._running.values(), return_exceptions=True)
        self._running.clear()
        _logger.info("Scheduler stopped")

    async def _check_and_fire(self, now: datetime) -> None:
        _min_dedup_seconds = 60
        for job in self._jobs.values():
            if not job.cron.matches(now):
                continue
            if job.last_run is not None:
                since_last = (now - job.last_run).total_seconds()
                if since_last < _min_dedup_seconds:
                    continue
            task = asyncio.create_task(self._run_scheduled(job))
            self._running[job.name] = task
            task.add_done_callback(lambda _t, n=job.name: self._running.pop(n, None))  # type: ignore[misc]

    async def _run_scheduled(self, job: ScheduledJob) -> None:
        now = datetime.now(tz=UTC)
        job.last_run = now
        job.next_run = job.cron.next_after(now)
        try:
            result = job.func()
            if asyncio.iscoroutine(result):
                await result
            job.run_count += 1
            job.last_error = None
            _logger.info("Scheduled job '%s' completed (run #%d)", job.name, job.run_count)
        except Exception as exc:
            job.last_error = str(exc)
            _logger.exception("Scheduled job '%s' failed", job.name)

    @property
    def jobs(self) -> dict[str, ScheduledJob]:
        return dict(self._jobs)

    def get_status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": job.name,
                "cron": job.cron._raw,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "run_count": job.run_count,
                "last_error": job.last_error,
            }
            for job in self._jobs.values()
        ]
