from __future__ import annotations

from core.blocks.base import BlockContext
from core.blocks.processing.transforms.attach_context import AttachContextBlock
from core.blocks.processing.transforms.coerce_values import CoerceValuesBlock
from core.blocks.processing.transforms.replace_values import ReplaceValuesBlock
from core.blocks.processing.transforms.select_by_indices import SelectByIndicesBlock


CTX = BlockContext(run_id="unit")


def test_attach_context_merge_and_as_key():
    blk = AttachContextBlock()
    items = [{"a": 1}, {"b": 2}]
    ctx = {"x": 9}
    # merge top-level
    m1 = blk.run(CTX, {"items": items, "context": ctx})
    rows = m1["items"]
    assert rows[0]["a"] == 1 and rows[0]["x"] == 9
    # as-key wrapper
    m2 = blk.run(CTX, {"items": items, "context": ctx, "as": "meta"})
    assert isinstance(m2["items"][0]["meta"], dict)


def test_coerce_values_number_bool_date_string():
    blk = CoerceValuesBlock()
    rows = [
        {"n": "1,234", "b": "true", "d": "2025-06-30", "s": 123},
        {"n": "-5", "b": 0, "d": "2025/06/30 12:00:00", "s": None},
    ]
    specs = [
        {"field": "n", "type": "number"},
        {"field": "b", "type": "boolean"},
        {"field": "d", "type": "date"},
        {"field": "s", "type": "string"},
    ]
    out = blk.run(CTX, {"items": rows, "specs": specs})
    r1, r2 = out["rows"]
    assert r1["n"] == 1234 and r2["n"] == -5
    assert r1["b"] is True and r2["b"] is False
    assert str(r1["d"]).startswith("2025-06-30")
    assert r2["s"] == "None"


def test_replace_values_equals_contains_regex_case_insensitive():
    blk = ReplaceValuesBlock()
    items = [
        {"name": "ALPHA"},
        {"name": "beta"},
        {"name": "gamma-123"},
    ]
    rules = [
        {"field": "name", "match": "equals", "mappings": [{"from": "alpha", "to": "A"}]},
        {"field": "name", "match": "contains", "mappings": [{"from": "et", "to": "B"}]},
        {"field": "name", "match": "regex", "mappings": [{"from": r"gamma-\d+", "to": "G"}]},
    ]
    out = blk.run(CTX, {"items": items, "rules": rules})
    vals = [r["name"] for r in out["rows"]]
    assert vals == ["A", "B", "G"]


def test_select_by_indices_coerces_and_bounds():
    blk = SelectByIndicesBlock()
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    out = blk.run(CTX, {"items": rows, "indices": ["0", 2, 99, "x"]})
    picked = [r["id"] for r in out["rows"]]
    assert picked == [1, 3]

