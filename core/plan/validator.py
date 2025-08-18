from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple
import ast
import os
from pathlib import Path

import networkx as nx
from packaging.version import Version

from core.blocks.registry import BlockRegistry, BlockSpec
from .graph_utils import build_dependency_graph
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

    # Helper function to check vars references
    def check_vars_ref(value: Any, node_id: str, field_name: str) -> None:
        """Check if ${vars.*} references exist in plan.vars"""
        if isinstance(value, str) and value.startswith("${vars.") and value.endswith("}"):
            var_path = value[7:-1]  # Remove ${vars. and }
            # Support nested path like vars.a.b.c
            parts = var_path.split(".")
            current = plan.vars
            for i, part in enumerate(parts):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    errors.append(
                        f"Node {node_id}: {field_name} references undefined variable '${{{value[2:-1]}}}'"
                    )
                    break
        elif isinstance(value, dict):
            for k, v in value.items():
                check_vars_ref(v, node_id, f"{field_name}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                check_vars_ref(v, node_id, f"{field_name}[{i}]")

    for n in plan.graph:
        # Check all inputs for vars references
        for input_key, input_value in n.inputs.items():
            check_vars_ref(input_value, n.id, f"input '{input_key}'")
        
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
                        errors.append(f"Node {n.id}: foreach.input must be an iterable when specified as a literal")
                if n.while_:
                    errors.append(f"Node {n.id}: both foreach and while are set (invalid)")
                # Check body structure for foreach loops
                if n.body:
                    if not isinstance(n.body, dict):
                        errors.append(f"Node {n.id}: foreach.body must be a dict")
                    elif "plan" not in n.body:
                        errors.append(f"Node {n.id}: foreach.body must contain 'plan' (got: {list(n.body.keys())})")
                    else:
                        # Validate the inner plan structure
                        inner_plan = n.body.get("plan")
                        if not isinstance(inner_plan, dict):
                            errors.append(f"Node {n.id}: foreach.body.plan must be a dict")
                        else:
                            if "id" not in inner_plan:
                                errors.append(f"Node {n.id}: foreach.body.plan.id is required")
                            if "version" not in inner_plan:
                                errors.append(f"Node {n.id}: foreach.body.plan.version is required")
                            if "graph" not in inner_plan:
                                errors.append(f"Node {n.id}: foreach.body.plan.graph is required")
                            elif not isinstance(inner_plan.get("graph"), list):
                                errors.append(f"Node {n.id}: foreach.body.plan.graph must be a list")
                else:
                    errors.append(f"Node {n.id}: foreach loops require body")
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
                # Check body structure for while loops
                if n.body:
                    if not isinstance(n.body, dict):
                        errors.append(f"Node {n.id}: while.body must be a dict")
                    elif "plan" not in n.body:
                        errors.append(f"Node {n.id}: while.body must contain 'plan' (got: {list(n.body.keys())})")
                    else:
                        # Validate the inner plan structure
                        inner_plan = n.body.get("plan")
                        if not isinstance(inner_plan, dict):
                            errors.append(f"Node {n.id}: while.body.plan must be a dict")
                        else:
                            if "id" not in inner_plan:
                                errors.append(f"Node {n.id}: while.body.plan.id is required")
                            if "version" not in inner_plan:
                                errors.append(f"Node {n.id}: while.body.plan.version is required")
                            if "graph" not in inner_plan:
                                errors.append(f"Node {n.id}: while.body.plan.graph is required")
                            elif not isinstance(inner_plan.get("graph"), list):
                                errors.append(f"Node {n.id}: while.body.plan.graph must be a list")
                else:
                    errors.append(f"Node {n.id}: while loops require body")
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
                else:
                    # Literal provided: if spec declares enum, enforce membership
                    if n.block and n.block in block_specs:
                        spec_in = (block_specs[n.block].inputs or {}).get(k) or {}
                        enum_vals = spec_in.get("enum")
                        if enum_vals and isinstance(enum_vals, list):
                            # Only check simple scalar literals (str/number/bool)
                            if isinstance(v, (str, int, float, bool)):
                                if v not in enum_vals:
                                    errors.append(
                                        f"Node {n.id}: input '{k}' value '{v}' not in enum {enum_vals}"
                                    )
                continue
            src_node, alias = ref
            if src_node not in node_ids:
                errors.append(
                    f"Node {n.id}: reference to unknown node '{src_node}' in input '{k}'"
                )
                continue
            # allow nested path after alias (e.g., compute_q.period.end)
            alias_root = alias.split(".", 1)[0]
            if alias_root not in produced_aliases.get(src_node, set()):
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
            # Use root alias type for comparison
            actual = produced_types.get(src_node, {}).get(alias_root)
            if expected is not None and actual is not None and expected != actual:
                # 緩和: 参照元が object でエイリアスのネストで取得する場合は型不一致を許容
                # 例: expected=int だが ${node.alias.path} で alias が object のとき
                primitive_expected = str(expected).lower() in {"string", "str", "number", "float", "integer", "int", "boolean", "bool", "bytes", "binary"}
                if not (primitive_expected and str(actual).lower() == "object" and "." in alias):
                    errors.append(
                        f"Node {n.id}: input '{k}' type mismatch (expected {expected}, got {actual} from {src_node}.{alias_root})"
                    )

        # Additional semantic checks for known blocks
        if n.block == "ai.process_llm":
            # output_schema must be non-empty object
            oschema = n.inputs.get("output_schema") if isinstance(n.inputs, dict) else None
            if not isinstance(oschema, dict) or not oschema:
                errors.append(f"Node {n.id}: ai.process_llm requires non-empty 'output_schema' object")
            # prompt or instruction must be provided (at least one)
            prompt_v = n.inputs.get("prompt") if isinstance(n.inputs, dict) else None
            instr_v = n.inputs.get("instruction") if isinstance(n.inputs, dict) else None
            if not (isinstance(prompt_v, str) and prompt_v.strip()) and not (isinstance(instr_v, str) and instr_v.strip()):
                errors.append(f"Node {n.id}: ai.process_llm requires 'prompt' or 'instruction'")
        # 旧 excel.write_results は廃止（特例検証は不要）

    # 4) DAG cycle check
    if not nx.is_directed_acyclic_graph(g):
        errors.append("Plan graph contains a cycle (must be a DAG)")

    # 5) UI layout nodes existence
    if plan.ui and plan.ui.layout:
        for nid in plan.ui.layout:
            if nid not in node_ids:
                errors.append(f"UI layout references unknown node id: {nid}")

    # 6) Excel疎通の簡易ドライラン検証（excel.write は実行時に整合性を確認するため特例不要）

    return errors


def dry_run_plan(plan: Plan, registry: BlockRegistry) -> bool:
    """Perform a non-destructive dry run by simulating outputs based on specs.

    This does not call external services nor execute UI. It only wires shapes.
    """

    # Build topo order (best-effort). If cycles exist, this will raise.
    errors = validate_plan(plan, registry)
    if errors:
        raise ValueError("Plan is invalid; cannot dry-run: " + "; ".join(errors))

    # Build graph again for topological order using shared utility
    g = build_dependency_graph(plan)
    node_by_id: Dict[str, Node] = {n.id: n for n in plan.graph}

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

    # Excel 書込の特例ドライランは不要（excel.write は正常性を内包検証）

    return True


