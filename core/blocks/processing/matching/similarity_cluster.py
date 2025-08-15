from __future__ import annotations

from typing import Any, Dict, List, Tuple

from datasketch import MinHash, MinHashLSH

from core.blocks.base import BlockContext, ProcessingBlock


def _tokenize(text: str) -> List[str]:
    return [t for t in str(text).lower().split() if t]


class SimilarityClusterBlock(ProcessingBlock):
    id = "matching.similarity_cluster"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        feature_spec = inputs.get("feature_spec") or {}
        method = str(inputs.get("method", "minhash")).lower()
        threshold = float(inputs.get("threshold", 0.8))
        top_k = int(inputs.get("top_k", 5))

        if not isinstance(items, list):
            items = []

        # Build textual representation per item according to feature_spec (simple concat)
        texts: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                texts.append(str(it))
                continue
            parts: List[str] = []
            for f in (feature_spec.get("text_fields") or []):
                v = None
                for k, val in it.items():
                    if str(k).lower() == str(f).lower():
                        v = val
                        break
                if v is not None:
                    parts.append(str(v))
            texts.append(" ".join(parts) if parts else str(it))

        clusters: List[List[int]] = []
        candidates: List[Dict[str, Any]] = []

        if method in ("minhash", "lsh"):
            lsh = MinHashLSH(threshold=threshold, num_perm=128)
            signatures: List[MinHash] = []
            for idx, t in enumerate(texts):
                m = MinHash(num_perm=128)
                for token in set(_tokenize(t)):
                    m.update(token.encode("utf-8"))
                signatures.append(m)
                lsh.insert(f"i{idx}", m)
            # retrieve candidate neighbors
            visited = set()
            for i, m in enumerate(signatures):
                if i in visited:
                    continue
                bucket = lsh.query(m)
                grp = sorted([int(x[1:]) for x in bucket])
                for j in grp:
                    visited.add(j)
                if grp:
                    clusters.append(grp)
            # build candidates top_k pairs inside clusters
            for grp in clusters:
                base = grp[0]
                sims: List[Tuple[int, float]] = []
                for j in grp[1:]:
                    s = signatures[base].jaccard(signatures[j])
                    sims.append((j, s))
                sims.sort(key=lambda x: x[1], reverse=True)
                for j, s in sims[:top_k]:
                    candidates.append({"a": base, "b": j, "score": round(float(s), 4)})
        else:
            # cosine/jaccard simple fallbacks via token set overlap
            token_sets: List[set[str]] = [set(_tokenize(t)) for t in texts]
            used = set()
            for i, si in enumerate(token_sets):
                if i in used:
                    continue
                grp = [i]
                for j in range(i + 1, len(token_sets)):
                    sj = token_sets[j]
                    if not si or not sj:
                        continue
                    inter = len(si & sj)
                    union = len(si | sj)
                    sim = inter / union
                    if sim >= threshold:
                        grp.append(j)
                for j in grp:
                    used.add(j)
                if grp:
                    clusters.append(sorted(grp))

        return {"clusters": clusters, "candidates": candidates, "summary": {"items": len(items), "clusters": len(clusters)}}


