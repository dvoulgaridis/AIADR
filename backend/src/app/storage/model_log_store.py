"""SQLite-backed model interaction log store."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.inference.model_log import (
    DebugModelIO,
    ModelInteractionLog,
    ModelResultSummary,
    ParseStatus,
)
from app.inference.requests import ModelRequestSummary
from app.storage import db


def _row_to_log(row: Any) -> ModelInteractionLog:
    debug = None
    if any(
        row[field] is not None
        for field in (
            "debug_request_payload",
            "debug_response_content",
            "debug_error_message",
        )
    ):
        debug = DebugModelIO(
            request_payload=json.loads(row["debug_request_payload"] or "{}"),
            response_content=row["debug_response_content"] or "",
            error_message=row["debug_error_message"],
        )
    return ModelInteractionLog(
        log_id=row["log_id"],
        session_id=row["session_id"],
        created_at=row["created_at"],
        status=row["status"],
        completed_at=row["completed_at"],
        duration_ms=row["duration_ms"],
        kind=row["kind"],
        page=row["page"],
        api_format=row["api_format"],
        model=row["model"],
        request_summary=ModelRequestSummary.model_validate_json(row["request_summary"]),
        result_summary=ModelResultSummary.model_validate_json(row["result_summary"]),
        debug=debug,
        finish_reason=row["finish_reason"],
        input_count_method=row["input_count_method"],
        estimated_input_tokens=row["estimated_input_tokens"],
        provider_counted_input_tokens=row["provider_counted_input_tokens"],
        requested_output_tokens=row["requested_output_tokens"],
        max_input_tokens=row["max_input_tokens"],
        actual_input_tokens=row["actual_input_tokens"],
        actual_output_tokens=row["actual_output_tokens"],
        total_tokens=row["total_tokens"],
        reasoning_tokens=row["reasoning_tokens"],
    )


def upsert_log(log: ModelInteractionLog) -> None:
    """Insert or replace a model interaction log for a session."""
    db.execute(
        """
        INSERT INTO model_logs (
            log_id, session_id, created_at, status, completed_at, duration_ms,
            kind, page, api_format, model, request_summary, result_summary,
            debug_request_payload, debug_response_content, debug_error_message,
            finish_reason, input_count_method, estimated_input_tokens,
            provider_counted_input_tokens, requested_output_tokens,
            max_input_tokens,
            actual_input_tokens, actual_output_tokens, total_tokens,
            reasoning_tokens
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(log_id) DO UPDATE SET
            created_at = excluded.created_at,
            status = excluded.status,
            completed_at = excluded.completed_at,
            duration_ms = excluded.duration_ms,
            kind = excluded.kind,
            page = excluded.page,
            api_format = excluded.api_format,
            model = excluded.model,
            request_summary = excluded.request_summary,
            result_summary = excluded.result_summary,
            debug_request_payload = excluded.debug_request_payload,
            debug_response_content = excluded.debug_response_content,
            debug_error_message = excluded.debug_error_message,
            finish_reason = excluded.finish_reason,
            input_count_method = excluded.input_count_method,
            estimated_input_tokens = excluded.estimated_input_tokens,
            provider_counted_input_tokens = excluded.provider_counted_input_tokens,
            requested_output_tokens = excluded.requested_output_tokens,
            max_input_tokens = excluded.max_input_tokens,
            actual_input_tokens = excluded.actual_input_tokens,
            actual_output_tokens = excluded.actual_output_tokens,
            total_tokens = excluded.total_tokens,
            reasoning_tokens = excluded.reasoning_tokens
        """,
        (
            log.log_id,
            log.session_id,
            log.created_at,
            log.status,
            log.completed_at,
            log.duration_ms,
            log.kind,
            log.page,
            log.api_format,
            log.model,
            log.request_summary.model_dump_json(),
            log.result_summary.model_dump_json(),
            json.dumps(log.debug.request_payload) if log.debug else None,
            log.debug.response_content if log.debug else None,
            log.debug.error_message if log.debug else None,
            log.finish_reason,
            log.input_count_method,
            log.estimated_input_tokens,
            log.provider_counted_input_tokens,
            log.requested_output_tokens,
            log.max_input_tokens,
            log.actual_input_tokens,
            log.actual_output_tokens,
            log.total_tokens,
            log.reasoning_tokens,
        ),
    )


def _record_parse_result(
    log_id: str,
    *,
    status: ParseStatus,
    parsed_finding_count: int | None = None,
    rejected_finding_count: int | None = None,
) -> None:
    with db.connect(immediate=True) as connection:
        row = connection.execute(
            "SELECT result_summary FROM model_logs WHERE log_id = ?",
            (log_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"Model interaction log not found: {log_id}")
        summary = ModelResultSummary.model_validate_json(row["result_summary"]).model_copy(
            update={
                "parse_status": status,
                "parsed_finding_count": parsed_finding_count,
                "rejected_finding_count": rejected_finding_count,
            }
        )
        connection.execute(
            "UPDATE model_logs SET result_summary = ? WHERE log_id = ?",
            (summary.model_dump_json(), log_id),
        )


def record_parse_success(
    log_id: str,
    *,
    parsed_finding_count: int,
    rejected_finding_count: int,
) -> None:
    """Record successful extraction without retaining provider content."""
    _record_parse_result(
        log_id,
        status=ParseStatus.SUCCEEDED,
        parsed_finding_count=parsed_finding_count,
        rejected_finding_count=rejected_finding_count,
    )


def record_parse_failure(log_id: str) -> None:
    """Record that a provider response could not be extracted."""
    _record_parse_result(log_id, status=ParseStatus.FAILED)


def clear_sensitive_debug_fields() -> None:
    """Remove development-only model I/O before serving in run mode."""
    db.execute(
        """
        UPDATE model_logs
        SET debug_request_payload = NULL,
            debug_response_content = NULL,
            debug_error_message = NULL
        WHERE debug_request_payload IS NOT NULL
           OR debug_response_content IS NOT NULL
           OR debug_error_message IS NOT NULL
        """
    )


def get_logs_with_connection(
    connection: sqlite3.Connection,
    session_id: str,
) -> list[ModelInteractionLog]:
    """Return model interaction logs using the caller's transaction."""
    rows = connection.execute(
        """
        SELECT * FROM model_logs
        WHERE session_id = ?
        ORDER BY created_at ASC, log_id ASC
        """,
        (session_id,),
    ).fetchall()
    return [_row_to_log(row) for row in rows]


def get_logs(session_id: str) -> list[ModelInteractionLog]:
    """Return model interaction logs for a session."""
    with db.connect() as connection:
        return get_logs_with_connection(connection, session_id)
