from __future__ import annotations

import json
import os
import subprocess
import stat
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


def _get_desired_log_mode() -> int:
    """Resolve desired file mode for JSONL logs.

    - Uses env `KEIRI_LOG_FILE_MODE` if set (accepts forms like "664", "0o664").
    - Defaults to 0o664 (rw-rw-r--).
    """
    v = os.getenv("KEIRI_LOG_FILE_MODE")
    if v:
        try:
            sv = v.strip().lower()
            # If explicit base prefix provided, respect it via base=0
            if sv.startswith(("0o", "0x", "0b", "0")):
                return int(v, 0)
            # Otherwise, interpret as octal like chmod notation (e.g., "664")
            return int(v, 8)
        except Exception:
            pass
    return 0o664


def _apply_windows_acl(target: Path) -> None:
    """Optionally widen ACLs on Windows using icacls if KEIRI_LOG_ACL_SPEC is set.

    Example: KEIRI_LOG_ACL_SPEC="Users:(R)" or "Everyone:(R)".
    """
    spec = os.getenv("KEIRI_LOG_ACL_SPEC")
    if not spec:
        return
    try:
        subprocess.run([
            "icacls",
            str(target),
            "/grant",
            spec,
        ], check=False, capture_output=True)
    except Exception:
        pass


def _set_file_permissions(path: Path) -> None:
    """Best-effort permission setting for created JSONL files.

    - POSIX: chmod to desired mode (default 0o664 unless env overrides)
    - Windows: use icacls when KEIRI_LOG_ACL_SPEC is set; otherwise set RW attribute
    """
    try:
        if os.name == "nt":
            _apply_windows_acl(path)
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        else:
            os.chmod(path, _get_desired_log_mode())
    except Exception:
        pass


def _set_dir_permissions(path: Path) -> None:
    """Best-effort permission setting for directory containing logs.

    - POSIX: chmod 0o775 to allow group traverse/read.
    - Windows: use icacls when KEIRI_LOG_ACL_SPEC is set.
    """
    try:
        if os.name == "nt":
            _apply_windows_acl(path)
        else:
            os.chmod(path, 0o775)
    except Exception:
        pass


def register_log_path(run_id: str, plan_id: str, path: Path, parent_run_id: Optional[str] = None) -> None:
    """Register JSONL log file path for a run.

    Enables blocks and utilities to append structured events via run_id.
    Stores parent_run_id and initializes a per-run event sequence counter.
    """
    with _RUN_LOG_PATHS_LOCK:
        _RUN_LOG_PATHS[run_id] = _RunLogInfo(plan_id=plan_id, path=path, parent_run_id=parent_run_id)
    # Ensure file exists and adjust permissions immediately upon registration
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_dir_permissions(path.parent)
        if not path.exists():
            path.touch(exist_ok=True)
        _set_file_permissions(path)
    except Exception:
        # Best-effort; logging should proceed even if this step fails
        pass


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


# ------------------ Introspection helpers (for UI) ------------------
def get_log_path_for_run(run_id: str) -> Optional[Path]:
    """Return the JSONL log path for a given run_id if registered in-process.

    UI から最新実行のログファイルを開く用途。プロセス内で登録済みの
    ランに対してのみ有効（プロセス再起動後は None）。
    """
    info = _lookup(run_id)
    return info.path if info else None


def get_plan_id_for_run(run_id: str) -> Optional[str]:
    """Return the plan id for a given run_id if available."""
    info = _lookup(run_id)
    return info.plan_id if info else None

