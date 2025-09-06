from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import base64
import re

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, ErrorCode, create_input_error, wrap_exception
from core.plan.text_extractor import extract_texts as _extract_texts


def _normalize_spaces(text: str) -> str:
    return " ".join(str(text).split())


def _split_sentences(text: str) -> List[str]:
    # Naive sentence splitter that keeps punctuation
    parts: List[str] = []
    buf: List[str] = []
    for ch in text:
        buf.append(ch)
        if ch in ".!?。！？":
            parts.append("".join(buf).strip())
            buf = []
    rest = "".join(buf).strip()
    if rest:
        parts.append(rest)
    # Merge very short sentences with next one to reduce fragmentation
    merged: List[str] = []
    for s in parts:
        if merged and len(s) < 12:
            merged[-1] = (merged[-1] + " " + s).strip()
        else:
            merged.append(s)
    return [p for p in merged if p]


def _split_paragraphs(text: str) -> List[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    return paras if paras else ([text.strip()] if text.strip() else [])


def _split_markdown_headings(text: str) -> List[str]:
    # Split on ATX headings while keeping content under each heading
    lines = text.splitlines()
    chunks: List[str] = []
    buf: List[str] = []
    for ln in lines:
        if ln.lstrip().startswith("#") and buf:
            chunks.append("\n".join(buf).strip())
            buf = [ln]
        else:
            buf.append(ln)
    if buf:
        val = "\n".join(buf).strip()
        if val:
            chunks.append(val)
    return chunks if chunks else ([text.strip()] if text.strip() else [])


class ChunkTextsBlock(ProcessingBlock):
    id = "nlp.chunk_texts"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        texts_in = inputs.get("texts")
        files_in = inputs.get("files")
        strategy = str(inputs.get("strategy") or "tokens").lower()
        try:
            max_tokens = int(inputs.get("max_tokens", 400))
        except Exception:
            max_tokens = 400
        try:
            overlap_tokens = int(inputs.get("overlap_tokens", 40))
        except Exception:
            overlap_tokens = 40
        normalize_ws = bool(inputs.get("normalize_whitespace", True))

        # Collect input texts
        texts: List[Tuple[str, str]] = []  # (source, text)
        if isinstance(texts_in, list):
            for i, t in enumerate(texts_in):
                if t is None:
                    continue
                s = str(t)
                texts.append((f"text:{i}", s))
        elif isinstance(files_in, list):
            for f in files_in:
                if not isinstance(f, dict):
                    continue
                name = str(f.get("name") or f.get("path") or "file")
                s = str(f.get("text_excerpt") or f.get("text") or "")
                if not s:
                    # Try to recover from bytes/base64
                    raw: Optional[bytes] = None
                    if isinstance(f.get("bytes"), (bytes, bytearray)):
                        raw = bytes(f.get("bytes"))  # type: ignore[arg-type]
                    elif isinstance(f.get("base64"), str):
                        try:
                            raw = base64.b64decode(str(f.get("base64")))
                        except Exception:
                            raw = None
                    if raw is not None:
                        try:
                            ext = ""
                            if "." in name:
                                ext = name[name.rfind(".") :].lower()
                            s_list = _extract_texts([(name, raw)])
                            s = s_list[0] if s_list else ""
                        except Exception:
                            s = ""
                if s:
                    texts.append((name, s))

        if not texts:
            raise create_input_error(
                field="texts|files",
                expected_type="texts: list[string] OR files: list[{name,text_excerpt}]",
                actual_value={"texts": texts_in, "files": files_in},
                code=ErrorCode.INPUT_REQUIRED_MISSING,
            )

        if strategy not in ("tokens", "sentences", "paragraphs", "markdown_headings"):
            raise create_input_error(
                field="strategy",
                expected_type="one of tokens|sentences|paragraphs|markdown_headings",
                actual_value=strategy,
            )

        try:
            chunks_out: List[Dict[str, Any]] = []
            total = 0
            for idx, (src, raw) in enumerate(texts):
                s = _normalize_spaces(raw) if normalize_ws else str(raw)
                if not s:
                    continue

                if strategy == "tokens":
                    try:
                        import tiktoken  # type: ignore
                    except Exception as e:
                        raise BlockException(
                            error=wrap_exception(
                                e,
                                ErrorCode.DEPENDENCY_NOT_FOUND,
                                inputs,
                            ).error
                        )
                    enc = tiktoken.get_encoding("cl100k_base")
                    toks = enc.encode(s)
                    if max_tokens <= 0:
                        max_tokens = 400
                    step = max(1, max_tokens - max(0, overlap_tokens))
                    pos = 0
                    c = 0
                    while pos < len(toks):
                        window = toks[pos : pos + max_tokens]
                        text_chunk = enc.decode(window)
                        start_char = c * 1  # approximate based on concatenation order
                        end_char = start_char + len(text_chunk)
                        chunks_out.append(
                            {
                                "id": f"{idx}-{c}",
                                "source": src,
                                "start": start_char,
                                "end": end_char,
                                "text": text_chunk,
                                "tokens": len(window),
                            }
                        )
                        c += 1
                        total += 1
                        pos += step
                else:
                    if strategy == "sentences":
                        units = _split_sentences(s)
                    elif strategy == "paragraphs":
                        units = _split_paragraphs(s)
                    else:
                        units = _split_markdown_headings(s)

                    # Pack units into size-constrained chunks (chars as proxy)
                    # Heuristic: tokens ~= chars/4
                    max_chars = max_tokens * 4 if max_tokens > 0 else 1600
                    buf: List[str] = []
                    cur_len = 0
                    c = 0
                    for u in units:
                        ul = len(u)
                        if buf and cur_len + 1 + ul > max_chars:
                            text_chunk = " ".join(buf).strip()
                            chunks_out.append(
                                {
                                    "id": f"{idx}-{c}",
                                    "source": src,
                                    "start": 0,
                                    "end": len(text_chunk),
                                    "text": text_chunk,
                                    "tokens": None,
                                }
                            )
                            total += 1
                            c += 1
                            buf = [u]
                            cur_len = ul
                        else:
                            if buf:
                                buf.append(u)
                                cur_len += 1 + ul
                            else:
                                buf = [u]
                                cur_len = ul
                    if buf:
                        text_chunk = " ".join(buf).strip()
                        chunks_out.append(
                            {
                                "id": f"{idx}-{c}",
                                "source": src,
                                "start": 0,
                                "end": len(text_chunk),
                                "text": text_chunk,
                                "tokens": None,
                            }
                        )
                        total += 1

            return {
                "chunks": chunks_out,
                "summary": {"texts": len(texts), "chunks": len(chunks_out), "strategy": strategy},
            }
        except BlockException:
            raise
        except Exception as e:
            raise wrap_exception(e, ErrorCode.BLOCK_EXECUTION_FAILED, inputs)


