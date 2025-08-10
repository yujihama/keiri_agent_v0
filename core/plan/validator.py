from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
import ast
import os
from pathlib import Path

import networkx as nx
from packaging.version import Version

from core.blocks.registry import BlockRegistry, BlockSpec
from .models import Node, Plan
from .config_store import get_store


_PLACEHOLDER_RE = re.compile(r"^\s*\$\{([^}]+)\}\s*$")


def _pick_latest_spec(specs: List[BlockSpec]) -> BlockSpec:
    if not specs:
        raise KeyError("No specs provided")
    try:
        return sorted(specs, key=lambda s: Version(s.version))[-1]
    except Exception:
        return specs[-1]


def validate_plan(plan: Plan, registry: BlockRegistry) -> List[str]:
    errors: List[str] = []

    # 1) Basic uniqueness
    seen_ids: set[str] = set()
    for node in plan.graph:
        if node.id in seen_ids:
            errors.append(f"Duplicate node id: {node.id}")
        seen_ids.add(node.id)

    # 2) Block existence and IO key checks (only for regular nodes)
    block_specs: Dict[str, BlockSpec] = {}
    for block_id, specs in registry.specs_by_id.items():
        block_specs[block_id] = _pick_latest_spec(specs)
    def _py_isinstance_for_type(val: Any, type_name: Any) -> bool:
        tn = str(type_name).lower() if type_name is not None else ""
        if tn in {"string", "str"}:
            return isinstance(val, str)
        if tn in {"number", "float"}:
            return isinstance(val, (int, float)) and not isinstance(val, bool)
        if tn in {"integer", "int"}:
            return isinstance(val, int) and not isinstance(val, bool)
        if tn in {"boolean", "bool"}:
            return isinstance(val, bool)
        if tn in {"array", "list"}:
            return isinstance(val, (list, tuple))
        if tn in {"object", "dict"}:
            return isinstance(val, dict)
        if tn in {"bytes", "binary"}:
            return isinstance(val, (bytes, bytearray))
        # unknown type: skip strict check
        return True

    # 2a) when.expr syntax validation (safe subset, placeholders replaced)
    for node in plan.graph:
        if node.when and isinstance(node.when, dict) and (expr := node.when.get("expr")):
            expr_str = str(expr)
            # Replace ${...} with neutral literal to allow parsing
            parts: List[str] = []
            i = 0
            while i < len(expr_str):
                if expr_str[i : i + 2] == "${":
                    j = expr_str.find("}", i + 2)
                    if j == -1:
                        parts.append(expr_str[i:])
                        break
                    parts.append("0")
                    i = j + 1
                else:
                    parts.append(expr_str[i])
                    i += 1
            replaced = "".join(parts)
            try:
                tree = ast.parse(replaced, mode="eval")
                # Walk and ensure only allowed nodes are present
                allowed = (
                    ast.Expression,
                    ast.BoolOp,
                    ast.And,
                    ast.Or,
                    ast.UnaryOp,
                    ast.Not,
                    ast.Compare,
                    ast.Eq,
                    ast.NotEq,
                    ast.Gt,
                    ast.GtE,
                    ast.Lt,
                    ast.LtE,
                    ast.Constant,
                    ast.Load,
                )
                for n_ in ast.walk(tree):
                    if not isinstance(n_, allowed):
                        raise ValueError(f"Unsupported token: {type(n_).__name__}")
            except Exception:
                errors.append(f"Node {node.id}: invalid when.expr syntax")

    for node in plan.graph:
        if node.type:
            # loop/subflow nodes will be validated in future iterations (minimal checks below)
            # subflow requires call.plan_id
            if node.type == "subflow":
                if not node.call or "plan_id" not in node.call:
                    errors.append(f"Node {node.id}: subflow.call.plan_id is required")
                if node.call and (inputs_map := node.call.get("inputs")) is not None and not isinstance(inputs_map, dict):
                    errors.append(f"Node {node.id}: subflow.call.inputs must be a mapping")
                # referenced plan existence (best-effort)
                if node.call and isinstance(node.call.get("plan_id"), str):
                    pid = str(node.call.get("plan_id"))
                    p = Path(pid)
                    if not p.suffix:
                        p = Path("designs") / f"{pid}.yaml"
                    if not p.exists():
                        errors.append(f"Node {node.id}: subflow plan not found: {p}")
            # when expr quick AST syntax safety (optional)
            # (moved to global when validation above)
            continue
        if node.block:
            if node.block not in block_specs:
                errors.append(f"Unknown block id in node {node.id}: {node.block}")
                continue
            spec = block_specs[node.block]
            # inputs keys validation (name-level)
            for key in node.inputs.keys():
                if key not in (spec.inputs or {}):
                    errors.append(
                        f"Node {node.id}: input key '{key}' not defined in block spec '{node.block}'"
                    )
            # outputs keys validation (name-level)
            for local_out_key in node.outputs.keys():
                if local_out_key not in (spec.outputs or {}):
                    errors.append(
                        f"Node {node.id}: output key '{local_out_key}' not defined in block spec '{node.block}'"
                    )

    # 3) Reference resolution and DAG edges + env/config checks + type propagation
    node_ids = {n.id for n in plan.graph}
    node_by_id: Dict[str, Node] = {n.id: n for n in plan.graph}
    produced_aliases: Dict[str, set[str]] = {}
    produced_types: Dict[str, Dict[str, Any]] = {}
    for n in plan.graph:
        if n.type:
            produced_aliases[n.id] = set(n.outputs.values()) if n.outputs else set()
            produced_types[n.id] = {alias: None for alias in produced_aliases[n.id]}
        else:
            produced_aliases[n.id] = set(n.outputs.values())
            # map alias -> output type from spec
            if n.block and n.block in block_specs:
                spec = block_specs[n.block]
                types_map: Dict[str, Any] = {}
                for local_out, alias in (n.outputs or {}).items():
                    out_schema = (spec.outputs or {}).get(local_out) or {}
                    out_type = out_schema.get("type")
                    types_map[alias] = out_type
                produced_types[n.id] = types_map
            else:
                produced_types[n.id] = {}

    g = nx.DiGraph()
    for n in plan.graph:
        g.add_node(n.id)

    def parse_placeholder(value: Any) -> Tuple[str, str] | None:
        if not isinstance(value, str):
            return None
        m = _PLACEHOLDER_RE.match(value)
        if not m:
            return None
        inner = m.group(1).strip()
        # allow vars./env./config. without structural checks here
        if inner.startswith("vars.") or inner.startswith("env.") or inner.startswith("config."):
            return None
        # expect form: nodeId.alias
        if "." not in inner:
            errors.append(f"Invalid reference format in node inputs: '{value}'")
            return None
        src_node, alias = inner.split(".", 1)
        return src_node, alias

    for n in plan.graph:
        # validate inputs of regular nodes; loops/subflow custom handling below
        if n.type:
            # foreach: expect input + itemVar
            if n.type == "loop" and n.foreach:
                if "input" not in n.foreach:
                    errors.append(f"Node {n.id}: foreach.input is required")
                else:
                    src = n.foreach.get("input")
                    # Only validate when statically decidable
                    if isinstance(src, str) and src.startswith("${") and src.endswith("}"):
                        inner = src[2:-1]
                        if inner.startswith("vars."):
                            _, key = inner.split(".", 1)
                            val = plan.vars.get(key)
                            if not isinstance(val, (list, tuple, dict)):
                                errors.append(
                                    f"Node {n.id}: foreach.input (${inner}) must be iterable (vars.{key} is not)"
                                )
                        elif inner.startswith("config."):
                            dotted = inner.split(".", 1)[1] if "." in inner else ""
                            try:
                                val = get_store().resolve(dotted)
                                if val is None or not isinstance(val, (list, tuple, dict)):
                                    errors.append(
                                        f"Node {n.id}: foreach.input (${inner}) must be iterable (config.{dotted} is not)"
                                    )
                            except Exception:
                                errors.append(f"Node {n.id}: foreach.input references invalid config key '{inner}'")
                        else:
                            # Reference to another node or env: skip static validation
                            pass
                    elif not isinstance(src, (list, tuple, dict)):
                        errors.append("Node {n.id}: foreach.input must be an iterable when specified as a literal")
                if n.while_:
                    errors.append(f"Node {n.id}: both foreach and while are set (invalid)")
            # while: must have positive max_iterations
            if n.type == "loop" and n.while_:
                if "max_iterations" not in n.while_:
                    errors.append(f"Node {n.id}: while.max_iterations is required")
                else:
                    try:
                        mi = int(n.while_.get("max_iterations"))
                        if mi <= 0:
                            errors.append(f"Node {n.id}: while.max_iterations must be > 0")
                    except Exception:
                        errors.append(f"Node {n.id}: while.max_iterations must be an integer")
            # subflow: must have call.plan_id
            if n.type == "subflow":
                if not n.call or "plan_id" not in n.call:
                    errors.append(f"Node {n.id}: subflow.call.plan_id is required")
                # inputs mapping should be dict (if present)
                if n.call and (inputs_map := n.call.get("inputs")) is not None and not isinstance(inputs_map, dict):
                    errors.append(f"Node {n.id}: subflow.call.inputs must be a mapping")
            continue
        for k, v in n.inputs.items():
            ref = parse_placeholder(v)
            if ref is None:
                # env/config static checks
                if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
                    inner = v[2:-1]
                    if inner.startswith("env."):
                        env_key = inner.split(".", 1)[1]
                        if env_key not in os.environ:
                            errors.append(f"Node {n.id}: env variable '{env_key}' not set")
                    if inner.startswith("config."):
                        dotted = inner.split(".", 1)[1] if "." in inner else ""
                        val = get_store().resolve(dotted)
                        if val is None:
                            errors.append(f"Node {n.id}: config key not found '{inner}'")
                        else:
                            # If spec declares expected type for this input, enforce basic type check
                            expected_type = None
                            if n.block and n.block in block_specs:
                                spec_in = (block_specs[n.block].inputs or {}).get(k) or {}
                                expected_type = spec_in.get("type")
                            if expected_type is not None and not _py_isinstance_for_type(val, expected_type):
                                errors.append(
                                    f"Node {n.id}: input '{k}' type mismatch for config value (expected {expected_type}, got {type(val).__name__})"
                                )
                continue
            src_node, alias = ref
            if src_node not in node_ids:
                errors.append(
                    f"Node {n.id}: reference to unknown node '{src_node}' in input '{k}'"
                )
                continue
            if alias not in produced_aliases.get(src_node, set()):
                errors.append(
                    f"Node {n.id}: reference to unknown alias '{alias}' from node '{src_node}'"
                )
                continue
            g.add_edge(src_node, n.id)
            # type check (if both sides declare types)
            expected = None
            if n.block and n.block in block_specs:
                spec_in = (block_specs[n.block].inputs or {}).get(k) or {}
                expected = spec_in.get("type")
            actual = produced_types.get(src_node, {}).get(alias)
            if expected is not None and actual is not None and expected != actual:
                errors.append(
                    f"Node {n.id}: input '{k}' type mismatch (expected {expected}, got {actual} from {src_node}.{alias})"
                )

    # 4) DAG cycle check
    if not nx.is_directed_acyclic_graph(g):
        errors.append("Plan graph contains a cycle (must be a DAG)")

    # 5) UI layout nodes existence
    if plan.ui and plan.ui.layout:
        for nid in plan.ui.layout:
            if nid not in node_ids:
                errors.append(f"UI layout references unknown node id: {nid}")

    # 6) Excel疎通の簡易ドライラン検証（出力設定の基本形）
    # excel.write_results の output_config が ${vars.*} を指している場合、基本キーの存在と型を確認
    for n in plan.graph:
        if n.block == "excel.write_results":
            cfg_ref = n.inputs.get("output_config") if isinstance(n.inputs, dict) else None
            if isinstance(cfg_ref, str) and cfg_ref.startswith("${vars.") and cfg_ref.endswith("}"):
                var_key = cfg_ref[7:-1]
                oc = plan.vars.get(var_key)
                if not isinstance(oc, dict):
                    errors.append(f"Node {n.id}: vars.{var_key} must be an object for output_config")
                else:
                    if "sheet" not in oc or not isinstance(oc.get("sheet"), str):
                        errors.append(f"Node {n.id}: output_config.sheet must be string")
                    if "start_row" not in oc or not isinstance(oc.get("start_row"), int):
                        errors.append(f"Node {n.id}: output_config.start_row must be int")
                    cols = oc.get("columns")
                    if not isinstance(cols, list) or not all(isinstance(c, str) for c in cols):
                        errors.append(f"Node {n.id}: output_config.columns must be list[str]")

    return errors


def dry_run_plan(plan: Plan, registry: BlockRegistry) -> bool:
    """Perform a non-destructive dry run by simulating outputs based on specs.

    This does not call external services nor execute UI. It only wires shapes.
    """

    # Build topo order (best-effort). If cycles exist, this will raise.
    errors = validate_plan(plan, registry)
    if errors:
        raise ValueError("Plan is invalid; cannot dry-run: " + "; ".join(errors))

    # Build graph again for topological order
    g = nx.DiGraph()
    node_by_id: Dict[str, Node] = {n.id: n for n in plan.graph}
    for n in plan.graph:
        g.add_node(n.id)
    for n in plan.graph:
        if n.type:
            continue
        for v in n.inputs.values():
            m = _PLACEHOLDER_RE.match(v) if isinstance(v, str) else None
            if m and "." in m.group(1) and not m.group(1).startswith(("vars.", "env.", "config.")):
                src_node = m.group(1).split(".", 1)[0]
                g.add_edge(src_node, n.id)

    order = list(nx.topological_sort(g))

    # Prepare quick access to specs
    latest_specs: Dict[str, BlockSpec] = {
        bid: _pick_latest_spec(specs) for bid, specs in registry.specs_by_id.items()
    }

    def _sample_for_type(t: Any) -> Any:
        """Return a lightweight sample value for a given spec type string.

        Supported: string, number, integer, boolean, array, object, bytes
        Fallback: string
        """
        if not t:
            return "sample"
        ts = str(t).lower()
        if ts in {"string", "str"}:
            return "sample"
        if ts in {"number", "float"}:
            return 0.0
        if ts in {"integer", "int"}:
            return 0
        if ts in {"boolean", "bool"}:
            return False
        if ts in {"array", "list"}:
            return []
        if ts in {"object", "dict"}:
            return {}
        if ts in {"bytes", "binary"}:
            return b""
        return "sample"

    # Simulated context: map (nodeId.alias) -> value
    produced: Dict[tuple[str, str], Any] = {}

    for node_id in order:
        node = node_by_id[node_id]
        if node.type:
            # For loops/subflow, synthesize minimal collect exports when declared
            if node.outputs:
                for local_out, alias in node.outputs.items():
                    # common: collect
                    if local_out == "collect":
                        produced[(node_id, alias)] = []
                    else:
                        produced[(node_id, alias)] = "sample"
            continue
        if not node.block:
            continue
        spec = latest_specs.get(node.block)
        if not spec:
            continue

        # Synthesize outputs with type-aware samples
        for local_out, alias in node.outputs.items():
            out_schema = (spec.outputs or {}).get(local_out) or {}
            sample = _sample_for_type(out_schema.get("type"))
            produced[(node_id, alias)] = sample

    # Excel 書込ブロックの簡易ドライラン（ワークブック生成→書込可能性確認）
    for n in plan.graph:
        if n.block == "excel.write_results":
            try:
                # 1) ワークブックダミー作成
                from openpyxl import Workbook as _WB
                from io import BytesIO as _BIO
                wb = _WB()
                ws = wb.active
                ws.title = "Results"
                bio = _BIO()
                wb.save(bio)
                bio.seek(0)
                wb_bytes = bio.getvalue()

                # 2) 出力設定の決定（vars 参照→辞書→既定）
                oc = {"sheet": "Results", "start_row": 2, "columns": ["A", "B", "C"]}
                cfg_ref = n.inputs.get("output_config") if isinstance(n.inputs, dict) else None
                if isinstance(cfg_ref, str) and cfg_ref.startswith("${vars.") and cfg_ref.endswith("}"):
                    var_key = cfg_ref[7:-1]
                    var_val = plan.vars.get(var_key)
                    if isinstance(var_val, dict):
                        oc = var_val
                elif isinstance(cfg_ref, dict):
                    oc = cfg_ref

                # 3) ダミーデータ
                data = {"items": [{"file": "sample.txt", "count": 1, "sum": 100.0}]}

                # 4) ブロック実行（メモリ上）
                from core.blocks.base import BlockContext
                block = registry.get("excel.write_results")
                ctx = BlockContext(run_id="dryrun", workspace=str(Path.cwd()), vars=dict(plan.vars))
                _ = block.run(ctx, {"workbook": {"name": "dryrun.xlsx", "bytes": wb_bytes}, "data": data, "output_config": oc})
            except Exception as e:  # pragma: no cover (失敗時のみ)
                raise ValueError(f"Dry-run for excel.write_results failed: {e}")

    return True


