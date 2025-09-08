from __future__ import annotations

from pathlib import Path

from core.blocks.base import BlockContext
from core.blocks.processing.control.policy_enforce import PolicyEnforceBlock
from core.blocks.processing.control.sampling import SamplingBlock
from core.blocks.processing.control.sod_check import SodCheckBlock


CTX = BlockContext(run_id="unit")


def test_policy_enforce_violations_and_lenient_pass():
    blk = PolicyEnforceBlock()
    items = [
        {"id": 1, "vendor_id": "V001", "amount": 200000},  # threshold violation, missing po_no
        {"id": 2, "vendor_id": "V999", "amount": 50000, "po_no": "PO-1"},  # ok
    ]
    policy = {
        "rules": [
            {"id": "po_threshold", "type": "threshold", "field": "amount", "op": "lte", "value": 100000},
            {"id": "required_po", "type": "required", "fields": ["po_no"]},
        ],
        "exceptions": {"allow_list": ["vendor_id:V001"]},
    }

    # strict -> violations exist
    out = blk.run(CTX, {"items": items, "policy": policy, "options": {"mode": "strict"}})
    assert out["passed"] is False
    vids = {v["rule_id"] for v in out["violations"]}
    # vendor_id:V001 is allow-listed; only required_po should remain for id=1
    assert "required_po" in vids

    # lenient -> passed True but violations included
    out2 = blk.run(CTX, {"items": items, "policy": policy, "options": {"mode": "lenient"}})
    assert out2["passed"] is True
    assert out2["summary"]["violations"] >= 1


def test_sampling_random_systematic_and_attribute_seed():
    blk = SamplingBlock()
    pop = [{"id": i, "group": "A" if i % 2 == 0 else "B", "score": i} for i in range(10)]

    # random with seed is deterministic
    r1 = blk.run(CTX, {"population": pop, "method": "random", "size": 3, "seed": 42})
    r2 = blk.run(CTX, {"population": pop, "method": "random", "size": 3, "seed": 42})
    assert r1["samples"] == r2["samples"]

    # systematic selects exact size
    sys = blk.run(CTX, {"population": pop, "method": "systematic", "size": 3, "seed": 1})
    assert len(sys["samples"]) == 3

    # attribute filtering narrows candidates
    attr = blk.run(
        CTX,
        {
            "population": pop,
            "method": "attribute",
            "size": 2,
            "attribute_rules": [{"field": "group", "operator": "eq", "value": "A"}],
        },
    )
    assert all(x.get("group") == "A" for x in attr["samples"]) and len(attr["samples"]) == 2


def test_sod_check_mutual_and_role_action():
    blk = SodCheckBlock()
    assignments = [
        {"user_id": "u1", "roles": ["requester", "approver"], "actions": ["post_journal"]},
        {"user_id": "u2", "roles": ["requester"], "actions": ["view"]},
    ]
    sod = {
        "conflicts": [
            {"roles_any": ["requester", "approver"], "rule": "mutual_exclusion"},
            {"roles_all": ["requester"], "actions_any": ["post_journal"], "rule": "role_action_separation"},
        ]
    }
    out = blk.run(CTX, {"assignments": assignments, "sod_matrix": sod})
    assert out["summary"]["violations"] >= 1
    uids = {v.get("user_id") for v in out["violations"]}
    assert "u1" in uids

