"""Memory diagnostics helpers for worker loop."""

import gc
import os
import sys
import tracemalloc
from typing import Any

from loguru import logger

# Default memory limit (MB) for threshold calculations; Render free tier is 512
_DEFAULT_MEMORY_LIMIT_MB = 512

# Thresholds as fraction of limit (0.7, 0.85, 0.95)
_THRESHOLD_FRACTIONS = (0.70, 0.85, 0.95)

# Top N allocations to log on threshold crossing
_TRACEMALLOC_TOP_N = 10


def _get_rss_mb() -> float:
    """RSS in MB; 0 if unavailable."""
    try:
        import resource  # Unix only
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux: ru_maxrss in KB; macOS: in bytes
        rss = usage.ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024.0 * 1024.0)
        return rss / 1024.0
    except (ImportError, OSError):
        return 0.0


def _get_gc_counts() -> tuple[int, int, int]:
    """Return gc.get_count() as tuple."""
    return gc.get_count()


def _get_num_threads() -> int:
    """Best-effort process thread count."""
    try:
        import threading
        return len(threading.enumerate())
    except Exception:
        return 0


def _get_open_fds() -> int:
    """Best-effort open fd count on Linux-like systems."""
    try:
        return len(os.listdir("/proc/self/fd"))
    except Exception:
        return 0


def _get_traced_memory_mb() -> tuple[float, float]:
    """Return tracemalloc current/peak MB if tracing; otherwise zeros."""
    if not tracemalloc.is_tracing():
        return (0.0, 0.0)
    current, peak = tracemalloc.get_traced_memory()
    return (round(current / (1024 * 1024), 2), round(peak / (1024 * 1024), 2))


def get_memory_snapshot() -> dict[str, Any]:
    """Best-effort snapshot for correlating process growth."""
    traced_current_mb, traced_peak_mb = _get_traced_memory_mb()
    return {
        "rss_mb": round(_get_rss_mb(), 2),
        "gc_counts": _get_gc_counts(),
        "gc_objects": len(gc.get_objects()),
        "num_threads": _get_num_threads(),
        "open_fds": _get_open_fds(),
        "traced_current_mb": traced_current_mb,
        "traced_peak_mb": traced_peak_mb,
    }


def log_heartbeat(
    *,
    rss_mb: float,
    gc_counts: tuple[int, int, int],
    gc_objects: int,
    num_threads: int,
    open_fds: int,
    traced_current_mb: float,
    traced_peak_mb: float,
    active_msg_id: int | None = None,
    active_run_id: str | None = None,
) -> None:
    """Emit structured heartbeat log."""
    logger.info(
        "worker_memory_heartbeat | rss_mb={} gc_counts={} gc_objects={} num_threads={} "
        "open_fds={} traced_current_mb={} traced_peak_mb={} msg_id={} run_id={}",
        rss_mb,
        gc_counts,
        gc_objects,
        num_threads,
        open_fds,
        traced_current_mb,
        traced_peak_mb,
        active_msg_id,
        active_run_id,
    )


def log_message_delta(
    *,
    mem_before_mb: float,
    mem_after_mb: float,
    msg_id: int,
    run_id: str,
    job_id: str,
    attempt: int,
    result: str,
    error_code: str | None = None,
) -> None:
    """Emit per-message memory delta log."""
    delta = round(mem_after_mb - mem_before_mb, 2)
    logger.info(
        "worker_memory_message_delta | mem_before_mb={} mem_after_mb={} mem_delta_mb={} "
        "msg_id={} run_id={} job_id={} attempt={} result={} error_code={}",
        mem_before_mb,
        mem_after_mb,
        delta,
        msg_id,
        run_id,
        job_id,
        attempt,
        result,
        error_code,
    )


def _format_tracemalloc_top(stats: list[tracemalloc.Statistic]) -> str:
    """Format top allocations for log."""
    lines: list[str] = []
    for i, s in enumerate(stats[:_TRACEMALLOC_TOP_N]):
        size_mb = s.size / (1024 * 1024)
        tb_str = str(s.traceback).replace("\n", " <- ")[:200]
        lines.append(f"  {i+1}. {size_mb:.2f} MB: {tb_str}")
    return "\n".join(lines) if lines else "  (none)"


def maybe_log_high_watermark(
    rss_mb: float,
    memory_limit_mb: float,
    crossed: set[float],
    msg_id: int | None,
    run_id: str | None,
    include_tracemalloc_snapshot: bool = True,
) -> set[float]:
    """
    If RSS crosses a threshold fraction, log once per threshold.
    Returns updated set of crossed thresholds.
    """
    new_crossed = set(crossed)
    for frac in _THRESHOLD_FRACTIONS:
        threshold_mb = memory_limit_mb * frac
        if rss_mb >= threshold_mb and frac not in crossed:
            new_crossed.add(frac)
            _emit_high_watermark_log(
                rss_mb=rss_mb,
                threshold_frac=frac,
                threshold_mb=threshold_mb,
                msg_id=msg_id,
                run_id=run_id,
                include_tracemalloc_snapshot=include_tracemalloc_snapshot,
            )
    return new_crossed


def _emit_high_watermark_log(
    *,
    rss_mb: float,
    threshold_frac: float,
    threshold_mb: float,
    msg_id: int | None,
    run_id: str | None,
    include_tracemalloc_snapshot: bool,
) -> None:
    """Emit one-time snapshot when crossing threshold."""
    top_stats = ""
    if include_tracemalloc_snapshot and tracemalloc.is_tracing():
        snapshot = tracemalloc.take_snapshot()
        top = snapshot.statistics("lineno")
        top_stats = _format_tracemalloc_top(top)
    elif not include_tracemalloc_snapshot:
        top_stats = "  (tracemalloc snapshot disabled)"
    else:
        top_stats = "  (tracemalloc not started)"
    logger.warning(
        "worker_memory_high_watermark | rss_mb={} threshold_pct={} threshold_mb={} "
        "msg_id={} run_id={} | top_allocations:\n{}",
        rss_mb,
        int(threshold_frac * 100),
        threshold_mb,
        msg_id,
        run_id,
        top_stats,
    )


def start_tracemalloc_if_enabled(enabled: bool) -> None:
    """Start tracemalloc when explicitly enabled."""
    if enabled:
        if not tracemalloc.is_tracing():
            tracemalloc.start()
            logger.info("worker_memory_tracemalloc_started")


def parse_memory_limit_mb(raw: str) -> float:
    """Parse WORKER_MEMORY_LIMIT_MB env; default 512."""
    if not raw or not raw.strip():
        return float(_DEFAULT_MEMORY_LIMIT_MB)
    try:
        v = float(raw.strip())
        return max(1.0, v)
    except ValueError:
        return float(_DEFAULT_MEMORY_LIMIT_MB)


def parse_diagnostics_enabled(raw: str) -> bool:
    """Parse WORKER_MEMORY_DIAGNOSTICS_ENABLED env; default 0 (off)."""
    if not raw or not raw.strip():
        return False
    return raw.strip().lower() in ("1", "true", "yes")


def parse_tracemalloc_enabled(raw: str) -> bool:
    """Parse WORKER_MEMORY_TRACEMALLOC_ENABLED env; default 0 (off)."""
    if not raw or not raw.strip():
        return False
    return raw.strip().lower() in ("1", "true", "yes")


def parse_heartbeat_interval_seconds(raw: str) -> float:
    """Parse WORKER_MEMORY_HEARTBEAT_INTERVAL_SECONDS; default 60."""
    if not raw or not raw.strip():
        return 60.0
    try:
        v = float(raw.strip())
        return max(5.0, v)
    except ValueError:
        return 60.0
