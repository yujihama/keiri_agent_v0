from __future__ import annotations

from typing import Any, Dict
from datetime import datetime, timezone, timedelta

from croniter import croniter

from core.blocks.base import BlockContext, ProcessingBlock


class SchedulerTriggerBlock(ProcessingBlock):
    id = "scheduler.trigger"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        schedule = inputs.get("schedule") or {}
        start_from = inputs.get("start_from")
        jitter_sec = int(inputs.get("jitter_sec", 0))

        now = datetime.now(timezone.utc)
        base = now
        if isinstance(start_from, str):
            try:
                base = datetime.fromisoformat(start_from.replace("Z", "+00:00"))
            except Exception:
                base = now

        triggered = False
        next_run_at = None

        if isinstance(schedule, dict) and schedule.get("cron"):
            itr = croniter(str(schedule.get("cron")), base)
            next_dt = itr.get_next(datetime)
            if jitter_sec:
                # do not actually sleep; just record window
                pass
            # Simple heuristic: trigger if base >= now (always true here in batch), expose next
            triggered = True
            next_run_at = next_dt.astimezone(timezone.utc).isoformat()
        elif isinstance(schedule, dict) and schedule.get("interval_sec"):
            triggered = True
            next_dt = base + timedelta(seconds=int(schedule.get("interval_sec")))  # type: ignore[name-defined]
            next_run_at = next_dt.astimezone(timezone.utc).isoformat()
        else:
            triggered = True
            next_run_at = None

        return {"triggered": bool(triggered), "next_run_at": next_run_at}


