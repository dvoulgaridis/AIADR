"""Typed application-error identities and JSON-compatible detail values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
ErrorDetails: TypeAlias = dict[str, JsonValue]


class ErrorCategory(StrEnum):
    """Broad application failure category shared with API clients."""

    VALIDATION = "validation"
    CONFLICT = "conflict"
    CONFIGURATION = "configuration"
    TRANSPORT = "transport"
    PROCESSING = "processing"
    RENDERING = "rendering"
    EXPORT = "export"
    STORAGE = "storage"
    INTERNAL = "internal"


class ErrorCode(StrEnum):
    """Stable identities for failures that cross an application boundary."""

    REQUEST_VALIDATION_FAILED = "request_validation_failed"
    EMPTY_UPDATE = "empty_update"
    UNSUPPORTED_UPLOAD_TYPE = "unsupported_upload_type"
    FILE_TOO_LARGE = "file_too_large"
    TEXT_LINE_TOO_LARGE = "text_line_too_large"
    UNSAFE_PATH = "unsafe_path"

    NO_MODELS = "no_models"
    MODEL_NOT_FOUND = "model_not_found"
    MODEL_STORE_INVALID = "model_store_invalid"
    ACTIVE_MODEL_NOT_SET = "active_model_not_set"
    ACTIVE_INSTRUCTION_SET_NOT_SET = "active_instruction_set_not_set"
    SETTINGS_STORE_INVALID = "settings_store_invalid"
    MODEL_ENDPOINT_NOT_CONFIGURED = "model_endpoint_not_configured"
    TOKEN_COUNT_FAILED = "token_count_failed"
    MODEL_INPUT_LIMIT_EXCEEDED = "model_input_limit_exceeded"
    MODEL_OUTPUT_LIMIT_EXCEEDED = "model_output_limit_exceeded"
    MODEL_CONTEXT_LIMIT_EXCEEDED = "model_context_limit_exceeded"
    VISION_NOT_SUPPORTED = "vision_not_supported"
    AUDIO_NOT_SUPPORTED = "audio_not_supported"
    PDF_DEPENDENCY_MISSING = "pdf_dependency_missing"
    DOCX_PROCESSOR_MISSING = "docx_processor_missing"
    DOCX_PROCESSOR_BUSY = "docx_processor_busy"
    DOCX_UNSUPPORTED_FEATURE = "docx_unsupported_feature"
    DOCX_PROCESSING_FAILED = "docx_processing_failed"
    DOCUMENT_CONVERTER_MISSING = "document_converter_missing"
    DOCUMENT_CONVERSION_FAILED = "document_conversion_failed"
    FFMPEG_UNAVAILABLE = "ffmpeg_unavailable"
    PROMPT_MISSING = "prompt_missing"
    UNSUPPORTED_PROMPT_KIND = "unsupported_prompt_kind"
    INSTRUCTION_SET_NOT_FOUND = "instruction_set_not_found"
    INVALID_INSTRUCTION_SET = "invalid_instruction_set"
    INSTRUCTION_SET_EXISTS = "instruction_set_exists"
    INSTRUCTION_SET_CONFLICT = "instruction_set_conflict"
    INSTRUCTION_SET_NOT_LOCKED = "instruction_set_not_locked"
    INSTRUCTION_SET_INTEGRITY_ERROR = "instruction_set_integrity_error"

    SESSION_NOT_FOUND = "session_not_found"
    SESSION_FILE_MISSING = "session_file_missing"
    SOURCE_INTEGRITY_ERROR = "source_integrity_error"
    ANALYSIS_ALREADY_RUNNING = "analysis_already_running"

    PROVIDER_CONNECTION_FAILED = "provider_connection_failed"
    PROVIDER_MODEL_NOT_FOUND = "provider_model_not_found"
    PROVIDER_AUTHENTICATION_FAILED = "provider_authentication_failed"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    PROVIDER_REQUEST_INVALID = "provider_request_invalid"
    PROVIDER_RESPONSE_INVALID = "provider_response_invalid"

    NOT_PDF_SESSION = "not_pdf_session"
    PDF_PAGE_OUT_OF_RANGE = "pdf_page_out_of_range"
    INVALID_DOCX_TEXT_TARGET = "invalid_docx_text_target"
    FINDING_NOT_FOUND = "finding_not_found"
    LAYER_NOT_FOUND = "layer_not_found"
    INVALID_FINDING_UPDATE = "invalid_finding_update"
    INVALID_LAYER_UPDATE = "invalid_layer_update"
    DUPLICATE_FINDING_LAYER = "duplicate_finding_layer"
    INVALID_ACTION_EFFECT = "invalid_action_effect"

    OUTPUT_MISSING = "output_missing"
    OUTPUT_STATE_CHANGED = "output_state_changed"
    OUTPUT_BLOCKED_PENDING_REVIEW = "output_blocked_pending_review"
    AUDIO_RENDER_FAILED = "audio_render_failed"
    EXPORT_MISSING = "export_missing"

    REVIEW_INTEGRITY_ERROR = "review_integrity_error"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """Application-owned public definition of an error code."""

    message: str
    category: ErrorCategory
    retryable: bool = False
