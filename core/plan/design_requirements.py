# from __future__ import annotations

# from typing import Any, Dict, List

# from core.plan.models import Plan


# Requirement = Dict[str, Any]


# def _require_text(id_: str, label: str, *, required: bool = True, hint: str | None = None) -> Requirement:
#     r: Requirement = {"id": id_, "type": "text", "label": label, "required": required}
#     if hint:
#         r["hint"] = hint
#     return r


# def _require_file(id_: str, label: str, *, accept: str = "", required: bool = True) -> Requirement:
#     r: Requirement = {"id": id_, "type": "file", "label": label, "required": required}
#     if accept:
#         r["accept"] = accept
#     return r


# def build_requirements_from_plan_or_errors(plan: Plan | None, errors: List[str] | None) -> List[Requirement]:
#     """[Disabled] Design QA を使用しないため、常に空リストを返します。"""
#     return []



# def build_requirements_from_overview_dict(overview: Dict[str, Any]) -> List[Requirement]:
#     """[Disabled] Design QA を使用しないため、常に空リストを返します。"""
#     return []


# def build_requirements_from_skeleton_dict(skeleton: Dict[str, Any]) -> List[Requirement]:
#     """[Disabled] Design QA を使用しないため、常に空リストを返します。"""
#     return []
