from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional


_RUN_LOG_PATHS_LOCK = Lock()
_RUN_LOG_PATHS: dict[str, "_RunLogInfo"] = {}


@dataclass
class _RunLogInfo:
    plan_id: str
    path: Path
    parent_run_id: Optional[str] = None
    # Per-log-file lock to guarantee atomic append from multiple threads
    lock: Lock = field(default_factory=Lock)
    # Monotonic sequence per event within a run
    seq: int = 0


def register_log_path(run_id: str, plan_id: str, path: Path, parent_run_id: Optional[str] = None) -> None:
    """Register JSONL log file path for a run.

    Enables blocks and utilities to append structured events via run_id.
    Stores parent_run_id and initializes a per-run event sequence counter.
    """
    with _RUN_LOG_PATHS_LOCK:
        _RUN_LOG_PATHS[run_id] = _RunLogInfo(plan_id=plan_id, path=path, parent_run_id=parent_run_id)


def _lookup(run_id: str) -> Optional[_RunLogInfo]:
    with _RUN_LOG_PATHS_LOCK:
        return _RUN_LOG_PATHS.get(run_id)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def write_event(run_id: str, event: Dict[str, Any]) -> None:
    """Append a JSON event to the JSONL file for the given run_id.

    Adds standard fields to every event: ts, plan, run_id, parent_run_id, seq, and schema version.
    """
    info = _lookup(run_id)
    if info is None:
        # If called too early or from an unknown run, silently ignore to avoid crashing user code.
        return
    # Ensure directory exists
    info.path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize writes per log file and assign a monotonic sequence
    with info.lock:
        ev = dict(event)
        info.seq += 1
        ev["seq"] = info.seq
        ev["ts"] = _now_iso()
        ev["plan"] = info.plan_id
        ev["run_id"] = run_id
        ev["parent_run_id"] = info.parent_run_id
        ev["schema"] = "v1"
        line = json.dumps(ev, ensure_ascii=False) + "\n"
        with info.path.open("a", encoding="utf-8") as f:
            f.write(line)


def export_log(
    data: Any,
    *,
    ctx: Optional[Any] = None,
    run_id: Optional[str] = None,
    node_id: Optional[str] = None,
    tag: Optional[str] = None,
    level: str = "debug",
) -> None:
    """Convenience API for blocks/tests to emit ad-hoc debug data into JSONL.

    Usage from a block:
        from core.plan.logger import export_log
        export_log({"some": "data"}, ctx=ctx, tag="parse_result")
    """
    rid = run_id or getattr(ctx, "run_id", None)
    if not isinstance(rid, str) or not rid:
        return
    event: Dict[str, Any] = {
        "type": "debug",
        "level": level,
        "tag": tag,
        "data": data,
    }
    # best-effort node id
    if node_id:
        event["node"] = node_id
    else:
        try:
            nid = None
            if ctx is not None and hasattr(ctx, "vars") and isinstance(ctx.vars, dict):
                nid = ctx.vars.get("__node_id")
            if nid:
                event["node"] = nid
        except Exception:
            pass
    write_event(rid, event)


def log_metric(
    name: str,
    value: Any,
    *,
    ctx: Optional[Any] = None,
    run_id: Optional[str] = None,
    node_id: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None,
) -> None:
    """Record a simple metric as a JSONL event.

    Example:
        log_metric("rows_processed", 123, ctx=ctx, tags={"table": "employees"})
    """
    rid = run_id or getattr(ctx, "run_id", None)
    if not isinstance(rid, str) or not rid:
        return
    event: Dict[str, Any] = {
        "type": "metric",
        "name": name,
        "value": value,
        "tags": tags or {},
        "level": "info",
    }
    if node_id:
        event["node"] = node_id
    write_event(rid, event)


