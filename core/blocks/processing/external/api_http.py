from __future__ import annotations

from typing import Any, Dict
import time
import json

import requests

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode


class ExternalHTTPApiBlock(ProcessingBlock):
    id = "external.api.http"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        method = str(inputs.get("method", "GET")).upper()
        url = inputs.get("url")
        headers = inputs.get("headers") or {}
        params = inputs.get("params") or {}
        body = inputs.get("body")
        timeout_sec = float(inputs.get("timeout_sec", 30))
        retry = inputs.get("retry") or {}
        max_retries = int(retry.get("max_retries", 0))
        backoff_ms = int(retry.get("backoff_ms", 200))

        if not isinstance(url, str) or not url:
            raise BlockException(BlockError(code=ErrorCode.INPUT_REQUIRED_MISSING, message="url is required"))

        sess = requests.Session()
        last_err: Exception | None = None
        for attempt in range(0, max_retries + 1):
            try:
                resp = sess.request(method, url, headers=headers, params=params, json=body if isinstance(body, (dict, list)) else None, data=None if isinstance(body, (dict, list)) else body, timeout=timeout_sec)
                status = resp.status_code
                text = resp.text
                try:
                    js = resp.json()
                except Exception:
                    js = None
                return {
                    "status": status,
                    "response_json": js,
                    "response_text": text,
                    "headers": dict(resp.headers),
                    "summary": {"ok": resp.ok, "elapsed_ms": int(resp.elapsed.total_seconds() * 1000) if resp.elapsed else None},
                }
            except requests.Timeout as e:  # type: ignore[attr-defined]
                last_err = e
                if attempt < max_retries:
                    time.sleep(backoff_ms / 1000.0)
                    continue
                raise BlockException(BlockError(code=ErrorCode.EXTERNAL_TIMEOUT, message=str(e)))
            except Exception as e:  # noqa: BLE001
                last_err = e
                if attempt < max_retries:
                    time.sleep(backoff_ms / 1000.0)
                    continue
                raise BlockException(BlockError(code=ErrorCode.EXTERNAL_API_ERROR, message=str(e)))

        raise BlockException(BlockError(code=ErrorCode.EXTERNAL_API_ERROR, message=str(last_err)))


