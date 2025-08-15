from __future__ import annotations

from typing import Any, Dict, List, Tuple
from datetime import datetime

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode


class ApprovalControlBlock(ProcessingBlock):
    """Multi-level approval evaluation and route integrity checker.

    Inputs
    ------
    - route_definition: {
        levels: [
          { id: str, approvers: [str], rule: { type: "any"|"all"|"n_of_m", n?: int } }, ...
        ],
        due_date?: ISO8601 string
      }
    - decisions: [ { level_id, approver_id, decision: "approve"|"reject", comment?, timestamp? } ]
    - context: any metadata

    Outputs
    -------
    - approved: bool
    - route_log: normalized log with per-level status and detected issues
    - violations: list of deviations
    """

    id = "control.approval"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        route_def = inputs.get("route_definition") or {}
        decisions_in = inputs.get("decisions") or []

        if not isinstance(route_def, dict) or not isinstance(route_def.get("levels"), list):
            raise BlockException(
                BlockError(
                    code=ErrorCode.INPUT_VALIDATION_FAILED,
                    message="route_definition.levels must be a list",
                    details={"route_definition": route_def},
                    recoverable=False,
                )
            )

        levels: List[Dict[str, Any]] = [l for l in route_def["levels"] if isinstance(l, dict)]
        level_order: Dict[str, int] = {str(l.get("id")): idx for idx, l in enumerate(levels)}
        # normalize decisions: keep last by (level_id, approver_id)
        normalized_decisions: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for d in decisions_in if isinstance(decisions_in, list) else []:
            if not isinstance(d, dict):
                continue
            lid = str(d.get("level_id")) if d.get("level_id") is not None else ""
            aid = str(d.get("approver_id")) if d.get("approver_id") is not None else ""
            if not lid or not aid:
                continue
            # parse/normalize timestamp for ordering when necessary
            ts_raw = d.get("timestamp")
            ts: float
            if isinstance(ts_raw, (int, float)):
                ts = float(ts_raw)
            elif isinstance(ts_raw, str):
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()
                except Exception:
                    ts = 0.0
            else:
                ts = 0.0
            cur = normalized_decisions.get((lid, aid))
            if not cur or ts >= cur.get("__ts__", -1.0):
                nd = dict(d)
                nd["__ts__"] = ts
                normalized_decisions[(lid, aid)] = nd

        # Build per-level buckets
        per_level: Dict[str, List[Dict[str, Any]]] = {str(l.get("id")): [] for l in levels}
        for (_lid, _aid), nd in normalized_decisions.items():
            if _lid in per_level:
                per_level[_lid].append(nd)

        violations: List[Dict[str, Any]] = []
        route_log: Dict[str, Any] = {"levels": []}

        # Order violation detection: if any decision exists for a level with index > current index while a previous level is not yet satisfied
        prior_satisfied: Dict[str, bool] = {}
        def _satisfy_rule(lcfg: Dict[str, Any], decs: List[Dict[str, Any]]) -> tuple[bool, Dict[str, Any]]:
            rule = lcfg.get("rule") or {}
            rtype = str((rule.get("type") or "any")).lower()
            approvers = lcfg.get("approvers") or []
            explicit_users = [a for a in approvers if isinstance(a, str) and not a.startswith("role:")]

            approves = [d for d in decs if str(d.get("decision")).lower() == "approve"]
            rejects = [d for d in decs if str(d.get("decision")).lower() == "reject"]

            # Unauthorized approver detection (only for explicit ids)
            for d in decs:
                aid = str(d.get("approver_id"))
                if explicit_users and aid not in explicit_users:
                    violations.append({
                        "type": "unauthorized_approver",
                        "level_id": lcfg.get("id"),
                        "approver_id": aid,
                    })

            if rejects:
                return False, {"reason": "rejected", "rejects": len(rejects)}

            if rtype == "all":
                # all explicit users must approve
                needed = set(explicit_users)
                got = set(str(d.get("approver_id")) for d in approves)
                missing = sorted(list(needed - got))
                return (len(missing) == 0, {"missing_explicit": missing})
            if rtype == "n_of_m":
                try:
                    n = int(rule.get("n", 1))
                except Exception:
                    n = 1
                return (len(approves) >= n, {"n": n, "approves": len(approves)})
            # default any
            return (len(approves) >= 1, {"approves": len(approves)})

        # Evaluate levels in order
        satisfied_up_to_index = -1
        for idx, lcfg in enumerate(levels):
            lid = str(lcfg.get("id"))
            decs = per_level.get(lid, [])
            ok, detail = _satisfy_rule(lcfg, decs)
            status = "satisfied" if ok else ("rejected" if detail.get("reason") == "rejected" else "pending")
            if ok:
                satisfied_up_to_index = idx
            prior_satisfied[lid] = ok
            route_log["levels"].append({
                "id": lid,
                "rule": lcfg.get("rule") or {"type": "any"},
                "approvers": lcfg.get("approvers") or [],
                "decisions": [
                    {
                        "approver_id": d.get("approver_id"),
                        "decision": d.get("decision"),
                        "comment": d.get("comment"),
                        "timestamp": d.get("timestamp"),
                    }
                    for d in sorted(decs, key=lambda x: x.get("__ts__", 0.0))
                ],
                "status": status,
                "detail": detail,
            })

        # Out-of-order decisions: any decision recorded for levels beyond the first unsatisfied level
        first_unsatisfied_index = None
        for idx, entry in enumerate(route_log["levels"]):
            if entry["status"] != "satisfied":
                first_unsatisfied_index = idx
                break
        if first_unsatisfied_index is not None:
            for lid, decs in per_level.items():
                lidx = level_order.get(lid, 10**6)
                if lidx > first_unsatisfied_index:
                    for d in decs:
                        violations.append({
                            "type": "order_violation",
                            "level_id": lid,
                            "approver_id": d.get("approver_id"),
                        })

        # Determine final approved status
        has_reject = any(e.get("status") == "rejected" for e in route_log["levels"])
        all_ok = all(e.get("status") == "satisfied" for e in route_log["levels"]) and not has_reject

        # Missing levels (no decisions and rule not satisfied)
        for entry in route_log["levels"]:
            if entry["status"] == "pending":
                violations.append({"type": "level_incomplete", "level_id": entry.get("id")})

        return {"approved": bool(all_ok), "route_log": route_log, "violations": violations}


