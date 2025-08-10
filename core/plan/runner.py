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

import networkx as nx

from core.blocks.base import BlockContext, ProcessingBlock, UIBlock
from core.blocks.registry import BlockRegistry
from .models import Node, Plan
from .config_store import get_store


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

    def _write_event(self, path: Path, event: Dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._log_lock:
            with path.open("a", encoding="utf-8") as f:
                f.write(line)

    def _build_graph(self, plan: Plan) -> nx.DiGraph:
        g = nx.DiGraph()
        for n in plan.graph:
            g.add_node(n.id)
        
        def add_edges_from_placeholders(text: str, dest_id: str) -> None:
            i = 0
            while i < len(text):
                if text[i : i + 2] == "${":
                    j = text.find("}", i + 2)
                    if j == -1:
                        break
                    inner = text[i + 2 : j]
                    if not inner.startswith(("vars.", "env.", "config.")) and "." in inner:
                        src = inner.split(".", 1)[0]
                        if src:
                            g.add_edge(src, dest_id)
                    i = j + 1
                else:
                    i += 1

        for n in plan.graph:
            if n.type:
                # Create edges for foreach/while references
                if n.type == "loop" and n.foreach and isinstance(n.foreach.get("input"), str):
                    add_edges_from_placeholders(str(n.foreach.get("input")), n.id)
                if n.type == "loop" and n.while_:
                    cond = n.while_.get("condition", {}) if isinstance(n.while_, dict) else {}
                    expr = cond.get("expr") if isinstance(cond, dict) else None
                    if isinstance(expr, str):
                        add_edges_from_placeholders(expr, n.id)
                # subflow: ignore; not analyzing child plan here
                continue
            for v in n.inputs.values():
                if isinstance(v, str):
                    add_edges_from_placeholders(v, n.id)
        return g

    def run(
        self,
        plan: Plan,
        vars_overrides: Dict[str, Any] | None = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        parent_run_id: Optional[str] = None,
        resume_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if resume_run_id:
            run_id = resume_run_id
        else:
            run_id = f"{parent_run_id}#{_now_ts()}" if parent_run_id else _now_ts()
        ctx = BlockContext(run_id=run_id, workspace=str(Path.cwd()), vars=dict(plan.vars))
        if vars_overrides:
            ctx.vars.update(vars_overrides)

        log_path = self._make_run_log_path(plan)
        def emit(event: Dict[str, Any]) -> None:
            self._write_event(log_path, event)
            if on_event is not None:
                try:
                    on_event(event)
                except Exception:
                    # UI callback errors must not break the runner
                    pass

        emit({"type": "start", "run_id": run_id, "plan": plan.id, "parent_run_id": parent_run_id})

        g = self._build_graph(plan)
        order = list(nx.topological_sort(g))

        results_by_alias: Dict[str, Any] = {}
        results_by_node: Dict[str, Dict[str, Any]] = {}

        # Build helper maps
        node_by_id: Dict[str, Node] = {n.id: n for n in plan.graph}

        # Helper to resolve an input value
        def resolve(value: Any) -> Any:
            if not isinstance(value, str) or not (value.startswith("${") and value.endswith("}")):
                return value
            inner = value[2:-1]
            if inner.startswith("vars."):
                _, key = inner.split(".", 1)
                return ctx.vars.get(key)
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

        # Execute nodes, grouping by same in-degree to allow simple parallelism
        indegree_levels: Dict[int, List[str]] = {}
        for nid in order:
            indegree_levels.setdefault(g.in_degree(nid), []).append(nid)

        # respect UI layout and priority within the same indegree level
        for _, nodes in sorted(indegree_levels.items(), key=lambda kv: kv[0]):
            ui_layout = plan.ui.layout if (plan.ui and plan.ui.layout) else []
            layout_index: Dict[str, int] = {nid_: ui_layout.index(nid_) for nid_ in ui_layout}

            def _sort_key(nid: str):
                n = node_by_id[nid]
                is_ui = 0 if (n.block and str(n.block).startswith("ui.")) else 1
                pos = layout_index.get(nid, 10**6)
                prio = n.priority if n.priority is not None else 1000
                return (is_ui, pos, prio, nid)

            nodes.sort(key=_sort_key)
            futures = []
            level_workers = 4
            if plan.policy and plan.policy.concurrency:
                level_workers = plan.policy.concurrency.get("default_max_workers", level_workers)
            # nodeごとのmax_workersを尊重（最小値）
            if any(node_by_id[nid].max_workers for nid in nodes):
                per_node = min([node_by_id[nid].max_workers or level_workers for nid in nodes])
                level_workers = max(1, min(level_workers, per_node))
            with ThreadPoolExecutor(max_workers=level_workers) as ex:
                # 依存関係: 参照を含むノードは遅延させる（簡易デフォ）
                ready_nodes: List[str] = []
                deferred_nodes: List[str] = []
                for nid in nodes:
                    node = next(n for n in plan.graph if n.id == nid)
                    # when guard
                    if not evaluate_when(node):
                        self._write_event(log_path, {"type": "node_skip", "run_id": run_id, "node": nid, "reason": "when_false"})
                        continue
                    # If inputs contain placeholders to nodes not yet in results_by_node, defer
                    unresolved = False
                    for v in node.inputs.values():
                        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                            inner = v[2:-1]
                            if "." in inner and not inner.startswith(("vars.", "env.", "config.")):
                                dep_node = inner.split(".", 1)[0]
                                if dep_node not in results_by_node:
                                    unresolved = True
                                    break
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
                        continue
                    if not node.block:
                        continue
                    block = self.registry.get(node.block)
                    if isinstance(block, UIBlock):
                        inputs = {k: resolve(v) for k, v in node.inputs.items()}
                        # HITL対象ノードのみ待機。それ以外は従来通り即時レンダリング（スタブ）
                        if node.hitl or self.default_ui_hitl:
                            state = self._load_state(plan, run_id) or {}
                            pending_ui = state.get("pending_ui")
                            completed_map = state.get("ui_outputs") or {}
                            # JSON保存されたbytesを復元する関数
                            def _decode_from_json(val):
                                if isinstance(val, dict) and val.get("__type") == "b64bytes":
                                    try:
                                        return base64.b64decode(val.get("data", ""))
                                    except Exception:
                                        return b""
                                if isinstance(val, dict):
                                    return {kk: _decode_from_json(vv) for kk, vv in val.items()}
                                if isinstance(val, list):
                                    return [_decode_from_json(x) for x in val]
                                return val

                            # 別ノードのsubmitted pendingが残っていたら completed_map に移し、pendingをクリア
                            if pending_ui and pending_ui.get("submitted") and pending_ui.get("node_id") != nid:
                                node_saved = str(pending_ui.get("node_id"))
                                outputs_saved = pending_ui.get("outputs", {})
                                completed_map[node_saved] = outputs_saved
                                state["ui_outputs"] = completed_map
                                state["pending_ui"] = None
                                self._save_state(plan, run_id, state)
                                pending_ui = None

                            # 既にこのノードの出力が保存済みならそれを使用
                            out = None
                            if str(nid) in completed_map:
                                out = _decode_from_json(completed_map[str(nid)])
                                emit({"type": "ui_reuse", "run_id": run_id, "node": nid})
                            elif pending_ui and pending_ui.get("node_id") == nid and pending_ui.get("submitted"):
                                out = _decode_from_json(pending_ui.get("outputs", {}))
                                # move to completed map and clear pending
                                completed_map[str(nid)] = pending_ui.get("outputs", {})
                                state["ui_outputs"] = completed_map
                                state["pending_ui"] = None
                                self._save_state(plan, run_id, state)
                                emit({"type": "ui_submit", "run_id": run_id, "node": nid})
                            else:
                                form_info = {
                                    "node_id": nid,
                                    "run_id": run_id,
                                    "inputs": inputs,
                                    "hitl": node.hitl or {},
                                    "submitted": False,
                                }
                                state["pending_ui"] = form_info
                                self._save_state(plan, run_id, state)
                                emit({"type": "ui_wait", "run_id": run_id, "node": nid})
                                return results_by_alias
                        else:
                            emit({"type": "node_start", "run_id": run_id, "node": nid})
                            _t0 = perf_counter()
                            out = block.render(ctx, inputs)
                            elapsed_ms = int((perf_counter() - _t0) * 1000)
                            emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": elapsed_ms, "attempts": 1})

                        for local_out, alias in node.outputs.items():
                            if isinstance(out, dict) and local_out in out:
                                results_by_alias[alias] = out[local_out]
                        results_by_node[nid] = dict(out)
                    else:
                        # Submit processing nodes for parallel execution within level
                        inputs = {k: resolve(v) for k, v in node.inputs.items()}

                        def _exec(block_obj: ProcessingBlock, node_id: str, inputs_dict: Dict[str, Any]):
                            emit({"type": "node_start", "run_id": run_id, "node": node_id})
                            # retry policy (minimal)
                            node_policy = node.policy or plan.policy
                            retries = node_policy.retries if node_policy else 0
                            timeout_ms = node_policy.timeout_ms if node_policy else None
                            attempt = 0
                            last_err = None
                            _t0 = perf_counter()
                            while attempt <= retries:
                                try:
                                    # timeout handling via thread future
                                    if timeout_ms and timeout_ms > 0:
                                        with ThreadPoolExecutor(max_workers=1) as sx:
                                            fut = sx.submit(block_obj.run, ctx, inputs_dict)
                                            out = fut.result(timeout=timeout_ms / 1000.0)
                                    else:
                                        out = block_obj.run(ctx, inputs_dict)
                                    elapsed_ms = int((perf_counter() - _t0) * 1000)
                                    return node_id, out, elapsed_ms, attempt + 1
                                except Exception as e:  # noqa: BLE001
                                    last_err = e
                                    attempt += 1
                                    emit({
                                        "type": "error",
                                        "run_id": run_id,
                                        "node": node_id,
                                        "attempt": attempt,
                                        "message": str(e),
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
                # If there were deferred nodes, execute them now sequentially (simple fallback)
                for nid in deferred_nodes:
                    node = next(n for n in plan.graph if n.id == nid)
                    inputs = {k: resolve(v) for k, v in node.inputs.items()}
                    if not node.block:
                        continue
                    block = self.registry.get(node.block)
                    if isinstance(block, UIBlock):
                        # should not happen in this plan; but respect HITL if exists
                        if node.hitl or self.default_ui_hitl:
                            state = self._load_state(plan, run_id) or {}
                            state["pending_ui"] = {"node_id": nid, "run_id": run_id, "inputs": inputs, "submitted": False}
                            self._save_state(plan, run_id, state)
                            emit({"type": "ui_wait", "run_id": run_id, "node": nid})
                            return results_by_alias
                        out = block.render(ctx, inputs)
                    else:
                        out = block.run(ctx, inputs)
                    for local_out, alias in node.outputs.items():
                        if isinstance(out, dict) and local_out in out:
                            results_by_alias[alias] = out[local_out]
                    results_by_node[nid] = dict(out)
                    emit({"type": "node_finish", "run_id": run_id, "node": nid, "elapsed_ms": 0, "attempts": 1})
        emit({"type": "finish", "run_id": run_id, "plan": plan.id})
        return results_by_alias


