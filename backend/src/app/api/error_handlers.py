"""FastAPI delivery boundary for structured application errors."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.contracts import ErrorCategory as ApiErrorCategory
from app.api.contracts import ErrorCode as ApiErrorCode
from app.api.contracts import ErrorResponse
from app.api.error_status import http_status_for
from app.errors import ApplicationError, ErrorCode, ErrorDetails, app_error

logger = logging.getLogger(__name__)


def _response(error: ApplicationError) -> JSONResponse:
    payload = ErrorResponse(
        code=ApiErrorCode(error.code.value),
        message=error.message,
        category=ApiErrorCategory(error.category.value),
        retryable=error.retryable,
        details=error.details,
        correlation_id=error.correlation_id,
    )
    return JSONResponse(
        status_code=http_status_for(error.code),
        content=payload.model_dump(mode="json"),
        headers={"X-Correlation-ID": error.correlation_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all public exception translation at the HTTP boundary."""

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        logger.info(
            "Application request failed method=%s path=%s error_code=%s correlation_id=%s",
            request.method,
            request.url.path,
            error.code.value,
            error.correlation_id,
        )
        return _response(error)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        details: ErrorDetails = {
            "errors": [
                {
                    "location": [str(part) for part in item["loc"]],
                    "message": str(item["msg"]),
                    "type": str(item["type"]),
                }
                for item in error.errors()
            ]
        }
        application_error = app_error(
            ErrorCode.REQUEST_VALIDATION_FAILED,
            details=details,
        )
        logger.info(
            "Request validation failed method=%s path=%s correlation_id=%s",
            request.method,
            request.url.path,
            application_error.correlation_id,
        )
        return _response(application_error)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
        application_error = app_error(ErrorCode.INTERNAL_ERROR)
        logger.error(
            "Unexpected request failure method=%s path=%s correlation_id=%s",
            request.method,
            request.url.path,
            application_error.correlation_id,
        )
        return _response(application_error)
