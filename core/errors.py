"""Structured error handling for keiri_agent

This module defines the BlockError class and error code system as specified
in the design document.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class BlockError(BaseModel):
    """Structured error data model
    
    Provides detailed error information with hints for resolution.
    """
    
    code: str = Field(description="Error code following the defined system")
    message: str = Field(description="User-friendly error message")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional error details")
    input_snapshot: Dict[str, Any] = Field(default_factory=dict, description="Input state at error time")
    hint: Optional[str] = Field(default=None, description="Hint for resolving the error")
    recoverable: bool = Field(default=False, description="Whether the error is recoverable")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the error occurred")
    
    def __str__(self) -> str:
        """Return a formatted error message"""
        msg = f"[{self.code}] {self.message}"
        if self.hint:
            msg += f"\nHint: {self.hint}"
        return msg


class BlockException(Exception):
    """Exception wrapper for BlockError
    
    This allows BlockError to be raised as an exception while maintaining
    its structured data.
    """
    
    def __init__(self, error: BlockError):
        self.error = error
        super().__init__(str(error))
    
    @classmethod
    def from_error(cls, error: BlockError) -> "BlockException":
        """Create BlockException from BlockError"""
        return cls(error)


# Error code constants
class ErrorCode:
    """Error code system as defined in design document"""
    
    # Input related errors
    INPUT_VALIDATION_FAILED = "INPUT_VALIDATION_FAILED"
    INPUT_TYPE_MISMATCH = "INPUT_TYPE_MISMATCH"
    INPUT_REQUIRED_MISSING = "INPUT_REQUIRED_MISSING"
    
    # Output related errors
    OUTPUT_SCHEMA_MISMATCH = "OUTPUT_SCHEMA_MISMATCH"
    OUTPUT_GENERATION_FAILED = "OUTPUT_GENERATION_FAILED"
    
    # Dependency related errors
    DEPENDENCY_NOT_FOUND = "DEPENDENCY_NOT_FOUND"
    DEPENDENCY_FAILED = "DEPENDENCY_FAILED"
    
    # External errors
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    EXTERNAL_TIMEOUT = "EXTERNAL_TIMEOUT"
    EXTERNAL_RATE_LIMIT = "EXTERNAL_RATE_LIMIT"
    
    # Block specific errors
    BLOCK_NOT_FOUND = "BLOCK_NOT_FOUND"
    BLOCK_INITIALIZATION_FAILED = "BLOCK_INITIALIZATION_FAILED"
    BLOCK_EXECUTION_FAILED = "BLOCK_EXECUTION_FAILED"
    
    # Configuration errors
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"


def create_input_error(
    field: str,
    expected_type: str,
    actual_value: Any,
    code: str = ErrorCode.INPUT_TYPE_MISMATCH
) -> BlockException:
    """Helper to create input validation errors"""
    error = BlockError(
        code=code,
        message=f"Input field '{field}' validation failed",
        details={
            "field": field,
            "expected_type": expected_type,
            "actual_value": str(actual_value),
            "actual_type": type(actual_value).__name__
        },
        hint=f"Ensure '{field}' is of type {expected_type}",
        recoverable=False
    )
    return BlockException(error)


def create_dependency_error(
    node_id: str,
    dependency: str,
    reason: str
) -> BlockException:
    """Helper to create dependency errors"""
    error = BlockError(
        code=ErrorCode.DEPENDENCY_FAILED,
        message=f"Dependency '{dependency}' failed for node '{node_id}'",
        details={
            "node_id": node_id,
            "dependency": dependency,
            "reason": reason
        },
        hint="Check the dependency node's output and ensure it completed successfully",
        recoverable=False
    )
    return BlockException(error)


def create_external_error(
    service: str,
    error_message: str,
    code: str = ErrorCode.EXTERNAL_API_ERROR
) -> BlockException:
    """Helper to create external service errors"""
    error = BlockError(
        code=code,
        message=f"External service '{service}' error: {error_message}",
        details={
            "service": service,
            "original_error": error_message
        },
        hint="Check service availability and credentials",
        recoverable=code != ErrorCode.EXTERNAL_RATE_LIMIT
    )
    return BlockException(error)


def wrap_exception(e: Exception, code: str, inputs: Dict[str, Any]) -> BlockException:
    """Wrap a regular exception as a BlockException"""
    error = BlockError(
        code=code,
        message=str(e),
        details={
            "exception_type": type(e).__name__,
            "exception_args": e.args if hasattr(e, 'args') else []
        },
        input_snapshot=inputs,
        hint="See details for the original exception information",
        recoverable=False
    )
    return BlockException(error)
