from __future__ import annotations

from typing import Any, Dict, List, Optional
import math

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, ErrorCode, create_input_error, wrap_exception
from core.plan.llm_factory import build_text_embedder


def _l2_normalize(vec: List[float]) -> List[float]:
    s = math.sqrt(sum((x * x) for x in vec))
    if s <= 0:
        return vec
    return [x / s for x in vec]


class EmbedTextsBlock(ProcessingBlock):
    id = "nlp.embed_texts"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        texts_in = inputs.get("texts")
        chunks_in = inputs.get("chunks")
        normalize = bool(inputs.get("normalize", True))
        # provider_model は llm_factory 側の環境設定を優先し、ここでは未使用（互換のため受理）

        texts: Optional[List[str]] = None
        mode: str = "texts"
        if isinstance(texts_in, list):
            texts = [str(t) for t in texts_in if t is not None]
            mode = "texts"
        elif isinstance(chunks_in, list):
            texts = []
            for ch in chunks_in:
                if isinstance(ch, dict) and ch.get("text"):
                    texts.append(str(ch["text"]))
            mode = "chunks"

        if not texts:
            raise create_input_error(
                field="texts|chunks",
                expected_type="texts: list[string] OR chunks: list[{text}]",
                actual_value={"texts": texts_in, "chunks": chunks_in},
                code=ErrorCode.INPUT_REQUIRED_MISSING,
            )

        try:
            embed_fn, label = build_text_embedder()
        except Exception as e:
            raise BlockException(
                error=wrap_exception(e, ErrorCode.CONFIG_MISSING, inputs).error
            )

        try:
            vecs = embed_fn(texts)
            if not isinstance(vecs, list) or (vecs and not isinstance(vecs[0], list)):
                raise ValueError("Embedding function returned unexpected shape")
            if normalize:
                vecs = [_l2_normalize([float(x) for x in v]) for v in vecs]

            if mode == "texts":
                return {"vectors": vecs, "summary": {"count": len(vecs), "model": label}}
            else:
                # Attach to chunks
                out_items: List[Dict[str, Any]] = []
                i = 0
                for ch in chunks_in:
                    if isinstance(ch, dict) and ch.get("text"):
                        item = dict(ch)
                        item["embedding"] = vecs[i]
                        out_items.append(item)
                        i += 1
                    else:
                        out_items.append(ch)
                return {"items": out_items, "summary": {"count": len(vecs), "model": label}}
        except BlockException:
            raise
        except Exception as e:
            raise wrap_exception(e, ErrorCode.BLOCK_EXECUTION_FAILED, inputs)


