import base64
from typing import Any, Dict, List
import types
import sys
import pytest

from core.blocks.base import BlockContext
from core.blocks.processing.ai.process_llm import ProcessLLMBlock


# --- Minimal shim for langchain_core.messages.HumanMessage
class HumanMessage:
    def __init__(self, content):
        self.content = content

# Inject shim into sys.modules so import in target code works for isinstance checks if any
langchain_core = types.ModuleType("langchain_core")
messages_mod = types.ModuleType("messages")
messages_mod.HumanMessage = HumanMessage
langchain_core.messages = messages_mod
sys.modules.setdefault("langchain_core", langchain_core)
sys.modules.setdefault("langchain_core.messages", messages_mod)


# --- Mock fitz (PyMuPDF) to simulate PDF with one embedded image
class _MockPixmap:
    def __init__(self, *args, **kwargs):
        self.alpha = False
    def tobytes(self, fmt: str) -> bytes:
        # Return minimal fake png bytes header
        return b"\x89PNG\r\n\x1a\nFAKEPNGDATA"

class _MockDoc:
    def __init__(self, stream: bytes, filetype: str):
        self._len = 1
        self._images = [
            # Simulate get_images returning a list of tuples, first element is xref id
            (1,)
        ]
    def __len__(self):
        return self._len
    def __getitem__(self, idx: int):
        return self
    def get_images(self, full: bool = True):
        return self._images
    def extract_image(self, xref: int):
        # Return an image dict with raw bytes and ext
        return {"image": b"rawjpegbytes", "ext": "jpeg"}

class _MockFitzModule:
    Rect = object
    Pixmap = _MockPixmap
    csRGB = object()
    def open(self, stream: bytes, filetype: str):
        return _MockDoc(stream, filetype)

# Inject mock fitz
sys.modules.setdefault("fitz", _MockFitzModule())


class _FakeStructuredLLM:
    def __init__(self, output_model: Any, capture: Dict[str, Any]):
        self._output_model = output_model
        self._capture = capture
    def invoke(self, messages: List[Any]):
        self._capture["messages"] = messages
        return self._output_model(foo="ok", nums=[1, 2])

class _FakeLLM:
    def __init__(self, capture: Dict[str, Any]):
        self._capture = capture
    def with_structured_output(self, output_model: Any) -> _FakeStructuredLLM:
        return _FakeStructuredLLM(output_model, self._capture)


@pytest.fixture()
def fake_build_chat_llm(monkeypatch):
    capture: Dict[str, Any] = {}
    def _fake_builder(**kwargs):
        return _FakeLLM(capture), "fake-model"
    monkeypatch.setattr(
        "core.blocks.processing.ai.process_llm.build_chat_llm",
        _fake_builder,
        raising=True,
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return capture


def _minimal_pdf_bytes() -> bytes:
    # Minimal bytes to be treated as a PDF (we do not actually parse it; we mock fitz)
    return b"%PDF-FAKE-MINIMAL"


def _common_inputs(pdf_bytes: bytes) -> Dict[str, Any]:
    return {
        "evidence_data": {
            "files": [
                {
                    "name": "test.pdf",
                    "ext": ".pdf",
                    "size": len(pdf_bytes),
                    "mime_type": "application/pdf",
                    "text_excerpt": "sample",
                    "bytes": pdf_bytes,
                }
            ]
        },
        "instruction": "Extract",
        "output_schema": {
            "foo": "string",
            "nums": {"type": "array", "items": "integer"},
        },
        "allow_images": True,
        "max_images": 4,
    }


def _assert_image_attached(capture: Dict[str, Any], summary: Dict[str, Any]) -> None:
    assert summary.get("images", 0) >= 1
    messages = capture.get("messages")
    assert isinstance(messages, list) and len(messages) >= 2
    # Find first human message (our shim)
    human_msgs = [m for m in messages if isinstance(m, HumanMessage)]
    assert human_msgs, "HumanMessage not found in messages"
    human = human_msgs[0]
    parts = human.content
    assert isinstance(parts, list)
    image_urls = [p.get("image_url", {}).get("url") for p in parts if isinstance(p, dict) and p.get("type") == "image_url"]
    assert image_urls and all(isinstance(u, str) and u.startswith("data:image/") for u in image_urls)


def test_llm_process_extracts_images_from_pdf_bytes(fake_build_chat_llm: Dict[str, Any]):
    pdf = _minimal_pdf_bytes()
    block = ProcessLLMBlock()
    ctx = BlockContext(run_id="test-run", workspace=None)

    inputs = _common_inputs(pdf)
    out = block.run(ctx, inputs)

    assert "results" in out and "summary" in out
    _assert_image_attached(fake_build_chat_llm, out["summary"])  # summary["images"] >= 1


def test_llm_process_extracts_images_from_pdf_base64(fake_build_chat_llm: Dict[str, Any]):
    pdf = _minimal_pdf_bytes()
    block = ProcessLLMBlock()
    ctx = BlockContext(run_id="test-run", workspace=None)

    b64 = base64.b64encode(pdf).decode("ascii")
    inputs = _common_inputs(pdf)
    inputs["evidence_data"]["files"][0].pop("bytes")
    inputs["evidence_data"]["files"][0]["base64"] = b64

    out = block.run(ctx, inputs)

    assert "results" in out and "summary" in out
    _assert_image_attached(fake_build_chat_llm, out["summary"])  # summary["images"] >= 1