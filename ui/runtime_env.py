from __future__ import annotations

import os
from contextlib import contextmanager


@contextmanager
def disable_headless_for_ui():
    """Temporarily disable headless mode during UI rendering/interaction."""
    prev = os.environ.get("KEIRI_AGENT_HEADLESS", None)
    try:
        os.environ["KEIRI_AGENT_HEADLESS"] = "0"
        yield
    finally:
        try:
            if prev is None:
                os.environ.pop("KEIRI_AGENT_HEADLESS", None)
            else:
                os.environ["KEIRI_AGENT_HEADLESS"] = prev
        except Exception:
            pass


