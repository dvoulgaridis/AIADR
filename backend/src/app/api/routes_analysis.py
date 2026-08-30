"""API routes for analysis requests and model diagnostics."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

import app.operations.analyze as analysis
from app.api.contracts import ModelLogsResponse
from app.api.mappers.model_logs import to_api_model_log
from app.storage import session_store
from app.storage.model_log_store import get_logs

router = APIRouter(tags=["analysis"])


@router.get("/sessions/{session_id}/model-log")
async def get_model_log(session_id: str) -> ModelLogsResponse:
    """Return model-call summaries and optional development diagnostics."""
    session_store.require_session(session_id)
    return ModelLogsResponse(
        session_id=session_id,
        logs=[to_api_model_log(log) for log in get_logs(session_id)],
    )


@router.post(
    "/sessions/{session_id}/analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=Response,
)
async def request_analysis(
    session_id: str,
) -> Response:
    """Request analysis for the given session."""
    analysis.request(session_id)
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/sessions/{session_id}/analysis/cancel")
async def request_cancel_analysis(session_id: str) -> Response:
    """Cancel active analysis for the given session."""
    if analysis.cancel(session_id):
        return Response(status_code=status.HTTP_202_ACCEPTED)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
