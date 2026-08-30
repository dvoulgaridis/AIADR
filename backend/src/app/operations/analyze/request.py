"""Request and cancel application-lifetime analysis tasks."""

from __future__ import annotations

import asyncio
import logging

from app.core.task_registry import cancel_task, create_task, mark_finishing
from app.errors import ApplicationError, ErrorCode, app_error
from app.operations.analyze.events import (
    AnalysisCancelledEvent,
    AnalysisCompleteEvent,
    AnalysisErrorEvent,
    AnalysisErrorPayload,
)
from app.operations.analyze.notifications import publish
from app.operations.analyze.run import analyze
from app.storage import session_store

logger = logging.getLogger(__name__)


def request(session_id: str) -> None:
    """Request analysis in the current application process."""
    session_store.require_session(session_id)
    task = create_task(session_id, lambda: _run(session_id))
    if task is None:
        raise app_error(
            ErrorCode.ANALYSIS_ALREADY_RUNNING,
            details={"session_id": session_id},
        )


def cancel(session_id: str) -> bool:
    """Request cancellation of the session's active analysis task."""
    return cancel_task(session_id)


async def _run(session_id: str) -> None:
    """Run one analysis and publish its terminal state after durable commit."""
    try:
        finding_count = await analyze(session_id)
    except asyncio.CancelledError:
        mark_finishing(session_id)
        await publish(AnalysisCancelledEvent(session_id=session_id))
        raise
    except ApplicationError as error:
        mark_finishing(session_id)
        await publish(
            AnalysisErrorEvent(
                session_id=session_id,
                error=AnalysisErrorPayload.from_error(error),
            )
        )
        logger.warning(
            "Analysis failed session_id=%s error_code=%s correlation_id=%s",
            session_id,
            error.code.value,
            error.correlation_id,
        )
    except Exception:
        translated = app_error(ErrorCode.INTERNAL_ERROR)
        mark_finishing(session_id)
        logger.error(
            "Unexpected analysis task failure "
            "session_id=%s correlation_id=%s",
            session_id,
            translated.correlation_id,
        )
        await publish(
            AnalysisErrorEvent(
                session_id=session_id,
                error=AnalysisErrorPayload.from_error(translated),
            )
        )
    else:
        mark_finishing(session_id)
        await publish(
            AnalysisCompleteEvent(
                session_id=session_id,
                finding_count=finding_count,
            )
        )
