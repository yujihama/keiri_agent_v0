from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv  # type: ignore


def has_llm_keys() -> bool:
    """Return True if environment has LLM API keys configured."""
    load_dotenv()
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))


def latest_artifacts_dir(base_output: Path, plan_id: str) -> Path:
    """Resolve the latest artifacts directory for a given plan id under base_output.

    Expect structure: base_output/<plan_id>/<timestamp>/artifacts
    """
    plan_dir = base_output / plan_id
    assert plan_dir.exists(), f"plan output dir not found: {plan_dir}"
    run_dirs = [d for d in plan_dir.iterdir() if d.is_dir()]
    assert run_dirs, f"no run dirs under: {plan_dir}"
    run_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return run_dirs[0] / "artifacts"


def inject_fastpath_for_llm(plan: Any, node_outputs: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Inject evidence_data.answer into ai.process_llm nodes to avoid external API calls.

    node_outputs: optional mapping of node.id -> results object that will be wrapped under
    top-level key "results". If omitted, an empty object is used.
    """
    node_outputs = node_outputs or {}

    for node in getattr(plan, "graph", []) or []:
        try:
            if getattr(node, "block", "") == "ai.process_llm":
                inputs: Dict[str, Any] = dict(getattr(node, "inputs", {}))
                evidence: Dict[str, Any] = dict(inputs.get("evidence_data") or {})
                results_obj = node_outputs.get(node.id) or {}
                evidence["answer"] = __to_json_string({"results": results_obj})
                inputs["evidence_data"] = evidence
                node.inputs = inputs
            # descend into loop body if present
            if getattr(node, "type", "") == "loop" and getattr(node, "body", None) and getattr(node.body, "plan", None):
                inject_fastpath_for_llm(node.body.plan, node_outputs)
        except Exception:
            continue


def __to_json_string(obj: Dict[str, Any]) -> str:
    # simple local import to avoid hard dependency in test import graph
    import json  # noqa: WPS433

    return json.dumps(obj, ensure_ascii=False)







