from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class BlockContext(BaseModel):
    """Execution context shared across blocks.

    Attributes
    -----------
    run_id: Unique identifier for the current run (traceable across subflows).
    workspace: Optional workspace root path for the current execution.
    vars: Free-form variables available to blocks (read/write allowed).
    """

    run_id: str
    workspace: Optional[str] = None
    vars: Dict[str, Any] = Field(default_factory=dict)


class ProcessingBlock(ABC):
    """Abstract base class for processing blocks (non-UI).

    Implementations should be stateless and side-effect free by default. Any
    required execution state should be provided via inputs and the context.
    """

    id: str = ""
    version: str = ""

    def validate(self) -> None:
        """Optionally validate static preconditions for the block.

        Default implementation does nothing.
        """

    def dry_run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Perform a non-destructive check and return a shape-compatible output.

        Implementations should avoid external calls and large allocations.
        Default implementation returns an empty dict.
        """

        return {}

    @abstractmethod
    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the block with given inputs and return outputs.

        Implementations must be deterministic given the same inputs and
        context, or explicitly document non-determinism.
        """


class UIBlock(ABC):
    """Abstract base class for UI blocks rendered in Streamlit.

    UI blocks are responsible for rendering controls and returning user
    selections/inputs as a dict.
    """

    id: str = ""
    version: str = ""

    @abstractmethod
    def render(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Render UI and return outputs collected from user interaction."""


