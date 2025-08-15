from __future__ import annotations

from typing import Any, Dict
import os
import json
import base64

import requests

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode


class NotifyBlock(ProcessingBlock):
    id = "notifier.notify"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        provider = str(inputs.get("provider", "webhook")).lower()
        target = inputs.get("target") or {}
        message = inputs.get("message") or ""
        title = inputs.get("title") or ""
        attachments = inputs.get("attachments") or []
        options = inputs.get("options") or {}

        def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None):
            try:
                r = requests.post(url, json=payload, headers=headers or {}, timeout=15)
                return r.ok, {"status": r.status_code, "text": r.text}
            except Exception as e:  # noqa: BLE001
                raise BlockException(BlockError(code=ErrorCode.EXTERNAL_API_ERROR, message=str(e)))

        if provider == "slack":
            key = target.get("webhook_key") or "SLACK_WEBHOOK_URL"
            url = os.getenv(str(key), target.get("url"))
            if not url:
                raise BlockException(BlockError(code=ErrorCode.CONFIG_MISSING, message="Slack webhook URL not provided"))
            payload = {"text": (title + "\n" if title else "") + str(message)}
            ok, resp = _post_json(url, payload)
            return {"ok": bool(ok), "response": resp}
        if provider == "teams":
            key = target.get("webhook_key") or "TEAMS_WEBHOOK_URL"
            url = os.getenv(str(key), target.get("url"))
            if not url:
                raise BlockException(BlockError(code=ErrorCode.CONFIG_MISSING, message="Teams webhook URL not provided"))
            payload = {"text": (title + "\n" if title else "") + str(message)}
            ok, resp = _post_json(url, payload)
            return {"ok": bool(ok), "response": resp}
        if provider == "email":
            # Minimal SMTP-less email stub via webhook gateway if provided
            url = os.getenv("EMAIL_WEBHOOK_URL", target.get("url"))
            if not url:
                raise BlockException(BlockError(code=ErrorCode.CONFIG_MISSING, message="EMAIL_WEBHOOK_URL not configured"))
            payload = {"title": title, "message": message, "to": target.get("to"), "attachments": attachments}
            ok, resp = _post_json(url, payload)
            return {"ok": bool(ok), "response": resp}
        # generic webhook
        url = target.get("url") or os.getenv(str(target.get("webhook_key") or "WEBHOOK_URL"))
        if not url:
            raise BlockException(BlockError(code=ErrorCode.CONFIG_MISSING, message="Webhook URL not provided"))
        payload = {"title": title, "message": message, "attachments": attachments, "options": options}
        ok, resp = _post_json(url, payload)
        return {"ok": bool(ok), "response": resp}


