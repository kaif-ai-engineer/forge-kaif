from __future__ import annotations

import random
from collections.abc import Callable

BackoffFn = Callable[[int], float]
"""Signature: ``(attempt: int) -> delay_seconds: float``.

*attempt* is 1-indexed (the first retry is attempt 1).
"""


def exponential(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Exponential backoff with full jitter.

    Delay = ``U(0, min(base_delay * 2 ** (attempt - 1), max_delay))``
    """
    cap = min(base_delay * 2.0 ** (attempt - 1), max_delay)
    return random.uniform(0.0, cap)  # noqa: S311


def linear(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Linear backoff.

    Delay = ``min(base_delay * attempt, max_delay)``
    """
    return min(base_delay * attempt, max_delay)


def constant(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:  # noqa: ARG001
    """Constant backoff — always returns *base_delay*."""
    return base_delay


_STRATEGIES: dict[str, BackoffFn] = {
    "exponential": exponential,
    "linear": linear,
    "constant": constant,
}


def get_backoff(name: str) -> BackoffFn:
    """
    Return the backoff function for the given strategy *name*.

    Raises ``ValueError`` for unknown strategies.
    """
    fn = _STRATEGIES.get(name)
    if fn is None:
        raise ValueError(f"Unknown backoff strategy {name!r}. Choose from {list(_STRATEGIES)}.")
    return fn
