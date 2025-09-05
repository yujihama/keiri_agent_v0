import base64
import os
import sys
import types
from typing import Any, Dict, List


# --- Shim for langchain_core.messages
class SystemMessage:
	def __init__(self, content):
		self.content = content

class HumanMessage:
	def __init__(self, content):
		self.content = content

langchain_core = types.ModuleType("langchain_core")
messages_mod = types.ModuleType("messages")
messages_mod.SystemMessage = SystemMessage
messages_mod.HumanMessage = HumanMessage
langchain_core.messages = messages_mod
sys.modules.setdefault("langchain_core", langchain_core)
sys.modules.setdefault("langchain_core.messages", messages_mod)


# --- Minimal shim for pydantic used by core
pydantic_mod = types.ModuleType("pydantic")

class _BaseModel:
	def __init__(self, **kwargs):
		for k, v in kwargs.items():
			setattr(self, k, v)
	def model_dump(self):
		return {k: v for k, v in self.__dict__.items()}

class _ConfigDict(dict):
	pass

def _Field(default=None, **kwargs):
	return default

def _create_model(name: str, __base__=_BaseModel, **fields):
	base = __base__ or _BaseModel
	return type(name, (base,), {})

pydantic_mod.BaseModel = _BaseModel
pydantic_mod.Field = _Field
pydantic_mod.create_model = _create_model
pydantic_mod.ConfigDict = _ConfigDict
sys.modules.setdefault("pydantic", pydantic_mod)


# Import after shimming messages and pydantic
from core.blocks.base import BlockContext
import core.blocks.processing.ai.process_llm as process_llm


# --- Mock fitz (PyMuPDF)
class _MockPixmap:
	def __init__(self, *args, **kwargs):
		self.alpha = False
	def tobytes(self, fmt: str) -> bytes:
		return b"\x89PNG\r\n\x1a\nFAKEPNGDATA"

class _MockDoc:
	def __init__(self, stream: bytes, filetype: str):
		self._len = 1
		self._images = [(1,)]
	def __enter__(self):
		return self
	def __exit__(self, exc_type, exc, tb):
		return False
	def __len__(self):
		return self._len
	def __getitem__(self, idx: int):
		return self
	def get_images(self, full: bool = True):
		return self._images
	def extract_image(self, xref: int):
		return {"image": b"rawjpegbytes", "ext": "jpeg"}

class _MockFitzModule:
	Rect = object
	Pixmap = _MockPixmap
	csRGB = object()
	def open(self, stream: bytes, filetype: str):
		return _MockDoc(stream, filetype)

sys.modules.setdefault("fitz", _MockFitzModule())


# --- Fake LLM
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

def _fake_build_chat_llm(**kwargs):
	return _FakeLLM(_CAPTURE), "fake-model"


# Ensure API key check passes
os.environ.setdefault("OPENAI_API_KEY", "test-key")

# Patch builder
process_llm.build_chat_llm = _fake_build_chat_llm

# Globals
_CAPTURE: Dict[str, Any] = {}


def _minimal_pdf_bytes() -> bytes:
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


def _assert_image_attached(summary: Dict[str, Any]) -> None:
	if summary.get("images", 0) < 1:
		raise AssertionError("Expected at least 1 image attached to LLM input")


def main() -> int:
	block = process_llm.ProcessLLMBlock()
	ctx = BlockContext(run_id="smoke-run", workspace=None)

	# bytes path
	pdf = _minimal_pdf_bytes()
	inputs = _common_inputs(pdf)
	out = block.run(ctx, inputs)
	if not ("results" in out and "summary" in out):
		print("ERROR: Missing keys in output")
		return 1
	_assert_image_attached(out["summary"])

	# base64 path
	b64 = base64.b64encode(pdf).decode("ascii")
	inputs_b64 = _common_inputs(pdf)
	inputs_b64["evidence_data"]["files"][0].pop("bytes")
	inputs_b64["evidence_data"]["files"][0]["base64"] = b64
	out2 = block.run(ctx, inputs_b64)
	if not ("results" in out2 and "summary" in out2):
		print("ERROR: Missing keys in output (base64 path)")
		return 1
	_assert_image_attached(out2["summary"])

	print("OK: ai.process_llm extracts images from PDF (bytes and base64)")
	return 0


if __name__ == "__main__":
	sys.exit(main())