"""Typed internal events for analysis progress and terminal states."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field
from pydantic import JsonValue as PydanticJsonValue

from app.errors import ApplicationError, ErrorCategory, ErrorCode


class AnalysisEventType(StrEnum):
    PROGRESS = "progress"
    COMPLETE = "complete"
    ERROR = "error"
    CANCELLED = "cancelled"


class AnalysisErrorPayload(BaseModel):
    """Safe application failure embedded in an analysis event."""

    code: ErrorCode
    message: str
    category: ErrorCategory
    retryable: bool
    details: dict[str, PydanticJsonValue] | None
    correlation_id: str

    model_config = {"extra": "forbid", "frozen": True}

    @classmethod
    def from_error(cls, error: ApplicationError) -> AnalysisErrorPayload:
        """Build a wire-compatible payload from one error occurrence."""
        return cls(
            code=error.code,
            message=error.message,
            category=error.category,
            retryable=error.retryable,
            details=error.details,
            correlation_id=error.correlation_id,
        )


class AnalysisProgressEvent(BaseModel):
    """Nonterminal analysis progress update."""

    event_type: Literal[AnalysisEventType.PROGRESS] = AnalysisEventType.PROGRESS
    session_id: str
    page: int | None = Field(default=None, ge=1)
    progress: float = Field(ge=0.0, le=1.0)
    message: str

    model_config = {"extra": "forbid", "frozen": True}


class AnalysisCompleteEvent(BaseModel):
    """Successful analysis terminal event."""

    event_type: Literal[AnalysisEventType.COMPLETE] = AnalysisEventType.COMPLETE
    session_id: str
    progress: float = Field(default=1.0, ge=0.0, le=1.0)
    message: str = "Analysis complete"
    finding_count: int = Field(ge=0)

    model_config = {"extra": "forbid", "frozen": True}


class AnalysisErrorEvent(BaseModel):
    """Failed analysis terminal event."""

    event_type: Literal[AnalysisEventType.ERROR] = AnalysisEventType.ERROR
    session_id: str
    progress: float = Field(default=1.0, ge=0.0, le=1.0)
    error: AnalysisErrorPayload

    model_config = {"extra": "forbid", "frozen": True}


class AnalysisCancelledEvent(BaseModel):
    """User-cancelled analysis terminal event."""

    event_type: Literal[AnalysisEventType.CANCELLED] = AnalysisEventType.CANCELLED
    session_id: str
    progress: float = Field(default=1.0, ge=0.0, le=1.0)
    message: str = "Analysis cancelled"

    model_config = {"extra": "forbid", "frozen": True}


AnalysisEvent: TypeAlias = Annotated[
    AnalysisProgressEvent | AnalysisCompleteEvent | AnalysisErrorEvent | AnalysisCancelledEvent,
    Field(discriminator="event_type"),
]
