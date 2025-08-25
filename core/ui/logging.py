from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional
import contextvars

import streamlit as st


# Context for structured logs
_log_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("keiri_log_ctx", default={})


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = _log_ctx.get({})
        record.plan_id = ctx.get("plan_id", "")
        record.run_id = ctx.get("run_id", "")
        record.node_id = ctx.get("node_id", "")
        record.tag = ctx.get("tag", "")
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "plan_id": getattr(record, "plan_id", ""),
            "run_id": getattr(record, "run_id", ""),
            "node_id": getattr(record, "node_id", ""),
            "tag": getattr(record, "tag", ""),
        }
        if record.exc_info:
            base["error"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)


_logger = logging.getLogger("keiri")
_logger.propagate = False


class _ConsoleSuppressFilter(logging.Filter):
    """Suppress console output for specific messages while keeping file logs.

    Suppressed substrings are checked against the rendered message via
    record.getMessage(). If any substring is contained, the record is filtered
    out for the console handler only.
    example:
    KEIRI_SUPPRESS_CONSOLE_MESSAGES=DAG描画の更新に失敗しました。|
    KEIRI_SUPPRESS_CONSOLE_MESSAGES=DAG描画の更新に失敗しました。|DAG描画の更新に失敗しました。
    """

    def __init__(self, suppressed_substrings: list[str] | None = None) -> None:
        super().__init__()
        self._suppressed = suppressed_substrings or []

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for s in self._suppressed:
            if s and s in msg:
                return False
        return True


def configure_logging(log_dir: str | None = None, *, level: str | None = None, console: bool = True) -> None:
    # Idempotent: clear only our handlers
    if _logger.handlers:
        return

    lvl_name = (level or os.getenv("KEIRI_LOG_LEVEL", "INFO")).upper()
    lvl = getattr(logging, lvl_name, logging.INFO)
    _logger.setLevel(lvl)

    filt = ContextFilter()

    # File handler (rotating)
    log_dir = log_dir or os.getenv("KEIRI_LOG_DIR", "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        fhandler = RotatingFileHandler(os.path.join(log_dir, "keiri_agent.log"), maxBytes=1_000_000, backupCount=5, encoding="utf-8")
        fhandler.setLevel(lvl)
        fhandler.setFormatter(JsonFormatter())
        fhandler.addFilter(filt)
        _logger.addHandler(fhandler)
    except Exception:
        # Fallback: console only
        pass

    if console:
        ch = logging.StreamHandler()
        ch.setLevel(lvl)
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        ch.addFilter(filt)
        # Default suppressed messages for console (file logging remains intact)
        default_suppressed = [
            "DAG描画の更新に失敗しました。",
        ]
        # Allow opt-in additional suppression via env var (pipe-delimited)
        extra = os.getenv("KEIRI_SUPPRESS_CONSOLE_MESSAGES", "")
        if extra:
            default_suppressed.extend([s for s in extra.split("|") if s])
        ch.addFilter(_ConsoleSuppressFilter(default_suppressed))
        _logger.addHandler(ch)


def set_context(*, plan_id: str | None = None, run_id: str | None = None, node_id: str | None = None, tag: str | None = None) -> None:
    cur = dict(_log_ctx.get({}))
    if plan_id is not None:
        cur["plan_id"] = plan_id
    if run_id is not None:
        cur["run_id"] = run_id
    if node_id is not None:
        cur["node_id"] = node_id
    if tag is not None:
        cur["tag"] = tag
    _log_ctx.set(cur)


def clear_context() -> None:
    _log_ctx.set({})


def info(message: str, *, user: bool = False) -> None:
    _logger.info(message)
    if user:
        st.info(message)


def warn(message: str, exc: Optional[BaseException] = None, *, user: bool = True) -> None:
    if exc is not None:
        _logger.warning(message, exc_info=exc)
    else:
        _logger.warning(message)
    if user:
        st.warning(message)


def error(message: str, exc: Optional[BaseException] = None, *, user: bool = True) -> None:
    if exc is not None:
        _logger.error(message, exc_info=exc)
    else:
        _logger.error(message)
    if user:
        st.error(message)


