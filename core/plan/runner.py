from __future__ import annotations

import json
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import ast
from datetime import datetime, UTC
import os
from pathlib import Path
from typing import Any, Dict, List, Callable, Optional
import threading
from time import perf_counter
import traceback
import base64

import networkx as nx

from core.blocks.base import BlockContext, ProcessingBlock, UIBlock
from core.blocks.registry import BlockRegistry
from core.errors import BlockException
from .models import Node, Plan
from .config_store import get_store
from .logger import register_log_path, write_event, export_log
from .events import (
    as_event_dict,
    StartEvent,
    NodeFinishEvent,
    ErrorEvent,
    ScheduleLevelEvent,
    ScheduleLevelFinishEvent,
    FinishSummaryEvent,
)


def _now_ts() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")


class PlanRunner:
    def __init__(
        self,
        registry: BlockRegistry,
        runs_dir: str | Path = "runs",
        default_ui_hitl: bool = False,
    ) -> None:
        self.registry = registry
        self.runs_dir = Path(runs_dir)
        self._log_lock = threading.Lock()
        self._state_dir = self.runs_dir  # reuse runs dir
        self.default_ui_hitl = default_ui_hitl

    def _make_run_log_path(self, plan: Plan) -> Path:
        plan_dir = self.runs_dir / plan.id
        plan_dir.mkdir(parents=True, exist_ok=True)
        return plan_dir / f"{_now_ts()}.jsonl"

    def _state_path(self, plan_id: str, run_id: str) -> Path:
        d = self._state_dir / plan_id
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{run_id}.state.json"

    def _save_state(self, plan: Plan, run_id: str, state: Dict[str, Any]) -> None:
        path = self._state_path(plan.id, run_id)
        def _default(o):
            try:
                import base64  # local import to avoid global dependency
                if isinstance(o, (bytes, bytearray)):
                    return {"__type": "b64bytes", "data": base64.b64encode(bytes(o)).decode("ascii")}
            except Exception:
                pass
            raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")
        with self._log_lock:
            path.write_text(json.dumps(state, ensure_ascii=False, default=_default), encoding="utf-8")

    def _load_state(self, plan: Plan, run_id: str) -> Dict[str, Any] | None:
        path = self._state_path(plan.id, run_id)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    # ------------------ Public State API (P0) ------------------
    def get_state(self, plan_id: str, run_id: str) -> Dict[str, Any] | None:
        """Public: Get state dict for plan_id/run_id."""
        path = self._state_path(plan_id, run_id)
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def save_state(self, plan_id: str, run_id: str, state: Dict[str, Any]) -> None:
        """Public: Save state dict for plan_id/run_id."""
        path = self._state_path(plan_id, run_id)
        with self._log_lock:
            path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def clear_state_files(self, plan_id: str) -> None:
        """Public: Remove saved state files for a plan."""
        d = self._state_dir / plan_id
        if not d.exists():
            return
        for f in d.glob("*.state.json"):
            try:
                f.unlink()
            except Exception:
                continue

    def find_latest_pending_ui(self, plan_id: str, prefer_run_id: Optional[str] = None) -> tuple[Dict[str, Any] | None, Optional[str]]:
        """Public: Find latest pending UI entry for a plan.

        Returns: (pending_ui_dict or None, run_id or None)
        """
        d = self._state_dir / plan_id
        # Prefer explicit run_id
        if prefer_run_id and d.exists():
            f = d / f"{prefer_run_id}.state.json"
            if f.exists():
                try:
                    stv = json.loads(f.read_text(encoding="utf-8"))
                    cand = stv.get("pending_ui")
                    if cand and not cand.get("submitted"):
                        return cand, prefer_run_id
                except Exception:
                    pass
        # Fallback: newest unsubmitted
        if d.exists():
            files = sorted(d.glob("*.state.json"), reverse=True)
            for f in files:
                try:
                    stv = json.loads(f.read_text(encoding="utf-8"))
                    cand = stv.get("pending_ui")
                    if cand and not cand.get("submitted"):
                        return cand, f.stem.replace(".state", "")
                except Exception:
                    continue
        return None, None

    # ------------------ Internal helpers ------------------
    def _record_success(self, plan: Plan, run_id: str, node_id: str) -> None:
        """Record a node id into success_nodes in state."""
        try:
            cur = self._load_state(plan, run_id) or {}
            succ = cur.get("success_nodes")
            if isinstance(succ, list):
                sset = set(str(x) for x in succ)
            else:
                sset = set()
            sset.add(str(node_id))
            cur["success_nodes"] = sorted(list(sset))
            self._save_state(plan, run_id, cur)
        except Exception:
            pass

    # _write_event was deprecated in favor of core.plan.logger.write_event and has been removed.

    def run(
        self,
        plan: Plan,
        vars_overrides: Dict[str, Any] | None = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent_run_id: Optional[str] = None,
        resume_run_id: Optional[str] = None,
        execution_context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if resume_run_id:
            run_id = resume_run_id
        else:
            run_id = f"{parent_run_id}#{_now_ts()}" if parent_run_id else _now_ts()
        ctx = BlockContext(run_id=run_id, workspace=str(Path.cwd()), vars=dict(plan.vars))
        # Embed plan id for downstream utilities that rely on it
        try:
            ctx.vars["__plan_id"] = plan.id
        except Exception:
            pass
        if vars_overrides:
            ctx.vars.update(vars_overrides)

        log_path = self._make_run_log_path(plan)
        # Register path so blocks/utilities can export_log with this run_id
        register_log_path(run_id, plan.id, log_path)
        def emit(event: Dict[str, Any]) -> None:
            write_event(run_id, event)
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    # UI callback errors must not break the runner
                    pass

        # start イベントに実行時の Plan 定義を埋め込み、後段のログ可視化で確実に復元できるようにする
        try:
            plan_spec = plan.model_dump(by_alias=True)
        except Exception:
            plan_spec = None
        emit(as_event_dict(StartEvent(run_id=run_id, plan=plan.id, parent_run_id=parent_run_id, plan_spec=plan_spec)))

        # Summarizer for debug logging to avoid dumping raw bytes/huge payloads
        def _summarize_for_log(value: Any, depth: int = 0) -> Any:
            try:
                if depth > 3:
                    return "<depth_limit>"
                if isinstance(value, (bytes, bytearray)):
                    return {"__type": "bytes", "len": len(value)}
                if isinstance(value, str):
                    s = value
                    return s if len(s) <= 200 else (s[:200] + "…")
                if isinstance(value, dict):
                    out: Dict[str, Any] = {}
                    cnt = 0
                    for k, v in value.items():
                        out[str(k)] = _summarize_for_log(v, depth + 1)
                        cnt += 1
                        if cnt >= 50:
                            out["__truncated__"] = True
                            break
                    return out
                if isinstance(value, (list, tuple)):
                    arr = []
                    for i, v in enumerate(value):
                        if i >= 50:
                            arr.append("<truncated>")
                            break
                        arr.append(_summarize_for_log(v, depth + 1))
                    return arr
                return value
            except Exception:
                return "<unserializable>"

        # Artifacts saving helpers (headless mode)
        def _artifacts_base_dir() -> Path:
            try:
                if execution_context and getattr(execution_context, "output_dir", None):
                    return Path(getattr(execution_context, "output_dir")) / plan.id / run_id / "artifacts"
            except Exception:
                pass
            return (self.runs_dir / plan.id / run_id / "artifacts")

        def _ensure_dir(p: Path) -> Path:
            p.mkdir(parents=True, exist_ok=True)
            return p

        def _safe_filename(name: str) -> str:
            try:
                # remove dangerous chars
                invalid = '<>:"/\\|?*\n\r\t'
                out = "".join(c for c in str(name) if c not in invalid)
                return out.strip() or "artifact.bin"
            except Exception:
                return "artifact.bin"

        def _write_bytes(path: Path, data: bytes) -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return path

        def _try_decode_b64(s: str) -> bytes | None:
            try:
                return base64.b64decode(s)
            except Exception:
                return None

        def _save_node_outputs(node_id: str, out: Dict[str, Any]) -> None:
            # Only in headless mode
            if not (execution_context and getattr(execution_context, "headless_mode", False)):
                return
            base_dir = _ensure_dir(_artifacts_base_dir())
            # Always save JSON snapshot (bytes will be base64-encoded)
            def _encode_for_json(v: Any) -> Any:
                try:
                    if isinstance(v, (bytes, bytearray)):
                        return {"__type": "b64bytes", "data": base64.b64encode(bytes(v)).decode("ascii")}
                    if isinstance(v, dict):
                        return {kk: _encode_for_json(vv) for kk, vv in v.items()}
                    if isinstance(v, list):
                        return [_encode_for_json(x) for x in v]
                    return v
                except Exception:
                    return str(v)
            try:
                encoded = _encode_for_json(out)
                (base_dir / f"{node_id}_outputs.json").write_text(
                    json.dumps(encoded, ensure_ascii=False), encoding="utf-8"
                )
            except Exception:
                pass
            # Extract and save binary-like artifacts
            def _walk(current: Any, prefix: str = "") -> None:
                if isinstance(current, dict):
                    # Pattern 1: dict with bytes
                    if "bytes" in current and isinstance(current.get("bytes"), (bytes, bytearray)):
                        raw: bytes = bytes(current["bytes"])  # type: ignore[arg-type]
                        name = current.get("name") or f"{prefix or 'artifact'}"
                        fname = _safe_filename(str(name))
                        _write_bytes(base_dir / fname, raw)
                        return
                    # Pattern 2: dict with base64
                    if "base64" in current and isinstance(current.get("base64"), str):
                        b = _try_decode_b64(current["base64"])  # type: ignore[arg-type]
                        if b is not None:
                            name = current.get("name") or f"{prefix or 'artifact'}.bin"
                            fname = _safe_filename(str(name))
                            _write_bytes(base_dir / fname, b)
                            return
                    # Recurse
                    for k, v in current.items():
                        new_pref = f"{prefix}_{k}" if prefix else str(k)
                        _walk(v, new_pref)
                    return
                if isinstance(current, list):
                    for idx, v in enumerate(current):
                        _walk(v, f"{prefix}_{idx}" if prefix else str(idx))
                    return
                # Pattern 3: plain base64 string with typical suffix key handled by parent dict
                return

            try:
                _walk(out, prefix=str(node_id))
            except Exception:
                pass

        # Build DAG from placeholders (shared utility)
        from .graph_utils import build_dependency_graph
        g = build_dependency_graph(plan)
        order = list(nx.topological_sort(g))

        results_by_alias: Dict[str, Any] = {}
        results_by_node: Dict[str, Dict[str, Any]] = {}

        # Build helper maps
        node_by_id: Dict[str, Node] = {n.id: n for n in plan.graph}

        # Helper to resolve an input value (top-level)
        def resolve(value: Any) -> Any:
            if not isinstance(value, str) or not (value.startswith("${") and value.endswith("}")):
                return value
            inner = value[2:-1]
            if inner.startswith("vars."):
                # Support nested path: vars.a.b.c ; Do NOT coerce non-literal types
                path = inner.split(".", 1)[1]
                cur: Any = ctx.vars
                for seg in path.split("."):
                    if isinstance(cur, dict) and seg in cur:
                        cur = cur[seg]
                    else:
                        cur = None
                        break
                return cur
            if inner.startswith("env."):
                _, key = inner.split(".", 1)
                return os.environ.get(key)
            if inner.startswith("config."):
                # Resolve from configuration store (${config.namespace.path})
                dotted = inner.split(".", 1)[1] if "." in inner else ""
                try:
                    return get_store().resolve(dotted)
                except Exception:
                    return None
            # nodeId.something (outputKey or alias, possibly nested path)
            if "." in inner:
                node_id, rest = inner.split(".", 1)
                base_val = None
                # try local output key from recorded node results
                node_results = results_by_node.get(node_id, {})
                first_seg, *remaining = rest.split(".")
                if first_seg in node_results:
                    base_val = node_results[first_seg]
                else:
                    # try alias mapping for that node
                    out_map = node_by_id.get(node_id).outputs if node_id in node_by_id else {}
                    # find local key by alias name
                    local_key = None
                    for lk, alias in out_map.items():
                        if alias == first_seg:
                            local_key = lk
                            break
                    if local_key and local_key in node_results:
                        base_val = node_results[local_key]
                # drill down remaining path
                for seg in remaining:
                    if isinstance(base_val, dict) and seg in base_val:
                        base_val = base_val[seg]
                    else:
                        base_val = None
                        break
                return base_val
            return value

        # Deep resolve for dict/list structures in node inputs
        def resolve_deep(value: Any) -> Any:
            if isinstance(value, str):
                # 完全一致のプレースホルダは従来どおり直接解決
                if value.startswith("${") and value.endswith("}"):
                    return resolve(value)
                # 文字列内の埋め込みプレースホルダを部分解決
                if "${" in value:
                    parts: List[str] = []
                    i = 0
                    while i < len(value):
                        if value[i : i + 2] == "${":
                            j = value.find("}", i + 2)
                            if j == -1:
                                parts.append(value[i:])
                                break
                            placeholder = value[i : j + 1]
                            try:
                                resolved = resolve(placeholder)
                            except Exception:
                                resolved = None
                            parts.append("" if resolved is None else str(resolved))
                            i = j + 1
                        else:
                            parts.append(value[i])
                            i += 1
                    return "".join(parts)
                return value
            if isinstance(value, dict):
                return {k: resolve_deep(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                t = [resolve_deep(v) for v in value]
                return tuple(t) if isinstance(value, tuple) else t
            return value

        def _safe_eval_expr(expr: str) -> bool:
            # Very small safe-eval supporting comparisons and boolean ops
            def _eval(node):
                if isinstance(node, ast.Expression):
                    return _eval(node.body)
                if isinstance(node, ast.BoolOp):
                    vals = [_eval(v) for v in node.values]
                    if isinstance(node.op, ast.And):
                        return all(vals)
                    if isinstance(node.op, ast.Or):
                        return any(vals)
                    raise ValueError("Unsupported boolean operator")
                if isinstance(node, ast.Compare):
                    left = _eval(node.left)
                    result = True
                    for op, comparator in zip(node.ops, node.comparators):
                        right = _eval(comparator)
                        if isinstance(op, ast.Eq):
                            ok = left == right
                        elif isinstance(op, ast.NotEq):
                            ok = left != right
                        elif isinstance(op, ast.Gt):
                            ok = left > right
                        elif isinstance(op, ast.GtE):
                            ok = left >= right
                        elif isinstance(op, ast.Lt):
                            ok = left < right
                        elif isinstance(op, ast.LtE):
                            ok = left <= right
                        else:
                            raise ValueError("Unsupported comparison operator")
                        result = result and ok
                        left = right
                    return result
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
                    return not _eval(node.operand)
                if isinstance(node, (ast.Constant,)):
                    return node.value
                raise ValueError("Unsupported expression")

            tree = ast.parse(expr, mode="eval")
            return bool(_eval(tree))

        def evaluate_when(n: Node) -> bool:
            if not n.when:
                return True
            expr = n.when.get("expr") if isinstance(n.when, dict) else None
            if expr is None:
                # support simple truthy/falsey when
                return bool(n.when)
            # replace placeholders within expr
            parts: List[str] = []
            i = 0
            while i < len(expr):
                if expr[i : i + 2] == "${":
                    j = expr.find("}", i + 2)
                    if j == -1:
                        parts.append(expr[i:])
                        break
                    placeholder = expr[i : j + 1]
                    val = resolve(placeholder)
                    parts.append(repr(val))
                    i = j + 1
                else:
                    parts.append(expr[i])
                    i += 1
            replaced = "".join(parts)
            try:
                return _safe_eval_expr(replaced)
            except Exception:
                # Fallback: any non-empty string treated as truthy
                return bool(replaced)

        # Collect dependency node ids referenced by placeholders in a value (dict/list supported)
        def _collect_dep_node_ids(val: Any) -> List[str]:
            deps: List[str] = []
            def _walk(v: Any) -> None:
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    inner = v[2:-1]
                    if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                        node_id = inner.split(".", 1)[0]
                        if node_id:
                            deps.append(node_id)
                    return
                if isinstance(v, dict):
                    for vv in v.values():
                        _walk(vv)
                    return
                if isinstance(v, (list, tuple)):
                    for vv in v:
                        _walk(vv)
                    return
            _walk(val)
            # preserve order while deduplicating
            seen: set[str] = set()
            uniq: List[str] = []
            for d in deps:
                if d not in seen:
                    seen.add(d)
                    uniq.append(d)
            return uniq

        # Execute nodes, grouping by same in-degree to allow simple parallelism
        indegree_levels: Dict[int, List[str]] = {}
        for nid in order:
            indegree_levels.setdefault(g.in_degree(nid), []).append(nid)

        # respect UI layout and priority within the same indegree level
        for _, nodes in sorted(indegree_levels.items(), key=lambda kv: kv[0]):
            # Emit scheduling info per level
            try:
                emit(as_event_dict(ScheduleLevelEvent(nodes=list(nodes))))
            except Exception:
                pass
            ui_layout = plan.ui.layout if (plan.ui and plan.ui.layout) else []
            layout_index: Dict[str, int] = {nid_: ui_layout.index(nid_) for nid_ in ui_layout}

            def _sort_key(nid: str):
                n = node_by_id[nid]
                is_ui = 0 if (n.block and str(n.block).startswith("ui.")) else 1
                pos = layout_index.get(nid, 10**6)
                prio = 1000  # Fixed priority since field was removed
                return (is_ui, pos, prio, nid)

            nodes.sort(key=_sort_key)
            futures = []
            level_workers = 4
            if plan.policy and plan.policy.concurrency:
                level_workers = plan.policy.concurrency.get("default_max_workers", level_workers)
            # nodeごとのmax_workersを尊重（最小値）
            # max_workers field was removed, use default level_workers
            with ThreadPoolExecutor(max_workers=level_workers) as ex:
                # 依存関係: 参照を含むノードは遅延させる（簡易デフォ）
                ready_nodes: List[str] = []
                deferred_nodes: List[str] = []
                executed_in_level: List[str] = []
                for nid in nodes:
                    node = next(n for n in plan.graph if n.id == nid)
                    # when guard
                    if not evaluate_when(node):
                        write_event(run_id, {"type": "node_skip", "node": nid, "reason": "when_false"})
                        continue
                    # If inputs contain placeholders (even nested) to nodes not yet in results_by_node, defer
                    def _has_unresolved_dependency(val: Any) -> bool:
                        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                            inner = val[2:-1]
                            if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                                dep_node = inner.split(".", 1)[0]
                                return dep_node not in results_by_node
                            return False
                        if isinstance(val, dict):
                            return any(_has_unresolved_dependency(vv) for vv in val.values())
                        if isinstance(val, (list, tuple)):
                            return any(_has_unresolved_dependency(vv) for vv in val)
                        return False

                    unresolved = any(_has_unresolved_dependency(v) for v in node.inputs.values())
                    # Additional guard: foreach.input dependency must also be resolved before running loop node
                    if not unresolved and node.type == "loop" and node.foreach:
                        fin = node.foreach.get("input") if isinstance(node.foreach, dict) else None
                        if isinstance(fin, str) and fin.startswith("${") and fin.endswith("}"):
                            inner = fin[2:-1]
                            if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                                dep_node = inner.split(".", 1)[0]
                                if dep_node not in results_by_node:
                                    unresolved = True
                    # Emit detailed defer info when unresolved
                    if unresolved:
                        try:
                            dep_nodes = []
                            for v in node.inputs.values():
                                dep_nodes.extend(_collect_dep_node_ids(v))
                            # unique & unresolved only
                            dep_nodes_unique = []
                            seen_dep: set[str] = set()
                            for d in dep_nodes:
                                if d not in seen_dep:
                                    seen_dep.add(d)
                                    if d not in results_by_node:
                                        dep_nodes_unique.append(d)
                            emit({
                                "type": "node_defer",
                                "node": nid,
                                "unresolved_deps": dep_nodes_unique,
                            })
                        except Exception:
                            pass
                    if unresolved:
                        deferred_nodes.append(nid)
                        continue
                    ready_nodes.append(nid)
                    if node.type:
                        # foreach loop minimal implementation
                        if node.type == "loop" and node.foreach and node.body and "plan" in node.body:
                            # foreach
                            src_list = resolve(node.foreach.get("input"))
                            if not isinstance(src_list, list):
                                src_list = list(src_list) if src_list is not None else []
                            item_var = node.foreach.get("itemVar", "item")
                            max_workers = int(node.foreach.get("max_concurrency", 4))
                            emit({
                                "type": "loop_start",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "foreach",
                                "planned_iterations": len(src_list),
                            })

                            collected: List[Any] = []
                            def _run_child(item_value, index):
                                child_plan_dict = node.body["plan"]
                                from core.plan.models import Plan as ChildPlan
                                child_plan = ChildPlan.model_validate(child_plan_dict)
                                child_runner = PlanRunner(self.registry, self.runs_dir)
                                emit({
                                    "type": "loop_iter_start",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "foreach",
                                    "iteration": {"index": index},
                                })
                                child_results = child_runner.run(
                                    child_plan,
                                    vars_overrides={item_var: item_value},
                                    parent_run_id=run_id,
                                )
                                emit({
                                    "type": "loop_iter_finish",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "foreach",
                                    "iteration": {"index": index},
                                })
                                return child_results

                            with ThreadPoolExecutor(max_workers=max_workers) as child_ex:
                                futs = {child_ex.submit(_run_child, v, idx): idx for idx, v in enumerate(src_list)}
                                for f in as_completed(futs):
                                    res = f.result()
                                    collected.append(res)

                            # map to alias via outputs mapping: local key 'collect'
                            out_alias = node.outputs.get("collect") if node.outputs else None
                            if out_alias:
                                results_by_alias[out_alias] = collected
                            results_by_node[nid] = {"collect": collected}
                            emit({
                                "type": "loop_finish",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "foreach",
                                "iterations": len(collected),
                            })
                            executed_in_level.append(nid)
                        # while loop minimal implementation
                        elif node.type == "loop" and node.while_ and node.body and "plan" in node.body:
                            max_iter = int(node.while_.get("max_iterations", 1))
                            emit({
                                "type": "loop_start",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "while",
                                "max_iterations": max_iter,
                            })
                            max_iter = int(node.while_.get("max_iterations", 1))
                            condition = node.while_.get("condition", {})
                            expr = condition.get("expr") if isinstance(condition, dict) else None
                            collected: List[Any] = []
                            for _idx in range(max_iter):
                                if expr:
                                    parts: List[str] = []
                                    i = 0
                                    while i < len(expr):
                                        if expr[i : i + 2] == "${":
                                            j = expr.find("}", i + 2)
                                            if j == -1:
                                                parts.append(expr[i:])
                                                break
                                            placeholder = expr[i : j + 1]
                                            val = resolve(placeholder)
                                            # None は 0 として扱い、文字列/辞書は repr にフォールバック
                                            if val is None:
                                                parts.append("0")
                                            elif isinstance(val, (int, float)):
                                                parts.append(str(val))
                                            else:
                                                parts.append(repr(val))
                                            i = j + 1
                                        else:
                                            parts.append(expr[i])
                                            i += 1
                                    replaced = "".join(parts)
                                    if not _safe_eval_expr(replaced):
                                        break
                                # run body once
                                from core.plan.models import Plan as ChildPlan
                                child_plan = ChildPlan.model_validate(node.body["plan"])
                                child_runner = PlanRunner(self.registry, self.runs_dir)
                                emit({
                                    "type": "loop_iter_start",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "while",
                                    "iteration": {"index": _idx},
                                })
                                child_results = child_runner.run(child_plan, parent_run_id=run_id)
                                emit({
                                    "type": "loop_iter_finish",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "while",
                                    "iteration": {"index": _idx},
                                })
                                collected.append(child_results)
                            out_alias = node.outputs.get("collect") if node.outputs else None
                            if out_alias:
                                results_by_alias[out_alias] = collected
                            results_by_node[nid] = {"collect": collected}
                            emit({
                                "type": "loop_finish",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "while",
                                "iterations": len(collected),
                            })
                            executed_in_level.append(nid)
                        # subflow implementation
                        elif node.type == "subflow" and node.call and "plan_id" in node.call:
                            # Resolve plan path: direct file path or designs/<plan_id>.yaml
                            plan_id = node.call.get("plan_id")
                            plan_path = Path(str(plan_id))
                            if not plan_path.suffix:
                                plan_path = Path("designs") / f"{plan_id}.yaml"
                            from core.plan.loader import load_plan as load_child
                            child_plan = load_child(plan_path)
                            # Optional inputs mapping: map to child's vars
                            child_vars = None
                            if isinstance(node.call, dict) and isinstance(node.call.get("inputs"), dict):
                                child_vars = {}
                                for k, v in node.call["inputs"].items():
                                    child_vars[k] = resolve(v)
                            child_runner = PlanRunner(self.registry, self.runs_dir)
                            emit({"type": "subflow_start", "run_id": run_id, "node": nid})
                            child_results = child_runner.run(
                                child_plan, vars_overrides=child_vars, parent_run_id=run_id
                            )
                            # Map child results to parent aliases using node.outputs mapping
                            if node.outputs:
                                for child_key, parent_alias in node.outputs.items():
                                    results_by_alias[parent_alias] = child_results.get(child_key)
                            results_by_node[nid] = dict(child_results)
                            emit({"type": "subflow_finish", "run_id": run_id, "node": nid})
                            executed_in_level.append(nid)
                        continue
                    if not node.block:
                        continue
                    block = self.registry.get(node.block)
                    if isinstance(block, UIBlock):
                        inputs = {k: resolve_deep(v) for k, v in node.inputs.items()}
                        # UIブロックの統合処理（HITL/ヘッドレス/事前注入対応）
                        out = self._handle_ui_block(block, ctx, inputs, execution_context, nid, plan.id)
                        
                        # UI待機が必要な場合は処理を中断
                        if out.get("metadata", {}).get("submitted") is False:
                            if self.default_ui_hitl:
                                state = self._load_state(plan, run_id) or {}
                                form_info = {
                                    "node_id": nid,
                                    "run_id": run_id,
                                    "inputs": inputs,
                                    "hitl": {},
                                    "submitted": False,
                                }
                                state["pending_ui"] = form_info
                                self._save_state(plan, run_id, state)
                                emit({"type": "ui_wait", "run_id": run_id, "node": nid})
                                return results_by_alias
                            else:
                                # 非HITLモードでは即座にレンダリング
                                emit({"type": "node_start", "run_id": run_id, "node": nid})
                                _t0 = perf_counter()
                                try:
                                    export_log({
                                        "phase": "start",
                                        "node": nid,
                                        "block": node.block,
                                        "inputs": _summarize_for_log(inputs),
                                    }, run_id=run_id, node_id=nid, tag="runner.block")
                                except Exception:
                                    pass
                                out = block.render(ctx, inputs, execution_context)
                                elapsed_ms = int((perf_counter() - _t0) * 1000)
                                emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": elapsed_ms, "attempts": 1})
                                try:
                                    export_log({
                                        "phase": "finish",
                                        "node": nid,
                                        "block": node.block,
                                        "outputs": _summarize_for_log(out),
                                    }, run_id=run_id, node_id=nid, tag="runner.block")
                                except Exception:
                                    pass
                                try:
                                    _save_node_outputs(nid, out if isinstance(out, dict) else {})
                                except Exception:
                                    pass
                        # ヘッドレス等で即時出力が得られた場合にも成果物を保存
                        try:
                            _save_node_outputs(nid, out if isinstance(out, dict) else {})
                        except Exception:
                            pass

                        for local_out, alias in node.outputs.items():
                            if isinstance(out, dict) and local_out in out:
                                results_by_alias[alias] = out[local_out]
                        results_by_node[nid] = dict(out)
                        executed_in_level.append(nid)
                    else:
                        # Submit processing nodes for parallel execution within level
                        inputs = {k: resolve_deep(v) for k, v in node.inputs.items()}

                        def _exec(block_obj: ProcessingBlock, node_id: str, inputs_dict: Dict[str, Any]):
                            emit({"type": "node_start", "run_id": run_id, "node": node_id})
                            # retry policy (minimal)
                            node_policy = node.policy or plan.policy
                            retries = node_policy.retries if node_policy else 0
                            timeout_ms = node_policy.timeout_ms if node_policy else None
                            attempt = 0
                            last_err = None
                            _t0 = perf_counter()
                            try:
                                export_log({
                                    "phase": "start",
                                    "node": node_id,
                                    "block": node.block,
                                    "inputs": _summarize_for_log(inputs_dict),
                                }, run_id=run_id, node_id=node_id, tag="runner.block")
                            except Exception:
                                pass
                            while attempt <= retries:
                                try:
                                    # timeout handling via thread future
                                    if timeout_ms and timeout_ms > 0:
                                        with ThreadPoolExecutor(max_workers=1) as sx:
                                            # create node-scoped context to include __node_id for block logging
                                            node_ctx = BlockContext(run_id=ctx.run_id, workspace=ctx.workspace, vars=dict(ctx.vars))
                                            try:
                                                node_ctx.vars["__node_id"] = node_id
                                            except Exception:
                                                pass
                                            fut = sx.submit(block_obj.run, node_ctx, inputs_dict)
                                            out = fut.result(timeout=timeout_ms / 1000.0)
                                    else:
                                        node_ctx = BlockContext(run_id=ctx.run_id, workspace=ctx.workspace, vars=dict(ctx.vars))
                                        try:
                                            node_ctx.vars["__node_id"] = node_id
                                        except Exception:
                                            pass
                                        out = block_obj.run(node_ctx, inputs_dict)
                                    elapsed_ms = int((perf_counter() - _t0) * 1000)
                                    try:
                                        export_log({
                                            "phase": "finish",
                                            "node": node_id,
                                            "block": node.block,
                                            "outputs": _summarize_for_log(out),
                                        }, run_id=run_id, node_id=node_id, tag="runner.block")
                                    except Exception:
                                        pass
                                    return node_id, out, elapsed_ms, attempt + 1
                                except Exception as e:  # noqa: BLE001
                                    last_err = e
                                    attempt += 1
                                    # Extract structured error information if available
                                    error_code = type(e).__name__
                                    error_details = {}
                                    recoverable = False
                                    if isinstance(e, BlockException) and e.error:
                                        error_code = e.error.code
                                        error_details = {
                                            "details": e.error.details,
                                            "hint": e.error.hint,
                                        }
                                        recoverable = bool(e.error.recoverable)
                                    else:
                                        error_details = {
                                            "exception_type": type(e).__name__,
                                            "exception_args": getattr(e, "args", ()),
                                            "input_keys": sorted(list(inputs_dict.keys())) if isinstance(inputs_dict, dict) else [],
                                            "traceback": "".join(traceback.format_exception_only(type(e), e))[:2000],
                                        }
                                    emit({
                                        "type": "error",
                                        "node": node_id,
                                        "attempt": attempt,
                                        "message": str(e),
                                        "error_code": error_code,
                                        "recoverable": recoverable,
                                        "error_details": error_details,
                                    })
                                    if not node_policy or (node_policy.on_error or "continue") == "halt":
                                        raise
                                    if (node_policy.on_error == "retry") and attempt <= retries:
                                        continue
                                    if (node_policy.on_error == "continue"):
                                        # treat as empty outputs
                                        elapsed_ms = int((perf_counter() - _t0) * 1000)
                                        return node_id, {}, elapsed_ms, attempt
                            # exhausted
                            raise last_err  # type: ignore[misc]

                        futures.append(ex.submit(_exec, block, nid, inputs))

                for fut in as_completed(futures):
                    node_id, out, elapsed_ms, attempts = fut.result()
                    node = next(n for n in plan.graph if n.id == node_id)
                    # Resolve any alias placeholders that remain as strings
                    if isinstance(out, dict):
                        for k, v in list(out.items()):
                            if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                                try:
                                    out[k] = resolve(v)
                                except Exception:
                                    pass
                    for local_out, alias in node.outputs.items():
                        if isinstance(out, dict) and local_out in out:
                            results_by_alias[alias] = out[local_out]
                    results_by_node[node_id] = dict(out)
                    emit({"type": "node_finish", "run_id": run_id, "node": node_id, "elapsed_ms": elapsed_ms, "attempts": attempts})
                    try:
                        _save_node_outputs(node_id, out if isinstance(out, dict) else {})
                    except Exception:
                        pass
                    # Flow図の成功状態を永続
                    try:
                        self._record_success(plan, run_id, node_id)
                    except Exception:
                        pass
                    executed_in_level.append(node_id)
                # If there were deferred nodes, execute them now sequentially (improved fallback)
                if deferred_nodes:
                    # Try to resolve deferred nodes in multiple passes to respect dependencies within the same indegree level
                    remaining = list(deferred_nodes)
                    made_progress = True
                    def _dep_unresolved(val: Any) -> bool:
                        if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                            inner = val[2:-1]
                            if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                                dep_node = inner.split(".", 1)[0]
                                return dep_node not in results_by_node
                            return False
                        if isinstance(val, dict):
                            return any(_dep_unresolved(vv) for vv in val.values())
                        if isinstance(val, (list, tuple)):
                            return any(_dep_unresolved(vv) for vv in val)
                        return False

                    while remaining and made_progress:
                        made_progress = False
                        # 1) Run non-loop nodes whose dependencies are now resolved
                        for nid in list(remaining):
                            node = node_by_id[nid]
                            if node.type == "loop":
                                continue
                            if any(_dep_unresolved(v) for v in node.inputs.values()):
                                continue
                            # Ready to run
                            inputs = {k: resolve_deep(v) for k, v in node.inputs.items()}
                            if not node.block:
                                remaining.remove(nid)
                                continue
                            block = self.registry.get(node.block)
                            if isinstance(block, UIBlock):
                                # UIブロックの統合処理
                                out = self._handle_ui_block(block, ctx, inputs, execution_context, nid, plan.id)
                                
                                # UI待機が必要な場合は処理を中断
                                if out.get("metadata", {}).get("submitted") is False:
                                    if self.default_ui_hitl:
                                        state = self._load_state(plan, run_id) or {}
                                        force_ui = os.getenv("KEIRI_AGENT_FORCE_UI", "0") == "1"
                                        # 強制UI時は既存完了を破棄
                                        if force_ui:
                                            try:
                                                cm = state.get("ui_outputs") or {}
                                                if str(nid) in cm:
                                                    cm.pop(str(nid), None)
                                                    state["ui_outputs"] = cm
                                            except Exception:
                                                pass
                                        state["pending_ui"] = {"node_id": nid, "run_id": run_id, "inputs": inputs, "submitted": False}
                                        self._save_state(plan, run_id, state)
                                        emit({"type": "ui_wait", "run_id": run_id, "node": nid})
                                        return results_by_alias
                                    else:
                                        # 非HITLモードでは即座にレンダリング
                                        out = block.render(ctx, inputs, execution_context)
                            else:
                                # create node-scoped context to include __node_id for block logging
                                node_ctx = BlockContext(run_id=ctx.run_id, workspace=ctx.workspace, vars=dict(ctx.vars))
                                try:
                                    node_ctx.vars["__node_id"] = nid
                                except Exception:
                                    pass
                                out = block.run(node_ctx, inputs)
                            for local_out, alias in node.outputs.items():
                                if isinstance(out, dict) and local_out in out:
                                    results_by_alias[alias] = out[local_out]
                            results_by_node[nid] = dict(out)
                            emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": 0, "attempts": 1})
                            try:
                                _save_node_outputs(nid, out if isinstance(out, dict) else {})
                            except Exception:
                                pass
                            try:
                                self._record_success(plan, run_id, nid)
                            except Exception:
                                pass
                            remaining.remove(nid)
                            made_progress = True
                            executed_in_level.append(nid)

                        # 2) Run loop nodes when their foreach.input resolves to a concrete list
                        for nid in list(remaining):
                            node = node_by_id[nid]
                            if node.type != "loop" or not node.foreach or not node.body or "plan" not in node.body:
                                continue
                            fin = node.foreach.get("input") if isinstance(node.foreach, dict) else None
                            src_resolved = resolve(fin) if isinstance(fin, str) else fin
                            if not isinstance(src_resolved, list):
                                # not ready yet
                                continue
                            item_var = node.foreach.get("itemVar", "item")
                            max_workers = int(node.foreach.get("max_concurrency", 4))
                            emit({
                                "type": "loop_start",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "foreach",
                                "planned_iterations": len(src_resolved),
                            })
                            collected: List[Any] = []
                            def _run_child(item_value, index):
                                child_plan_dict = node.body["plan"]
                                from core.plan.models import Plan as ChildPlan
                                child_plan = ChildPlan.model_validate(child_plan_dict)
                                child_runner = PlanRunner(self.registry, self.runs_dir)
                                emit({
                                    "type": "loop_iter_start",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "foreach",
                                    "iteration": {"index": index},
                                })
                                child_results = child_runner.run(
                                    child_plan,
                                    vars_overrides={item_var: item_value},
                                    parent_run_id=run_id,
                                )
                                emit({
                                    "type": "loop_iter_finish",
                                    "run_id": run_id,
                                    "node": nid,
                                    "loop": "foreach",
                                    "iteration": {"index": index},
                                })
                                return child_results
                            with ThreadPoolExecutor(max_workers=max_workers) as child_ex:
                                futs = {child_ex.submit(_run_child, v, idx): idx for idx, v in enumerate(src_resolved)}
                                for f in as_completed(futs):
                                    res = f.result()
                                    collected.append(res)
                            out_alias = node.outputs.get("collect") if node.outputs else None
                            if out_alias:
                                results_by_alias[out_alias] = collected
                            results_by_node[nid] = {"collect": collected}
                            emit({
                                "type": "loop_finish",
                                "run_id": run_id,
                                "node": nid,
                                "loop": "foreach",
                                "iterations": len(collected),
                            })
                            remaining.remove(nid)
                            made_progress = True
                            executed_in_level.append(nid)
                # level end summary
                try:
                    # Nodes that still remained deferred after fallback (if any)
                    leftover: List[str] = []
                    try:
                        # mypy: deferred_nodes may be referenced outside context; safe here
                        leftover = [n for n in (deferred_nodes or []) if n not in executed_in_level]
                    except Exception:
                        leftover = []
                    emit(as_event_dict(ScheduleLevelFinishEvent(executed=executed_in_level, leftover=leftover)))
                except Exception:
                    pass
        # Global re-evaluation pass: try to execute any remaining nodes whose
        # dependencies have become resolvable after later-level executions.
        try:
            remaining = [nid for nid in order if nid not in results_by_node]
            if remaining:
                emit({"type": "schedule_global_pass_start", "nodes": list(remaining)})
                executed_global: List[str] = []
                def _dep_unresolved(val: Any) -> bool:
                    if isinstance(val, str) and val.startswith("${") and val.endswith("}"):
                        inner = val[2:-1]
                        if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                            dep_node = inner.split(".", 1)[0]
                            return dep_node not in results_by_node
                        return False
                    if isinstance(val, dict):
                        return any(_dep_unresolved(vv) for vv in val.values())
                    if isinstance(val, (list, tuple)):
                        return any(_dep_unresolved(vv) for vv in val)
                    return False
                made_progress = True
                while remaining and made_progress:
                    made_progress = False
                    for nid in list(remaining):
                        node = node_by_id[nid]
                        if not evaluate_when(node):
                            write_event(run_id, {"type": "node_skip", "node": nid, "reason": "when_false"})
                            remaining.remove(nid)
                            made_progress = True
                            continue
                        if any(_dep_unresolved(v) for v in node.inputs.values()):
                            continue
                        # Ready to run
                        inputs = {k: resolve_deep(v) for k, v in node.inputs.items()}
                        if not node.block:
                            remaining.remove(nid)
                            made_progress = True
                            continue
                        block_obj = self.registry.get(node.block)
                        if isinstance(block_obj, UIBlock):
                            # UIブロックの統合処理
                            out = self._handle_ui_block(block_obj, ctx, inputs, execution_context, nid, plan.id)
                            
                            # UI待機が必要な場合は処理を中断
                            if out.get("metadata", {}).get("submitted") is False:
                                if self.default_ui_hitl:
                                    state = self._load_state(plan, run_id) or {}
                                    form_info = {"node_id": nid, "run_id": run_id, "inputs": inputs, "submitted": False}
                                    state["pending_ui"] = form_info
                                    self._save_state(plan, run_id, state)
                                    emit({"type": "ui_wait", "node": nid})
                                    emit({
                                        "type": "schedule_global_pass_finish",
                                        "executed": executed_global,
                                        "leftover": [n for n in remaining if n not in executed_global],
                                    })
                                    return results_by_alias
                                else:
                                    # 非HITLモードでは即座にレンダリング
                                    emit({"type": "node_start", "run_id": run_id, "node": nid})
                                    _t0 = perf_counter()
                                    out = block_obj.render(ctx, inputs, execution_context)
                                    elapsed_ms = int((perf_counter() - _t0) * 1000)
                                    emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": elapsed_ms, "attempts": 1})
                            try:
                                _save_node_outputs(nid, out if isinstance(out, dict) else {})
                            except Exception:
                                pass
                        else:
                            # Processing block with minimal retry policy
                            def _exec_block(block_inst: ProcessingBlock, node_id: str, inputs_dict: Dict[str, Any]):
                                emit({"type": "node_start", "run_id": run_id, "node": node_id})
                                node_policy = node.policy or plan.policy
                                retries = node_policy.retries if node_policy else 0
                                timeout_ms = node_policy.timeout_ms if node_policy else None
                                attempt = 0
                                last_err = None
                                _t0 = perf_counter()
                                try:
                                    export_log({
                                        "phase": "start",
                                        "node": node_id,
                                        "block": node.block,
                                        "inputs": _summarize_for_log(inputs_dict),
                                    }, run_id=run_id, node_id=node_id, tag="runner.block")
                                except Exception:
                                    pass
                                while attempt <= retries:
                                    try:
                                        if timeout_ms and timeout_ms > 0:
                                            with ThreadPoolExecutor(max_workers=1) as sx:
                                                fut = sx.submit(block_inst.run, ctx, inputs_dict)
                                                out = fut.result(timeout=timeout_ms / 1000.0)
                                        else:
                                            node_ctx = BlockContext(run_id=ctx.run_id, workspace=ctx.workspace, vars=dict(ctx.vars))
                                            try:
                                                node_ctx.vars["__node_id"] = node_id
                                            except Exception:
                                                pass
                                            out = block_inst.run(node_ctx, inputs_dict)
                                        elapsed_ms = int((perf_counter() - _t0) * 1000)
                                        try:
                                            export_log({
                                                "phase": "finish",
                                                "node": node_id,
                                                "block": node.block,
                                                "outputs": _summarize_for_log(out),
                                            }, run_id=run_id, node_id=node_id, tag="runner.block")
                                        except Exception:
                                            pass
                                        return node_id, out, elapsed_ms, attempt + 1
                                    except Exception as e:  # noqa: BLE001
                                        last_err = e
                                        attempt += 1
                                        error_code = type(e).__name__
                                        error_details = {}
                                        recoverable = False
                                        if isinstance(e, BlockException) and e.error:
                                            error_code = e.error.code
                                            error_details = {
                                                "details": e.error.details,
                                                "hint": e.error.hint,
                                            }
                                            recoverable = bool(e.error.recoverable)
                                        else:
                                            error_details = {
                                                "exception_type": type(e).__name__,
                                                "exception_args": getattr(e, "args", ()),
                                                "input_keys": sorted(list(inputs_dict.keys())) if isinstance(inputs_dict, dict) else [],
                                                "traceback": "".join(traceback.format_exception_only(type(e), e))[:2000],
                                            }
                                        emit({
                                            "type": "error",
                                            "node": node_id,
                                            "attempt": attempt,
                                            "message": str(e),
                                            "error_code": error_code,
                                            "recoverable": recoverable,
                                            "error_details": error_details,
                                        })
                                        if not node_policy or (node_policy.on_error or "continue") == "halt":
                                            raise
                                        if (node_policy.on_error == "retry") and attempt <= retries:
                                            continue
                                        if (node_policy.on_error == "continue"):
                                            elapsed_ms = int((perf_counter() - _t0) * 1000)
                                            return node_id, {}, elapsed_ms, attempt
                                raise last_err  # type: ignore[misc]
                            node_id, out, elapsed_ms, attempts = _exec_block(block_obj, nid, inputs)  # type: ignore[arg-type]
                            # Resolve any alias placeholders
                            if isinstance(out, dict):
                                for k, v in list(out.items()):
                                    if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                                        try:
                                            out[k] = resolve(v)
                                        except Exception:
                                            pass
                            for local_out, alias in node.outputs.items():
                                if isinstance(out, dict) and local_out in out:
                                    results_by_alias[alias] = out[local_out]
                            results_by_node[nid] = dict(out)
                            emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": elapsed_ms, "attempts": attempts})
                            try:
                                _save_node_outputs(nid, out if isinstance(out, dict) else {})
                            except Exception:
                                pass
                            try:
                                self._record_success(plan, run_id, nid)
                            except Exception:
                                pass
                        remaining.remove(nid)
                        executed_global.append(nid)
                        made_progress = True
                emit({"type": "schedule_global_pass_finish", "executed": executed_global, "leftover": [n for n in remaining if n not in executed_global]})
        except Exception:
            pass

        # Emit final list of unexecuted nodes (for diagnostics)
        try:
            not_executed = [nid for nid in order if nid not in results_by_node]
            if not_executed:
                emit({
                    "type": "plan_unexecuted_nodes",
                    "nodes": not_executed,
                })
        except Exception:
            pass
        try:
            total_nodes = len(order)
            success_nodes = len(results_by_node)
            summary = FinishSummaryEvent(
                total_nodes=total_nodes,
                success_nodes=success_nodes,
                skipped_nodes=0,
                error_nodes=0,
                total_elapsed_ms=0,
                total_retries=0,
            )
            emit(as_event_dict(summary))
        except Exception:
            pass
        emit({"type": "finish", "run": run_id, "plan": plan.id})
        return results_by_alias

    def _handle_headless_ui(self, block: UIBlock, ctx: BlockContext, inputs: Dict[str, Any], execution_context: Any, node_id: str | None = None) -> Dict[str, Any]:
        """ヘッドレスモードでのUIブロック処理"""
        # 実行コンテキストからモック応答を取得
        node_key = (node_id or ctx.vars.get("__node_id", "") or inputs.get("node_id") or "")
        mock_response = execution_context.get_ui_mock_response(block.id, node_key)
        if mock_response:
            # モック応答の後処理（auto_resolve など）
            try:
                if isinstance(mock_response, dict):
                    resp = dict(mock_response)
                    cd = resp.get("collected_data")
                    if isinstance(cd, dict):
                        realized: Dict[str, Any] = {}
                        for fid, val in cd.items():
                            if val == "auto_resolve":
                                try:
                                    data = execution_context.resolve_file_input(fid)
                                    realized[fid] = data if data is not None else None
                                except Exception:
                                    realized[fid] = None
                            else:
                                realized[fid] = val
                        resp["collected_data"] = realized
                    return resp
            except Exception:
                return mock_response
            return mock_response
        
        # フォールバック: ブロックのヘッドレス応答
        if hasattr(block, '_headless_response'):
            return block._headless_response(inputs, execution_context)
        
        # 最終フォールバック: 空の応答
        return {"metadata": {"submitted": True, "headless": True}}

    def _handle_ui_block(self, block: UIBlock, ctx: BlockContext, inputs: Dict[str, Any], 
                         execution_context: Optional[Any] = None, node_id: str = "", plan_id: Optional[str] = None) -> Dict[str, Any]:
        """UIブロックの統合処理"""
        # ヘッドレスモードでの自動処理
        if execution_context and getattr(execution_context, 'headless_mode', False):
            return self._handle_headless_ui(block, ctx, inputs, execution_context, node_id)
        # default_ui_hitl=True かつ 事前注入されたUI結果がある場合はそれを使用
        if self.default_ui_hitl and plan_id:
            try:
                state = self.get_state(plan_id, ctx.run_id) or {}
                pre = state.get("ui_outputs") or {}
                # デコード: {"__type":"b64bytes","data":...} -> bytes
                def _decode(v):
                    if isinstance(v, dict):
                        if v.get("__type") == "b64bytes" and isinstance(v.get("data"), str):
                            try:
                                return base64.b64decode(v["data"])  # type: ignore[arg-type]
                            except Exception:
                                return b""
                        return {kk: _decode(vv) for kk, vv in v.items()}
                    if isinstance(v, list):
                        return [_decode(x) for x in v]
                    return v
                if isinstance(pre, dict) and node_id in pre:
                    out = _decode(pre[node_id])
                    if isinstance(out, dict):
                        # ensure metadata.submitted is truthy to avoid UI wait
                        md = out.get("metadata") or {}
                        if not isinstance(md, dict):
                            md = {}
                        md.setdefault("submitted", True)
                        out["metadata"] = md
                        return out
            except Exception:
                pass
        
        # 通常のUI処理
        if hasattr(block, 'render'):
            return block.render(ctx, inputs, execution_context)
        else:
            # フォールバック
            return {"metadata": {"submitted": False, "error": "UI block not supported"}}


