from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


def as_event_dict(obj: Any) -> Dict[str, Any]:
    try:
        return asdict(obj)
    except Exception:
        # Fallback for plain dicts
        return dict(obj)  # type: ignore[arg-type]


@dataclass
class StartEvent:
    type: str = "start"
    run_id: str = ""
    plan: str = ""
    parent_run_id: Optional[str] = None
    plan_spec: Optional[Dict[str, Any]] = None


@dataclass
class NodeFinishEvent:
    type: str = "node_finish"
    node: str = ""
    elapsed_ms: int = 0
    attempts: int = 1


@dataclass
class ErrorEvent:
    type: str = "error"
    node: str = ""
    attempt: int = 1
    message: str = ""
    error_code: str = "Exception"
    recoverable: bool = False
    error_details: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class ScheduleLevelEvent:
    type: str = "schedule_level_start"
    nodes: List[str] = None  # type: ignore[assignment]


@dataclass
class ScheduleLevelFinishEvent:
    type: str = "schedule_level_finish"
    executed: List[str] = None  # type: ignore[assignment]
    leftover: List[str] = None  # type: ignore[assignment]


@dataclass
class FinishSummaryEvent:
    type: str = "finish_summary"
    total_nodes: int = 0
    success_nodes: int = 0
    skipped_nodes: int = 0
    error_nodes: int = 0
    total_elapsed_ms: int = 0
    total_retries: int = 0


