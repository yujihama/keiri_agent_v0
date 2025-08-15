from __future__ import annotations

from typing import Any, Dict, List, Set

from core.blocks.base import BlockContext, ProcessingBlock


class SodCheckBlock(ProcessingBlock):
    id = "control.sod_check"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        assignments = inputs.get("assignments") or []
        matrix = inputs.get("sod_matrix") or {}
        scope = inputs.get("scope") or {}

        if not isinstance(assignments, list):
            assignments = []

        # Build user -> roles/actions sets
        user_roles: Dict[str, Set[str]] = {}
        user_actions: Dict[str, Set[str]] = {}
        for a in assignments:
            if not isinstance(a, dict):
                continue
            uid = str(a.get("user_id")) if a.get("user_id") is not None else None
            if not uid:
                continue
            roles = [str(r) for r in (a.get("roles") or []) if isinstance(r, str)]
            acts = [str(r) for r in (a.get("actions") or []) if isinstance(r, str)]
            user_roles.setdefault(uid, set()).update(roles)
            user_actions.setdefault(uid, set()).update(acts)

        violations: List[Dict[str, Any]] = []
        conflicts = matrix.get("conflicts") if isinstance(matrix, dict) else []
        for c in conflicts if isinstance(conflicts, list) else []:
            if not isinstance(c, dict):
                continue
            rule_type = str(c.get("rule", "mutual_exclusion")).lower()
            roles_any = [str(r) for r in (c.get("roles_any") or []) if isinstance(r, str)]
            roles_all = [str(r) for r in (c.get("roles_all") or []) if isinstance(r, str)]
            actions_any = [str(r) for r in (c.get("actions_any") or []) if isinstance(r, str)]
            actions_all = [str(r) for r in (c.get("actions_all") or []) if isinstance(r, str)]

            for uid, rset in user_roles.items():
                aset = user_actions.get(uid, set())
                if rule_type == "mutual_exclusion":
                    # Having both roles_any on the same user constitutes a violation
                    hits = [r for r in roles_any if r in rset]
                    if len(hits) >= 2:  # at least two conflicting roles
                        violations.append({
                            "user_id": uid,
                            "conflict": {"rule": rule_type, "roles": hits},
                        })
                elif rule_type == "role_action_separation":
                    # roles_all must not co-exist with actions_any (or actions_all)
                    if roles_all and all(r in rset for r in roles_all):
                        if actions_all and all(a in aset for a in actions_all):
                            violations.append({
                                "user_id": uid,
                                "conflict": {"rule": rule_type, "roles": roles_all, "actions": actions_all},
                            })
                        elif actions_any and any(a in aset for a in actions_any):
                            violations.append({
                                "user_id": uid,
                                "conflict": {"rule": rule_type, "roles": roles_all, "actions": actions_any},
                            })

        return {"violations": violations, "summary": {"users": len(user_roles), "violations": len(violations)}}


