from __future__ import annotations

from typing import Any, Dict
import os
import json
import base64

from cryptography.hazmat.primitives.asymmetric import ed25519, rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.exceptions import InvalidSignature

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode


class SignManifestBlock(ProcessingBlock):
    id = "security.attestation.sign_manifest"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        manifest = inputs.get("manifest") or {}
        key_ref = inputs.get("key_ref") or "SIGNING_KEY"
        algo = str(inputs.get("algo", "ed25519")).lower()

        # resolve private key from environment by key_ref
        pem = os.getenv(str(key_ref))
        if not pem:
            raise BlockException(BlockError(code=ErrorCode.CONFIG_MISSING, message=f"Private key not found for {key_ref}"))

        data = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")

        if algo == "ed25519":
            try:
                private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)  # type: ignore[arg-type]
                if not isinstance(private_key, ed25519.Ed25519PrivateKey):
                    raise ValueError("Not an Ed25519 private key")
                signature = private_key.sign(data)
                sig_b64 = base64.b64encode(signature).decode("ascii")
                signed_manifest = {**manifest, "_signature": {"algo": algo, "key_ref": key_ref, "sig": sig_b64}}
                return {"signature": sig_b64, "signed_manifest": signed_manifest}
            except Exception as e:  # noqa: BLE001
                raise BlockException(BlockError(code=ErrorCode.BLOCK_EXECUTION_FAILED, message=str(e)))
        elif algo == "rsa":
            try:
                private_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)  # type: ignore[arg-type]
                if not isinstance(private_key, rsa.RSAPrivateKey):
                    raise ValueError("Not an RSA private key")
                signature = private_key.sign(data, padding.PKCS1v15(), hashes.SHA256())
                sig_b64 = base64.b64encode(signature).decode("ascii")
                signed_manifest = {**manifest, "_signature": {"algo": algo, "key_ref": key_ref, "sig": sig_b64}}
                return {"signature": sig_b64, "signed_manifest": signed_manifest}
            except Exception as e:  # noqa: BLE001
                raise BlockException(BlockError(code=ErrorCode.BLOCK_EXECUTION_FAILED, message=str(e)))
        else:
            raise BlockException(BlockError(code=ErrorCode.CONFIG_INVALID, message=f"Unsupported algo: {algo}"))


