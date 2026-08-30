"""Safe public definitions for every application error code."""

from __future__ import annotations

from typing import Final

from app.errors.types import ErrorCategory, ErrorCode, ErrorSpec

ERROR_SPECS: Final[dict[ErrorCode, ErrorSpec]] = {
    ErrorCode.REQUEST_VALIDATION_FAILED: ErrorSpec(
        "The request contains invalid data.", ErrorCategory.VALIDATION
    ),
    ErrorCode.EMPTY_UPDATE: ErrorSpec(
        "At least one field must be provided.", ErrorCategory.VALIDATION
    ),
    ErrorCode.UNSUPPORTED_UPLOAD_TYPE: ErrorSpec(
        "The uploaded file type is not supported.", ErrorCategory.VALIDATION
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorSpec(
        "The uploaded file exceeds the configured size limit.", ErrorCategory.VALIDATION
    ),
    ErrorCode.TEXT_LINE_TOO_LARGE: ErrorSpec(
        "A text line is too large for one model request.", ErrorCategory.VALIDATION
    ),
    ErrorCode.UNSAFE_PATH: ErrorSpec(
        "The requested file path is outside the managed data directory.",
        ErrorCategory.VALIDATION,
    ),
    ErrorCode.NO_MODELS: ErrorSpec(
        "No saved models were found. Add a model in Settings.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.MODEL_NOT_FOUND: ErrorSpec(
        "The saved model was not found.", ErrorCategory.VALIDATION
    ),
    ErrorCode.MODEL_STORE_INVALID: ErrorSpec(
        "The saved model file is invalid.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.ACTIVE_MODEL_NOT_SET: ErrorSpec(
        "Select an active model in Settings before analyzing.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.ACTIVE_INSTRUCTION_SET_NOT_SET: ErrorSpec(
        "Select an active policy in Settings before analyzing.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.SETTINGS_STORE_INVALID: ErrorSpec(
        "The saved application settings are invalid.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.MODEL_ENDPOINT_NOT_CONFIGURED: ErrorSpec(
        "Configure the selected model endpoint before analyzing.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.TOKEN_COUNT_FAILED: ErrorSpec(
        "The model endpoint could not count the request tokens.",
        ErrorCategory.TRANSPORT,
        retryable=True,
    ),
    ErrorCode.MODEL_INPUT_LIMIT_EXCEEDED: ErrorSpec(
        "The model request exceeds the input-token limit.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.MODEL_OUTPUT_LIMIT_EXCEEDED: ErrorSpec(
        "The requested output-token limit exceeds the model limit.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.MODEL_CONTEXT_LIMIT_EXCEEDED: ErrorSpec(
        "The model request exceeds the configured context window.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.VISION_NOT_SUPPORTED: ErrorSpec(
        "The selected model is not configured for vision analysis.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.AUDIO_NOT_SUPPORTED: ErrorSpec(
        "The selected model is not configured for audio analysis.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.PDF_DEPENDENCY_MISSING: ErrorSpec(
        "PDF support requires pypdfium2.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.DOCX_PROCESSOR_MISSING: ErrorSpec(
        "The DOCX processor is not available.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.DOCX_PROCESSOR_BUSY: ErrorSpec(
        "The DOCX processor is busy. Try again shortly.",
        ErrorCategory.PROCESSING,
        retryable=True,
    ),
    ErrorCode.DOCX_UNSUPPORTED_FEATURE: ErrorSpec(
        "The DOCX contains a feature that is not supported safely.",
        ErrorCategory.VALIDATION,
    ),
    ErrorCode.DOCX_PROCESSING_FAILED: ErrorSpec(
        "DOCX processing failed.",
        ErrorCategory.PROCESSING,
    ),
    ErrorCode.DOCUMENT_CONVERTER_MISSING: ErrorSpec(
        "DOCX preview requires a user-installed LibreOffice application.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.DOCUMENT_CONVERSION_FAILED: ErrorSpec(
        "LibreOffice could not convert the document preview.",
        ErrorCategory.PROCESSING,
    ),
    ErrorCode.FFMPEG_UNAVAILABLE: ErrorSpec(
        "Audio processing requires a user-installed FFmpeg binary.",
        ErrorCategory.CONFIGURATION,
    ),
    ErrorCode.PROMPT_MISSING: ErrorSpec(
        "The required prompt template is missing.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.UNSUPPORTED_PROMPT_KIND: ErrorSpec(
        "No prompt is configured for this source kind.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.INSTRUCTION_SET_NOT_FOUND: ErrorSpec(
        "The requested instruction set was not found.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.INVALID_INSTRUCTION_SET: ErrorSpec(
        "The instruction set is invalid.", ErrorCategory.CONFIGURATION
    ),
    ErrorCode.INSTRUCTION_SET_EXISTS: ErrorSpec(
        "An instruction set with this ID already exists.", ErrorCategory.CONFLICT
    ),
    ErrorCode.INSTRUCTION_SET_CONFLICT: ErrorSpec(
        "The instruction set changed since it was loaded.", ErrorCategory.CONFLICT
    ),
    ErrorCode.INSTRUCTION_SET_NOT_LOCKED: ErrorSpec(
        "The session has no instruction-set snapshot.", ErrorCategory.CONFLICT
    ),
    ErrorCode.INSTRUCTION_SET_INTEGRITY_ERROR: ErrorSpec(
        "The stored instruction-set snapshot failed integrity validation.", ErrorCategory.STORAGE
    ),
    ErrorCode.SESSION_NOT_FOUND: ErrorSpec(
        "The review session was not found.", ErrorCategory.VALIDATION
    ),
    ErrorCode.SESSION_FILE_MISSING: ErrorSpec(
        "The uploaded file for this session is missing.", ErrorCategory.STORAGE
    ),
    ErrorCode.SOURCE_INTEGRITY_ERROR: ErrorSpec(
        "Stored source file metadata is internally inconsistent.",
        ErrorCategory.STORAGE,
    ),
    ErrorCode.ANALYSIS_ALREADY_RUNNING: ErrorSpec(
        "Analysis is already running for this session.", ErrorCategory.CONFLICT
    ),
    ErrorCode.PROVIDER_CONNECTION_FAILED: ErrorSpec(
        "The configured model endpoint is unavailable or not reachable.",
        ErrorCategory.TRANSPORT,
        retryable=True,
    ),
    ErrorCode.PROVIDER_MODEL_NOT_FOUND: ErrorSpec(
        "The configured model was not found at the endpoint.", ErrorCategory.TRANSPORT
    ),
    ErrorCode.PROVIDER_AUTHENTICATION_FAILED: ErrorSpec(
        "The model endpoint rejected the configured credentials.",
        ErrorCategory.TRANSPORT,
    ),
    ErrorCode.PROVIDER_RATE_LIMITED: ErrorSpec(
        "The model endpoint is temporarily rate limited.",
        ErrorCategory.TRANSPORT,
        retryable=True,
    ),
    ErrorCode.PROVIDER_REQUEST_INVALID: ErrorSpec(
        "The model endpoint rejected the request.", ErrorCategory.TRANSPORT
    ),
    ErrorCode.PROVIDER_RESPONSE_INVALID: ErrorSpec(
        "The model returned a response that could not be converted into findings.",
        ErrorCategory.PROCESSING,
    ),
    ErrorCode.NOT_PDF_SESSION: ErrorSpec(
        "This operation is available only for PDF sessions.", ErrorCategory.VALIDATION
    ),
    ErrorCode.PDF_PAGE_OUT_OF_RANGE: ErrorSpec(
        "The requested PDF page is out of range.", ErrorCategory.VALIDATION
    ),
    ErrorCode.INVALID_DOCX_TEXT_TARGET: ErrorSpec(
        "The DOCX text target is invalid.", ErrorCategory.VALIDATION
    ),
    ErrorCode.FINDING_NOT_FOUND: ErrorSpec("The finding was not found.", ErrorCategory.VALIDATION),
    ErrorCode.LAYER_NOT_FOUND: ErrorSpec(
        "The redaction layer was not found.", ErrorCategory.VALIDATION
    ),
    ErrorCode.INVALID_FINDING_UPDATE: ErrorSpec(
        "The finding update violates the source target contract.",
        ErrorCategory.VALIDATION,
    ),
    ErrorCode.INVALID_LAYER_UPDATE: ErrorSpec(
        "The layer update violates the effect contract.", ErrorCategory.VALIDATION
    ),
    ErrorCode.DUPLICATE_FINDING_LAYER: ErrorSpec(
        "Each finding must have exactly one layer.", ErrorCategory.CONFLICT
    ),
    ErrorCode.INVALID_ACTION_EFFECT: ErrorSpec(
        "The selected action and effect are not valid for this source kind.",
        ErrorCategory.VALIDATION,
    ),
    ErrorCode.OUTPUT_MISSING: ErrorSpec(
        "No redacted output has been rendered.", ErrorCategory.VALIDATION
    ),
    ErrorCode.OUTPUT_STATE_CHANGED: ErrorSpec(
        "The source or review changed while rendering. Try again.",
        ErrorCategory.CONFLICT,
        retryable=True,
    ),
    ErrorCode.OUTPUT_BLOCKED_PENDING_REVIEW: ErrorSpec(
        "All findings must be reviewed before rendering output.",
        ErrorCategory.CONFLICT,
    ),
    ErrorCode.AUDIO_RENDER_FAILED: ErrorSpec(
        "FFmpeg failed to render redacted audio.", ErrorCategory.RENDERING
    ),
    ErrorCode.EXPORT_MISSING: ErrorSpec(
        "No export bundle has been created for this session.", ErrorCategory.EXPORT
    ),
    ErrorCode.REVIEW_INTEGRITY_ERROR: ErrorSpec(
        "Stored review data is internally inconsistent.", ErrorCategory.STORAGE
    ),
    ErrorCode.INTERNAL_ERROR: ErrorSpec(
        "An unexpected internal error occurred.", ErrorCategory.INTERNAL
    ),
}

if set(ERROR_SPECS) != set(ErrorCode):
    raise RuntimeError("The application error catalog must define every error code.")
