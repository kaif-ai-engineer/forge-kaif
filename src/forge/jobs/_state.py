from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from forge.jobs.queue import JobQueue

_module: JobQueue | None = None


def get_job_queue() -> JobQueue | None:
    return _module


def set_job_queue(module: JobQueue | None) -> None:
    global _module  # noqa: PLW0603
    _module = module
