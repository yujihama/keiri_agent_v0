from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UIConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    layout: List[str] = Field(default_factory=list)


class Policy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    on_error: Optional[str] = Field(default="continue")  # halt|continue|retry
    retries: int = 0
    concurrency: Optional[Dict[str, int]] = None
    timeout_ms: Optional[int] = None


class Node(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    block: Optional[str] = None
    type: Optional[str] = None  # for future: loop/subflow
    max_workers: Optional[int] = None
    priority: Optional[int] = None
    inputs: Dict[str, Any] = Field(default_factory=dict, alias="in")
    outputs: Dict[str, str] = Field(default_factory=dict, alias="out")
    when: Optional[Dict[str, Any]] = None
    # loop/subflow extensions
    foreach: Optional[Dict[str, Any]] = None
    while_: Optional[Dict[str, Any]] = Field(default=None, alias="while")
    body: Optional[Dict[str, Any]] = None
    call: Optional[Dict[str, Any]] = None
    # per-node policy override (subset)
    policy: Optional[Policy] = None
    # HITL設定
    hitl: Optional[Dict[str, Any]] = None


class Plan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    apiVersion: Optional[str] = None
    id: str
    version: str
    vars: Dict[str, Any] = Field(default_factory=dict)
    policy: Optional[Policy] = None
    ui: Optional[UIConfig] = None
    graph: List[Node] = Field(default_factory=list)


