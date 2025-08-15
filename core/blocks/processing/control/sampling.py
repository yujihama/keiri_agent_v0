from __future__ import annotations

from typing import Any, Dict, List, Tuple
import random

from core.blocks.base import BlockContext, ProcessingBlock


class SamplingBlock(ProcessingBlock):
    id = "control.sampling"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        population = inputs.get("population") or []
        method = str(inputs.get("method", "random")).lower()
        size_in = inputs.get("size", 0)
        attribute_rules = inputs.get("attribute_rules") or []
        risk_weights = inputs.get("risk_weights") or {}
        seed = inputs.get("seed")
        if isinstance(seed, int):
            random.seed(seed)

        pop: List[Any] = list(population) if isinstance(population, list) else []
        n = int(size_in or 0)
        n = max(0, min(n, len(pop)))

        def _match_rule(item: Any, rule: Dict[str, Any]) -> bool:
            if not isinstance(item, dict) or not isinstance(rule, dict):
                return False
            field = str(rule.get("field"))
            op = str(rule.get("operator", "eq")).lower()
            val = rule.get("value")
            left = None
            for k, v in item.items():
                if str(k).lower() == field.lower():
                    left = v
                    break
            try:
                if op == "eq":
                    return left == val
                if op == "ne":
                    return left != val
                if op == "gt":
                    return float(left) > float(val)  # type: ignore[arg-type]
                if op == "gte":
                    return float(left) >= float(val)  # type: ignore[arg-type]
                if op == "lt":
                    return float(left) < float(val)  # type: ignore[arg-type]
                if op == "lte":
                    return float(left) <= float(val)  # type: ignore[arg-type]
                if op == "in":
                    return left in val  # type: ignore[operator]
                if op == "contains":
                    return str(val) in str(left)
            except Exception:
                return False
            return False

        candidates: List[Any] = pop
        excluded: List[Any] = []

        if method == "attribute" and isinstance(attribute_rules, list) and attribute_rules:
            filt: List[Any] = []
            for it in pop:
                ok = all(_match_rule(it, r) for r in attribute_rules if isinstance(r, dict))
                (filt if ok else excluded).append(it)
            candidates = filt
        elif method == "risk_weighted" and isinstance(risk_weights, dict) and risk_weights:
            # risk weight per item via key lookup; default weight 1.0
            weighted: List[Tuple[Any, float]] = []
            for it in pop:
                key = None
                if isinstance(it, dict):
                    key = it.get("id") or it.get("_id") or it.get("key")
                w = risk_weights.get(key, 1.0)
                try:
                    w = float(w)  # type: ignore[assignment]
                except Exception:
                    w = 1.0
                weighted.append((it, w))
            # sample with probability proportional to weight
            total = sum(max(w, 0.0) for _, w in weighted)
            if total <= 0:
                candidates = pop
            else:
                picks: List[Any] = []
                for _ in range(n):
                    r = random.random() * total
                    acc = 0.0
                    chosen = weighted[0][0] if weighted else None
                    for it, w in weighted:
                        acc += max(w, 0.0)
                        if r <= acc:
                            chosen = it
                            break
                    if chosen is not None:
                        picks.append(chosen)
                # allow duplicates if weights concentrate; de-dup while preserving order
                seen = set()
                dedup: List[Any] = []
                for it in picks:
                    if id(it) in seen:
                        continue
                    seen.add(id(it))
                    dedup.append(it)
                candidates = dedup
        elif method == "systematic":
            if n <= 0 or not pop:
                candidates = []
            else:
                step = max(len(pop) // n, 1)
                start = random.randrange(0, step)
                candidates = [pop[i] for i in range(start, len(pop), step)][:n]
        else:  # random
            candidates = random.sample(pop, n) if n > 0 else []

        samples = candidates[:n]
        excluded = [x for x in pop if x not in samples]
        return {
            "samples": samples,
            "excluded": excluded,
            "summary": {"population": len(pop), "selected": len(samples), "method": method},
        }


