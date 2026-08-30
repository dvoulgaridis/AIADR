"""Typed, privacy-aware records of model interactions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, JsonValue

from app.inference.provider import TokenCountMethod
from app.inference.requests import ModelRequestSummary
from app.models.model import ApiFormat
from app.sources.kinds import SourceKind


class ModelInteractionStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ParseStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


class ModelResultSummary(BaseModel):
    """Content-free provider and extraction outcome metadata."""

    response_size_bytes: int | None = Field(default=None, ge=0)
    parse_status: ParseStatus = ParseStatus.PENDING
    parsed_finding_count: int | None = Field(default=None, ge=0)
    rejected_finding_count: int | None = Field(default=None, ge=0)
    provider_code: str | None = None
    provider_status: int | None = None
    provider_request_id: str | None = None
    provider_retryable: bool | None = None

    model_config = {"extra": "forbid", "frozen": True}


class DebugModelIO(BaseModel):
    """Development-only textual request, response, and error diagnostics."""

    request_payload: dict[str, JsonValue] = Field(default_factory=dict)
    response_content: str = ""
    error_message: str | None = None

    model_config = {"extra": "forbid", "frozen": True}


class ModelInteractionLog(BaseModel):
    """A model interaction with optional development-only diagnostics."""

    log_id: str = Field(..., description="Unique log identifier.")
    session_id: str = Field(..., description="Review session identifier.")
    created_at: str = Field(..., description="ISO timestamp.")
    status: ModelInteractionStatus = ModelInteractionStatus.STARTED
    completed_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    kind: SourceKind = Field(..., description="Analyzed source kind.")
    page: int | None = Field(default=None, description="PDF page number when applicable.")
    api_format: ApiFormat
    model: str = Field(default="", description="Configured model identifier.")
    request_summary: ModelRequestSummary
    result_summary: ModelResultSummary = Field(default_factory=ModelResultSummary)
    debug: DebugModelIO | None = None
    finish_reason: str | None = Field(default=None)
    input_count_method: TokenCountMethod | None = None
    estimated_input_tokens: int | None = Field(default=None, ge=0)
    provider_counted_input_tokens: int | None = Field(default=None, ge=0)
    requested_output_tokens: int | None = Field(default=None, ge=0)
    max_input_tokens: int | None = Field(default=None, ge=0)
    actual_input_tokens: int | None = Field(default=None, ge=0)
    actual_output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid", "frozen": True}
