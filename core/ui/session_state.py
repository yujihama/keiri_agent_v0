"""Unified Session State management for UI blocks

This module provides a centralized way to manage Streamlit session state
following the naming conventions defined in the design document.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st


class SessionStateManager:
    """Manages session state with consistent naming conventions
    
    Key naming pattern:
    - Node state: f"plan:{plan_id}::node:{node_id}::v{block_version}"
    - Global state: f"plan:{plan_id}::global::{key}"
    """
    
    def __init__(self, plan_id: str, run_id: str):
        self.plan_id = plan_id
        self.run_id = run_id
    
    def _make_node_key(self, node_id: str, block_version: str, suffix: str = "") -> str:
        """Create a key for node-specific state"""
        key = f"plan:{self.plan_id}::node:{node_id}::v{block_version}"
        if suffix:
            key += f"::{suffix}"
        return key
    
    def _make_global_key(self, key: str) -> str:
        """Create a key for global plan state"""
        return f"plan:{self.plan_id}::global::{key}"
    
    def get_node_state(
        self,
        node_id: str,
        block_version: str,
        key: str,
        default: Any = None
    ) -> Any:
        """Get state value for a specific node"""
        state_key = self._make_node_key(node_id, block_version, key)
        return st.session_state.get(state_key, default)
    
    def set_node_state(
        self,
        node_id: str,
        block_version: str,
        key: str,
        value: Any
    ) -> None:
        """Set state value for a specific node"""
        state_key = self._make_node_key(node_id, block_version, key)
        st.session_state[state_key] = value
    
    def get_global_state(self, key: str, default: Any = None) -> Any:
        """Get global state value"""
        state_key = self._make_global_key(key)
        return st.session_state.get(state_key, default)
    
    def set_global_state(self, key: str, value: Any) -> None:
        """Set global state value"""
        state_key = self._make_global_key(key)
        st.session_state[state_key] = value
    
    def clear_node_state(self, node_id: str, block_version: str) -> None:
        """Clear all state for a specific node"""
        prefix = self._make_node_key(node_id, block_version)
        keys_to_remove = [k for k in st.session_state.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            del st.session_state[key]
    
    def clear_plan_state(self) -> None:
        """Clear all state for the current plan"""
        prefix = f"plan:{self.plan_id}::"
        keys_to_remove = [k for k in st.session_state.keys() if k.startswith(prefix)]
        for key in keys_to_remove:
            del st.session_state[key]
    
    def get_all_node_state(self, node_id: str, block_version: str) -> Dict[str, Any]:
        """Get all state values for a node"""
        prefix = self._make_node_key(node_id, block_version)
        result = {}
        for key, value in st.session_state.items():
            if key.startswith(prefix + "::"):
                # Extract the suffix part
                suffix = key[len(prefix) + 2:]
                result[suffix] = value
        return result


class NodeStateContext:
    """Context manager for node state operations
    
    Usage:
        with NodeStateContext(plan_id, run_id, node_id, block_version) as state:
            value = state.get("key", default)
            state.set("key", new_value)
    """
    
    def __init__(self, plan_id: str, run_id: str, node_id: str, block_version: str):
        self.manager = SessionStateManager(plan_id, run_id)
        self.node_id = node_id
        self.block_version = block_version
        self._snapshot = None
    
    def __enter__(self) -> "NodeStateContext":
        # Take a snapshot of current state
        self._snapshot = self.manager.get_all_node_state(self.node_id, self.block_version)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Could implement rollback on error if needed
        pass
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get state value"""
        return self.manager.get_node_state(self.node_id, self.block_version, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set state value"""
        self.manager.set_node_state(self.node_id, self.block_version, key, value)
    
    def update(self, **kwargs) -> None:
        """Update multiple state values"""
        for key, value in kwargs.items():
            self.set(key, value)
    
    def clear(self) -> None:
        """Clear all state for this node"""
        self.manager.clear_node_state(self.node_id, self.block_version)


# Utility functions for common patterns
def get_or_create_state(
    key: str,
    creator_func: callable,
    *args,
    **kwargs
) -> Any:
    """Get state value or create it if not exists
    
    Args:
        key: Session state key
        creator_func: Function to create the value
        *args, **kwargs: Arguments for creator_func
    """
    if key not in st.session_state:
        st.session_state[key] = creator_func(*args, **kwargs)
    return st.session_state[key]


def persist_widget_value(widget_key: str, value: Any) -> Any:
    """Persist widget value across reruns
    
    This ensures widget values are maintained even when the page reruns.
    """
    if widget_key not in st.session_state:
        st.session_state[widget_key] = value
    return st.session_state[widget_key]
