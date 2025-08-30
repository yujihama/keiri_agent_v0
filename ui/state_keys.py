from __future__ import annotations


class SessionKeys:
    execute_requested: str = "execute_requested"
    allow_pending_ui_render: str = "allow_pending_ui_render"
    run_in_progress: str = "run_in_progress"
    auto_resume_run_id: str = "auto_resume_run_id"
    last_run_id: str = "last_run_id"

    @staticmethod
    def flow_success(plan_id: str) -> str:
        return f"flow_success::{plan_id}"

    @staticmethod
    def flow_last_render(plan_id: str) -> str:
        return f"flow_last_render::{plan_id}"


