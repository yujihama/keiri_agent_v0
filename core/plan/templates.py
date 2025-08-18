from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field


class TemplateSpec(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    imports: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    exports: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    vars_defaults: Optional[Dict[str, Any]] = None
    ui_suggestions: Optional[Dict[str, Any]] = None
    graph_snippet: List[Dict[str, Any]] = Field(default_factory=list)


def load_all_templates(base_dir: str | Path = "designs/templates") -> Dict[str, TemplateSpec]:
    """Load all template YAML files under designs/templates recursively.

    Returns dict of id -> TemplateSpec. Duplicate ids are resolved by last-wins order.
    """

    root = Path(base_dir)
    out: Dict[str, TemplateSpec] = {}
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.yaml")):
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            spec = TemplateSpec.model_validate(data)
            out[spec.id] = spec
        except Exception:
            # Skip invalid templates silently for now (UI can warn later)
            continue
    return out


def summarize_templates(templates: List[TemplateSpec]) -> List[Dict[str, Any]]:
    """Return a compact summary suitable for LLM hinting.

    Includes id/title/description/tags/imports/exports and a compacted graph snippet (ids only).
    """

    out: List[Dict[str, Any]] = []
    for t in templates:
        # Compact snippet: include node id and block/type for brevity
        compact_graph = []
        for n in (t.graph_snippet or []):
            compact_graph.append({
                "id": n.get("id"),
                **({"block": n.get("block")} if n.get("block") else {}),
                **({"type": n.get("type")} if n.get("type") else {}),
            })
        out.append({
            "id": t.id,
            "title": t.title,
            "description": t.description or "",
            "tags": t.tags or [],
            "imports": list((t.imports or {}).keys()),
            "exports": list((t.exports or {}).keys()),
            "graph_outline": compact_graph,
        })
    return out


