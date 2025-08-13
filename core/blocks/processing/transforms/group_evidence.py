from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class GroupEvidenceBlock(ProcessingBlock):
    id = "transforms.group_evidence"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Group parsed evidence into scoped groups for foreach.

        Inputs
        ------
        - evidence: object from file.parse_zip_2tier
          {
            raw_size: int,
            total_files: int,
            files: [ { path, name, size, ext, sha1, text_excerpt } ],
            by_dir: { top_dir_or_empty: [relative_paths] }
          }
        - level: str  (supports: "top_dir" | "second_dir" | "auto")
        - instruction: str (optional)  additional payload to carry into each group

        Outputs
        -------
        - groups: list of { key, evidence, instruction? }
          where evidence is scoped to the group (files filtered by key)
        """

        evidence = inputs.get("evidence") or {}
        level = str(inputs.get("level") or "top_dir").strip().lower()
        instruction = inputs.get("instruction")

        if not isinstance(evidence, dict):
            return {"groups": []}

        files = evidence.get("files") or []
        by_dir = evidence.get("by_dir") or {}

        groups: List[Dict[str, Any]] = []

        if level in ("top_dir", "by_dir"):
            # iterate keys from by_dir; include empty "" for root files if present
            keys = list(by_dir.keys()) if isinstance(by_dir, dict) else []
            # Fallback: if by_dir missing, infer top_dir from file paths
            if not keys and isinstance(files, list):
                try:
                    inferred: Dict[str, List[str]] = {}
                    for f in files:
                        p = f.get("path") or f.get("name") or ""
                        if "/" in p:
                            top = p.split("/", 1)[0]
                            rel = p[len(top) + 1 :]
                        else:
                            top = ""
                            rel = p
                        inferred.setdefault(top, []).append(rel)
                    keys = list(inferred.keys())
                    by_dir = inferred
                except Exception:
                    keys = []

            for key in keys:
                # Filter files whose top-level directory equals key (or root "")
                scoped_files: List[Dict[str, Any]] = []
                if isinstance(files, list):
                    for f in files:
                        p = f.get("path") or f.get("name") or ""
                        if "/" in p:
                            top = p.split("/", 1)[0]
                        else:
                            top = ""
                        if top == key:
                            scoped_files.append(dict(f))

                scoped_by_dir = {key: list(by_dir.get(key) or [])} if isinstance(by_dir, dict) else {key: []}
                scoped_evidence = {
                    "raw_size": evidence.get("raw_size"),
                    "total_files": len(scoped_files),
                    "files": scoped_files,
                    "by_dir": scoped_by_dir,
                }
                group_obj: Dict[str, Any] = {"key": key, "evidence": scoped_evidence}
                if instruction is not None:
                    group_obj["instruction"] = instruction
                groups.append(group_obj)

        elif level in ("second_dir", "tier2", "sub_dir") or level == "auto":
            # Determine whether we should split by second-level directory.
            # auto: if there's exactly one top_dir and relative paths include '/', prefer second_dir grouping.
            use_second = level in ("second_dir", "tier2", "sub_dir")
            if level == "auto":
                try:
                    if isinstance(by_dir, dict) and len(by_dir.keys()) == 1:
                        rels = next(iter(by_dir.values())) or []
                        use_second = any(isinstance(r, str) and "/" in r for r in rels)
                    else:
                        use_second = False
                except Exception:
                    use_second = False

            if not use_second:
                # fallback to top_dir strategy
                keys = list(by_dir.keys()) if isinstance(by_dir, dict) else []
                for key in keys:
                    scoped_files = []
                    if isinstance(files, list):
                        for f in files:
                            p = f.get("path") or f.get("name") or ""
                            top = p.split("/", 1)[0] if "/" in p else ""
                            if top == key:
                                scoped_files.append(dict(f))
                    scoped_by_dir = {key: list(by_dir.get(key) or [])} if isinstance(by_dir, dict) else {key: []}
                    scoped_evidence = {
                        "raw_size": evidence.get("raw_size"),
                        "total_files": len(scoped_files),
                        "files": scoped_files,
                        "by_dir": scoped_by_dir,
                    }
                    group_obj = {"key": key, "evidence": scoped_evidence}
                    if instruction is not None:
                        group_obj["instruction"] = instruction
                    groups.append(group_obj)
            else:
                # Build mapping by second-level directory
                second_to_files: Dict[str, List[Dict[str, Any]]] = {}
                if isinstance(files, list):
                    for f in files:
                        p = f.get("path") or f.get("name") or ""
                        if "/" in p:
                            top, rest = p.split("/", 1)
                            second = rest.split("/", 1)[0] if "/" in rest else rest
                        else:
                            top = ""  # unused
                            second = ""
                        second_to_files.setdefault(second, []).append(dict(f))

                for key, scoped_files in second_to_files.items():
                    # Construct a minimal by_dir-like structure for the group
                    # Use second-level name as the key; list relative names under that second
                    try:
                        rels: List[str] = []
                        for f in scoped_files:
                            p = f.get("path") or f.get("name") or ""
                            if "/" in p:
                                # remove top/second prefix if possible
                                parts = p.split("/")
                                rel = "/".join(parts[2:]) if len(parts) >= 3 else parts[-1]
                            else:
                                rel = p
                            rels.append(rel)
                    except Exception:
                        rels = [f.get("name") for f in scoped_files if isinstance(f, dict)]

                    scoped_by_dir = {key: rels}
                    scoped_evidence = {
                        "raw_size": evidence.get("raw_size"),
                        "total_files": len(scoped_files),
                        "files": scoped_files,
                        "by_dir": scoped_by_dir,
                    }
                    group_obj: Dict[str, Any] = {"key": key, "evidence": scoped_evidence}
                    if instruction is not None:
                        group_obj["instruction"] = instruction
                    groups.append(group_obj)

        else:
            # Unknown level -> single group passthrough
            passthrough = {"key": None, "evidence": evidence}
            if instruction is not None:
                passthrough["instruction"] = instruction
            groups = [passthrough]

        return {"groups": groups}


