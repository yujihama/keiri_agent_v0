from __future__ import annotations

import os
import pytest

from core.blocks.base import BlockContext
from core.blocks.processing.security.attestation import SignManifestBlock


CTX = BlockContext(run_id="unit")


def test_sign_manifest_missing_key_ref_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SIGNING_KEY", raising=False)
    blk = SignManifestBlock()
    with pytest.raises(Exception):
        blk.run(CTX, {"manifest": {"a": 1}, "key_ref": "SIGNING_KEY", "algo": "ed25519"})


def test_sign_manifest_invalid_pem_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SIGNING_KEY", "INVALID_PEM")
    blk = SignManifestBlock()
    with pytest.raises(Exception):
        blk.run(CTX, {"manifest": {"a": 1}, "key_ref": "SIGNING_KEY", "algo": "ed25519"})


def test_sign_manifest_unsupported_algo(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SIGNING_KEY", "INVALID_PEM")
    blk = SignManifestBlock()
    with pytest.raises(Exception):
        blk.run(CTX, {"manifest": {"a": 1}, "key_ref": "SIGNING_KEY", "algo": "unknown_algo"})

