from __future__ import annotations

from pathlib import Path
from io import BytesIO
import os
import json

import pytest

from core.blocks.base import BlockContext
from core.blocks.processing.excel.read_data import ExcelReadDataBlock
from core.blocks.processing.excel.update_workbook import ExcelUpdateWorkbookBlock
from core.blocks.processing.excel.write import ExcelWriteBlock
from core.blocks.processing.file.read_csv import ReadCSVBlock
from core.blocks.processing.file.encode_base64 import EncodeBase64Block
from core.blocks.processing.file.parse_zip_2tier import ParseZip2TierBlock
from core.blocks.processing.transforms.rename_fields import RenameFieldsBlock
from core.blocks.processing.transforms.filter import FilterBlock
from core.blocks.processing.transforms.group_by_agg import GroupByAggBlock
from core.blocks.processing.transforms.compute_features import ComputeFeaturesBlock
from core.blocks.processing.transforms.compute_fiscal_quarter import ComputeFiscalQuarterBlock
from core.blocks.processing.transforms.pick import PickBlock
from core.blocks.processing.transforms.flatten_items import FlattenItemsBlock
from core.blocks.processing.transforms.group_evidence import GroupEvidenceBlock
from core.blocks.processing.data_quality.schema_diff import SchemaDiffBlock
from core.blocks.processing.data_quality.validate_rules import ValidateDataQualityRulesBlock
from core.blocks.processing.data_quality.provenance_capture import ProvenanceCaptureBlock
from core.blocks.processing.matching.record_linkage import RecordLinkageBlock
from core.blocks.processing.matching.similarity_cluster import SimilarityClusterBlock
from core.blocks.processing.external.api_http import ExternalHTTPApiBlock
from core.blocks.processing.notifier.notify import NotifyBlock
from core.blocks.processing.security.attestation import SignManifestBlock
from core.blocks.processing.scheduler.trigger import SchedulerTriggerBlock
from core.blocks.processing.evidence.vault_store import EvidenceVaultStoreBlock
from core.blocks.processing.table.pivot import TablePivotBlock
from core.blocks.processing.table.from_rows import FromRowsToDataFrameBlock
from core.blocks.processing.ai.process_llm import ProcessLLMBlock
from core.blocks.processing.control.approval import ApprovalControlBlock


CTX = BlockContext(run_id="unit")


def test_read_csv_bytes():
    blk = ReadCSVBlock()
    out = blk.run(CTX, {"bytes": b"a,b\n1,2\n"})
    assert out["rows"][0] == {"a": "1", "b": "2"}


def test_encode_base64_simple():
    blk = EncodeBase64Block()
    out = blk.run(CTX, {"data": b"hello", "name": "x.txt", "as_data_uri": True})
    enc = out["encoded"]
    assert enc["mime_type"].startswith("text/") or enc["mime_type"] == "application/octet-stream"
    assert enc["size"] == 5
    assert enc["base64"]
    assert enc.get("data_uri", "").startswith("data:")


def test_parse_zip_2tier_minimal():
    import zipfile
    bio = BytesIO()
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("top/a.txt", "hello")
        zf.writestr("b.txt", "world")
    blk = ParseZip2TierBlock()
    out = blk.run(CTX, {"zip_bytes": bio.getvalue()})
    ev = out["evidence"]
    assert ev["total_files"] == 2
    assert "top" in ev["by_dir"] and "" in ev["by_dir"]


def test_rename_fields_move_and_drop():
    blk = RenameFieldsBlock()
    out = blk.run(CTX, {"items": [{"old": 1, "keep": 2}], "rename": {"old": "new"}, "drop": ["keep"]})
    assert out["rows"][0] == {"new": 1}


def test_filter_numeric_and_contains():
    blk = FilterBlock()
    items = [
        {"id": 1, "amount": 10, "text": "Alpha"},
        {"id": 2, "amount": 5, "text": "beta"},
    ]
    conds = [
        {"field": "amount", "operator": "gte", "value": 6},
        {"field": "text", "operator": "contains", "value": "alp"},
    ]
    out = blk.run(CTX, {"items": items, "conditions": conds})
    assert [r["id"] for r in out["filtered"]] == [1]


def test_group_by_agg_sum():
    blk = GroupByAggBlock()
    items = [
        {"dept": "A", "amount": 10},
        {"dept": "A", "amount": 5},
        {"dept": "B", "amount": 3},
    ]
    out = blk.run(CTX, {"items": items, "by": ["dept"], "aggregations": [{"field": "amount", "op": "sum"}]})
    rows = {r["dept"]: r["amount_sum"] for r in out["rows"]}
    assert rows == {"A": 15.0, "B": 3.0}


def test_compute_features_text_and_numeric():
    blk = ComputeFeaturesBlock()
    items = [{"name": "Hello  World", "v": "12"}]
    cfg = {"text": [{"field": "name", "ops": ["normalize", "ngram"], "n": 2}], "numeric": [{"field": "v", "ops": ["log", "zscore"]}]}
    out = blk.run(CTX, {"items": items, "config": cfg})
    feats = out["features"][0]["features"]
    assert "name_len" in feats and "v_raw" in feats


def test_compute_fiscal_quarter_happy():
    blk = ComputeFiscalQuarterBlock()
    out = blk.run(CTX, {"fiscal_year": 2025, "quarter": "Q2", "start_month": 4})
    assert out["period"]["start"].endswith("-07-01")
    assert out["quarter_sheet_name"] == "2025_Q2"


def test_pick_value_variants():
    blk = PickBlock()
    src = {"a": {"b": "123"}}
    assert blk.run(CTX, {"source": src, "path": "a.b", "return": "string"})["value"] == "123"
    assert blk.run(CTX, {"source": src, "path": "a.b", "return": "number"})["value"] == 123.0
    # boolean 判定は文字列 "1"/"true" 等のみ True
    src2 = {"a": {"b": "1"}}
    assert blk.run(CTX, {"source": src2, "path": "a.b", "return": "boolean"})["value"] is True


def test_flatten_items():
    blk = FlattenItemsBlock()
    src = [{"results": {"items": [{"x": 1}, {"x": 2}]}}]
    out = blk.run(CTX, {"results_list": src})
    assert [it["x"] for it in out["items"]] == [1, 2]


def test_group_evidence_top_dir_and_second():
    blk = GroupEvidenceBlock()
    evidence = {"files": [{"path": "top/a.txt"}, {"path": "top/b.txt"}, {"path": "other/c.txt"}], "by_dir": {"top": ["a.txt", "b.txt"], "other": ["c.txt"]}}
    out1 = blk.run(CTX, {"evidence": evidence, "level": "top_dir"})
    keys1 = sorted(g["key"] for g in out1["groups"])
    assert keys1 == ["other", "top"]
    out2 = blk.run(CTX, {"evidence": evidence, "level": "second_dir"})
    # second level keys should be filenames here
    keys2 = sorted(g["key"] for g in out2["groups"])
    assert set(keys2) >= {"a.txt", "b.txt", "c.txt"}


def test_schema_diff_basic():
    blk = SchemaDiffBlock()
    old = {"a": {"type": "string"}, "b": 1}
    new = {"a": {"type": "number"}, "c": True}
    out = blk.run(CTX, {"schema_old": old, "schema_new": new})
    types = sorted(set(d["type"] for d in out["diffs"]))
    assert set(types) >= {"added", "removed", "changed"}


def test_validate_rules_required_unique_range_regex():
    blk = ValidateDataQualityRulesBlock()
    items = [{"id": 1, "name": "A", "score": 50}, {"id": 2, "name": "A", "score": 101}, {"id": 3, "name": None}]
    rules = [
        {"id": "r1", "type": "required", "fields": ["name"]},
        {"id": "r2", "type": "unique", "field": "name"},
        {"id": "r3", "type": "range", "field": "score", "min": 0, "max": 100},
        {"id": "r4", "type": "regex", "field": "name", "pattern": r"^[A-Z]+$"},
    ]
    out = blk.run(CTX, {"items": items, "rules": rules})
    assert out["summary"]["violations"] >= 2


def test_provenance_capture_attaches_metadata():
    blk = ProvenanceCaptureBlock()
    out = blk.run(CTX, {"items": [{"x": 1}]})
    pv = out["items_with_provenance"][0]["__provenance__"]
    assert pv.get("run_id") == CTX.run_id


def test_record_linkage_exact_and_fuzzy():
    blk = RecordLinkageBlock()
    left = [{"id": 1, "name": "Alice"}]
    right = [{"id": "A", "name": "alice"}]
    keys = [{"left": "name", "right": "name", "type": "string"}]
    out_fuzzy = blk.run(CTX, {"left": left, "right": right, "keys": keys, "strategy": "fuzzy", "fuzzy": {"threshold": 0.8}})
    assert out_fuzzy["matches"][0]["score"] >= 0.8
    out_exact = blk.run(CTX, {"left": left, "right": right, "keys": keys, "strategy": "exact"})
    assert out_exact["matches"] == []


def test_similarity_cluster_minhash():
    blk = SimilarityClusterBlock()
    items = [{"text": "hello world"}, {"text": "hello  world"}, {"text": "different text"}]
    spec = {"text_fields": ["text"]}
    out = blk.run(CTX, {"items": items, "feature_spec": spec, "method": "minhash", "threshold": 0.5})
    assert out["summary"]["clusters"] >= 1


def test_external_api_http_get_httpbin_or_expected_error():
    blk = ExternalHTTPApiBlock()
    try:
        out = blk.run(CTX, {"method": "GET", "url": "https://httpbin.org/get", "timeout_sec": 10})
        # ステータスは環境依存（502等）になり得るため、構造・型を検証
        assert isinstance(out.get("status"), int)
        assert isinstance(out.get("headers"), dict)
        assert "response_text" in out
    except Exception as e:
        # 実ネットワークが不可の環境でも実装の例外系を検証
        from core.errors import BlockException

        assert isinstance(e, BlockException)


def test_notifier_notify_webhook_httpbin_or_expected_error():
    blk = NotifyBlock()
    try:
        out = blk.run(CTX, {"provider": "webhook", "target": {"url": "https://httpbin.org/post"}, "title": "t", "message": "m"})
        assert isinstance(out.get("ok"), bool)
    except Exception as e:
        from core.errors import BlockException

        assert isinstance(e, BlockException)


def test_sign_manifest_ed25519_from_env_key():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization

    private_key = ed25519.Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    os.environ["SIGNING_KEY"] = pem
    blk = SignManifestBlock()
    out = blk.run(CTX, {"manifest": {"a": 1}, "key_ref": "SIGNING_KEY", "algo": "ed25519"})
    assert out["signature"] and out["signed_manifest"]["_signature"]["algo"] == "ed25519"


def test_scheduler_trigger_cron():
    blk = SchedulerTriggerBlock()
    out = blk.run(CTX, {"schedule": {"cron": "*/5 * * * *"}})
    assert out["triggered"] is True


def test_evidence_vault_store_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("KEIRI_AGENT_EVIDENCE_DIR", str(tmp_path))
    blk = EvidenceVaultStoreBlock()
    data = b"artifact"
    out = blk.run(CTX, {"items": [{"name": "a.bin", "bytes": data}]})
    stored = out["stored"][0]
    assert Path(stored["path"]).exists()


def test_table_pivot_from_rows():
    blk = TablePivotBlock()
    rows = [
        {"dept": "A", "month": "Jan", "amount": 10},
        {"dept": "A", "month": "Feb", "amount": 5},
        {"dept": "B", "month": "Jan", "amount": 3},
    ]
    out = blk.run(CTX, {"rows": rows, "index": "dept", "columns": "month", "values": "amount", "aggfunc": "sum"})
    assert out["summary"]["cols"] >= 2 and out["rows"]


def test_from_rows_to_dataframe():
    from core.blocks.processing.table.from_rows import FromRowsToDataFrameBlock

    blk = FromRowsToDataFrameBlock()
    out = blk.run(CTX, {"rows": [{"a": 1}, {"a": 2}]})
    assert out["dataframe"] is not None


def test_approval_control_rules_and_violations():
    blk = ApprovalControlBlock()
    route = {
        "levels": [
            {"id": "L1", "approvers": ["u1", "u2"], "rule": {"type": "all"}},
            {"id": "L2", "approvers": ["u3"], "rule": {"type": "any"}},
        ]
    }
    decisions = [
        {"level_id": "L2", "approver_id": "u3", "decision": "approve"},  # out-of-order
        {"level_id": "L1", "approver_id": "u1", "decision": "approve"},
        {"level_id": "L1", "approver_id": "u4", "decision": "approve"},  # unauthorized
    ]
    out = blk.run(CTX, {"route_definition": route, "decisions": decisions})
    types = sorted(set(v["type"] for v in out["violations"]))
    assert "unauthorized_approver" in types and "order_violation" in types


def test_excel_read_write_update_roundtrip():
    # create workbook, append a table, then read back rows
    write_blk = ExcelWriteBlock()
    w1 = write_blk.run(CTX, {"workbook": b""})
    upd_blk = ExcelUpdateWorkbookBlock()
    u1 = upd_blk.run(
        CTX,
        {
            "workbook": {"name": "t.xlsx", "bytes": w1["workbook_updated"]["bytes"]},
            "operations": [
                {"type": "append_table", "sheet_name": "S", "target": "A1", "data": [{"A": "v", "B": 123}]}
            ],
        },
    )
    rd_blk = ExcelReadDataBlock()
    out = rd_blk.run(
        CTX,
        {
            "workbook": {"bytes": u1["workbook_updated"]["bytes"]},
            "read_config": {"sheets": [{"name": "S", "header_row": 1}], "mode": "single"},
        },
    )
    assert out["data"]["S"][0]["A"] == "v"


def test_transforms_join_numeric_equivalence():
    from core.blocks.processing.transforms.join import JoinBlock

    blk = JoinBlock()
    left = [{"k": "1.0"}, {"k": "2"}]
    right = [{"k": 1}, {"k": 2.0}]
    out = blk.run(CTX, {"left": left, "right": right, "left_key": "k", "right_key": "k", "select": {"lv": "left.k", "rv": "right.k"}})
    assert len(out["rows"]) == 2


def test_external_llm_blocks_behavior_depends_on_env():
    # ai.process_llm and nlp.summarize_structured share same class
    blk = ProcessLLMBlock()
    have_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
    if not have_key:
        with pytest.raises(Exception):
            blk.run(CTX, {"evidence_data": {}, "output_schema": {"foo": {"type": "object"}}})
    else:
        # If keys are present, perform a minimal call; allow any structured result
        out = blk.run(
            CTX,
            {
                "evidence_data": {"rows": [{"a": 1}]},
                "instruction": "Return an object under key foo.",
                "output_schema": {"foo": {"type": "object"}},
                "per_table_rows": 1,
                "per_file_chars": 200,
                "allow_images": False,
            },
        )
        assert isinstance(out, dict) and "summary" in out


