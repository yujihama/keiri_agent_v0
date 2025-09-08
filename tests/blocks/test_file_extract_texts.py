from __future__ import annotations

from pathlib import Path
import base64

import pytest

from core.blocks.base import BlockContext
from core.blocks.processing.file.extract_texts import ExtractTextsBlock


CTX = BlockContext(run_id="unit")


def test_extract_texts_from_bytes_and_base64_and_path(tmp_path: Path):
    blk = ExtractTextsBlock()

    # temp file path case
    p = tmp_path / "a.txt"
    p.write_text("Hello World", encoding="utf-8")

    files = [
        {"name": "b.txt", "bytes": b"Alpha Beta"},
        {"name": "c.txt", "base64": base64.b64encode(b"Gamma Delta").decode("ascii")},
        {"name": "a.txt", "bytes": str(p)},  # path in bytes field is allowed
        {"name": "bad.txt", "base64": "@@@"},  # invalid -> ignored
    ]

    out = blk.run(CTX, {"files": files})
    ev = out.get("evidence") or {}
    items = ev.get("files") or []
    assert isinstance(items, list) and len(items) == 3
    names = {it.get("name") for it in items}
    assert {"a.txt", "b.txt", "c.txt"}.issubset(names)
    # ext/size presence
    assert all("ext" in it and "size" in it and "text_excerpt" in it for it in items)


def test_extract_texts_invalid_input_raises():
    blk = ExtractTextsBlock()
    with pytest.raises(Exception):
        blk.run(CTX, {"files": []})

