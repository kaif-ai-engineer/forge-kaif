"""Compare benchmark results against thresholds and detect regressions."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

LOG_COUNT = 100_000
RETRY_CALLS = 5_000

BenchSpec = dict[str, float | str | None]

BENCH_SPECS: dict[str, BenchSpec] = {
    "test_runtime_init_time": {
        "label": "Runtime init (5 modules)",
        "threshold": 200,
        "unit": "ms",
        "agg": "total",
    },
    "test_config_load_time": {
        "label": "Config load",
        "threshold": 50,
        "unit": "ms",
        "agg": "total",
    },
    "test_log_throughput": {
        "label": "Log throughput",
        "threshold": 25_000,
        "unit": "logs/s",
        "agg": "throughput",
        "factor": LOG_COUNT,
    },
    "test_retry_overhead": {
        "label": "Retry overhead",
        "threshold": 1,
        "unit": "ms/call",
        "agg": "per_call",
        "calls": RETRY_CALLS,
    },
    "test_health_check_response": {
        "label": "Health check",
        "threshold": 100,
        "unit": "ms",
        "agg": "total",
    },
    "test_ai_overhead": {
        "label": "AI module overhead",
        "threshold": 5,
        "unit": "ms",
        "agg": "total",
    },
}


def _compute(mean: float, spec: BenchSpec) -> tuple[float, str]:
    """Compute the display value and get the comparable number."""
    agg: str = spec["agg"]  # type: ignore[assignment]
    if agg == "throughput":
        factor: float = spec["factor"]  # type: ignore[typeddict-item]
        value = factor / mean if mean > 0 else 0
        return value, f"{value:,.0f}{spec['unit']}"
    if agg == "per_call":
        calls: float = spec["calls"]  # type: ignore[typeddict-item]
        value = (mean / calls) * 1000  # ms per call
        return value, f"{value:.4f}{spec['unit']}"
    value = mean * 1000  # ms
    return value, f"{value:.2f}{spec['unit']}"


def _compute_prev(mean: float, spec: BenchSpec) -> float:
    """Compute the comparable baseline value."""
    agg: str = spec["agg"]  # type: ignore[assignment]
    if agg == "throughput":
        factor: float = spec["factor"]  # type: ignore[typeddict-item]
        return factor / mean if mean > 0 else 0
    if agg == "per_call":
        calls: float = spec["calls"]  # type: ignore[typeddict-item]
        return (mean / calls) * 1000
    return mean * 1000


def main() -> int:
    report_path = Path(sys.argv[1])
    with open(report_path) as f:
        data = json.load(f)

    benchmarks: list[dict] = data.get("benchmarks", [])
    if not benchmarks:
        print("No benchmark results found")
        return 1

    regression = False
    results: list[str] = []
    results.append("## Benchmark Results\n")
    results.append("| Benchmark | Result | Threshold | Status |")
    results.append("|-----------|--------|-----------|--------|")

    baseline_path = Path(".benchmarks/baseline.json")
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}

    for bench in benchmarks:
        name: str = bench.get("name", "unknown")
        raw_mean: float = bench.get("stats", {}).get("mean", 0)
        spec = BENCH_SPECS.get(name)

        if spec is None:
            results.append(f"| `{name}` | {raw_mean * 1000:.2f}ms | — | ❓ |")
            continue

        label: str = spec["label"]  # type: ignore[assignment]
        threshold: float = spec["threshold"]  # type: ignore[assignment]
        agg: str = spec["agg"]  # type: ignore[assignment]

        value, display = _compute(raw_mean, spec)

        if raw_mean > 0:
            passed = value > threshold if agg == "throughput" else value < threshold
            status = "✅ PASS" if passed else "❌ FAIL"
            if not passed:
                regression = True
        else:
            status = "❓"

        prev_raw = baseline.get(name)
        reg = ""
        if prev_raw is not None and prev_raw > 0 and raw_mean > 0:
            prev_val = _compute_prev(prev_raw, spec)
            change = ((value - prev_val) / prev_val) * 100
            is_regression = (change > 0 and agg != "throughput") or (
                change < 0 and agg == "throughput"
            )
            if abs(change) > 10:
                icon = "⚠️" if is_regression else "✅"
                reg = f" {icon} {change:+.1f}%"
                if is_regression:
                    regression = True

        results.append(f"| **{label}** | {display} | {threshold} | {status}{reg} |")

    print("\n".join(results))

    if regression:
        print("\n⚠️ Performance regression detected (>10% degradation).")
        print("Add the `benchmark-approved` label to override.")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"regression={str(regression).lower()}\n")
            f.write(f"report={'%0A'.join(results)}\n")

    return 1 if regression else 0


if __name__ == "__main__":
    sys.exit(main())
