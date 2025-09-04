from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import math

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import create_input_error, ErrorCode, wrap_exception


def _dot(a: List[float], b: List[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def _l2(a: List[float]) -> float:
    return math.sqrt(sum(x * x for x in a))


def _cosine(a: List[float], b: List[float]) -> float:
    na = _l2(a)
    nb = _l2(b)
    if na <= 0 or nb <= 0:
        return 0.0
    return _dot(a, b) / (na * nb)


class SemanticTopKBlock(ProcessingBlock):
    id = "matching.semantic_topk"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        query_text = inputs.get("query_text")
        qvec_in = inputs.get("query_embedding")
        items = inputs.get("items")
        metric = str(inputs.get("metric") or "cosine").lower()
        try:
            top_k = int(inputs.get("top_k", 5))
        except Exception:
            top_k = 5
        require_embeddings = bool(inputs.get("require_embeddings", True))

        if not isinstance(items, list) or not items:
            raise create_input_error(
                field="items",
                expected_type="non-empty list[{ id?, text?, embedding? }]",
                actual_value=items,
                code=ErrorCode.INPUT_REQUIRED_MISSING,
            )

        # Determine query vector
        qvec: Optional[List[float]] = None
        if isinstance(qvec_in, list) and qvec_in and isinstance(qvec_in[0], (int, float)):
            qvec = [float(x) for x in qvec_in]
        else:
            if require_embeddings:
                raise create_input_error(
                    field="query_embedding",
                    expected_type="list[number] (auto-embed is disabled)",
                    actual_value=qvec_in,
                    code=ErrorCode.INPUT_REQUIRED_MISSING,
                )
            else:
                # Fallback: naive lexical similarity by token overlap ratio
                qt = str(query_text or "")
                qtok = set(t.lower() for t in qt.split() if t)
                scored: List[Tuple[int, float]] = []
                for idx, it in enumerate(items):
                    text = str((it or {}).get("text") or it)
                    stok = set(t.lower() for t in text.split() if t)
                    inter = len(qtok & stok)
                    union = len(qtok | stok) or 1
                    scored.append((idx, inter / union))
                scored.sort(key=lambda x: x[1], reverse=True)
                top = scored[: max(1, top_k)]
                results = [
                    {"item": items[i], "score": round(float(s), 6), "rank": r + 1}
                    for r, (i, s) in enumerate(top)
                ]
                return {"results": results, "summary": {"metric": "lexical", "k": len(results)}}

        # Vector similarity path
        scored_vec: List[Tuple[int, float]] = []
        for idx, it in enumerate(items):
            emb = (it or {}).get("embedding") if isinstance(it, dict) else None
            if not isinstance(emb, list) or not emb:
                if require_embeddings:
                    continue
                else:
                    # score = 0 for missing embedding
                    scored_vec.append((idx, 0.0))
                    continue
            v = [float(x) for x in emb]
            if metric == "cosine":
                s = _cosine(qvec, v)  # type: ignore[arg-type]
            elif metric == "dot":
                s = _dot(qvec, v)  # type: ignore[arg-type]
            else:
                # euclidean distance -> convert to similarity (smaller is better)
                d = math.sqrt(sum((a - b) * (a - b) for a, b in zip(qvec or [], v)))
                s = -d
            scored_vec.append((idx, float(s)))

        scored_vec.sort(key=lambda x: x[1], reverse=True)
        top = scored_vec[: max(1, top_k)]
        results = [
            {"item": items[i], "score": round(float(s), 6), "rank": r + 1}
            for r, (i, s) in enumerate(top)
        ]
        return {"results": results, "summary": {"metric": metric, "k": len(results)}}


