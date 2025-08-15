from __future__ import annotations

from typing import Any, Dict, List, Tuple
import itertools

from core.blocks.base import BlockContext, ProcessingBlock


def _norm_keymap(keys: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for k in keys or []:
        if not isinstance(k, dict):
            continue
        out.append((str(k.get("left")), str(k.get("right")), str(k.get("type", "string")).lower()))
    return out


def _get_ci(obj: Dict[str, Any], key: str):
    if not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        if str(k).lower() == key.lower():
            return v
    return None


def _similarity(a: str, b: str) -> float:
    # simple token sort ratio (scaled) + containment bonus
    if a is None or b is None:
        return 0.0
    sa = sorted(str(a).lower().split())
    sb = sorted(str(b).lower().split())
    if not sa and not sb:
        return 1.0
    i = 0
    j = 0
    match = 0
    while i < len(sa) and j < len(sb):
        if sa[i] == sb[j]:
            match += 1
            i += 1
            j += 1
        elif sa[i] < sb[j]:
            i += 1
        else:
            j += 1
    base = (2 * match) / (len(sa) + len(sb))
    cont = 1.0 if " ".join(sa) in " ".join(sb) or " ".join(sb) in " ".join(sa) else 0.0
    return min(1.0, base + 0.1 * cont)


class RecordLinkageBlock(ProcessingBlock):
    id = "matching.record_linkage"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        left = inputs.get("left") or []
        right = inputs.get("right") or []
        strategy = str(inputs.get("strategy", "exact")).lower()
        keys = inputs.get("keys") or []
        fuzzy_cfg = inputs.get("fuzzy") or {}
        window = int(inputs.get("window", 0) or 0)

        keymap = _norm_keymap(keys if isinstance(keys, list) else [])

        matches: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []

        if not isinstance(left, list) or not isinstance(right, list):
            return {"matches": [], "candidates": [], "summary": {"left": 0, "right": 0}}

        threshold = float(fuzzy_cfg.get("threshold", 0.85)) if isinstance(fuzzy_cfg, dict) else 0.85

        # optional blocking/windowing not implemented for now beyond simple slice
        left_iter = left[: window or len(left)] if window else left
        right_iter = right[: window or len(right)] if window else right

        for li, ri in itertools.product(left_iter, right_iter):
            if not isinstance(li, dict) or not isinstance(ri, dict):
                continue
            if strategy == "exact":
                eq = True
                for lk, rk, _t in keymap:
                    lv = _get_ci(li, lk)
                    rv = _get_ci(ri, rk)
                    if lv != rv:
                        eq = False
                        break
                if eq:
                    matches.append({"left": li, "right": ri, "score": 1.0})
            elif strategy in ("fuzzy", "hybrid"):
                # Compute average similarity across string fields
                sims: List[float] = []
                for lk, rk, t in keymap:
                    lv = _get_ci(li, lk)
                    rv = _get_ci(ri, rk)
                    if t == "string":
                        sims.append(_similarity(str(lv), str(rv)))
                    else:
                        sims.append(1.0 if lv == rv else 0.0)
                score = sum(sims) / len(sims) if sims else 0.0
                if score >= threshold:
                    matches.append({"left": li, "right": ri, "score": round(score, 4)})
                elif strategy == "hybrid":
                    candidates.append({"left": li, "right": ri, "score": round(score, 4)})

        return {"matches": matches, "candidates": candidates, "summary": {"left": len(left), "right": len(right), "matches": len(matches)}}


