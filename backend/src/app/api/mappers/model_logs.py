"""Model-log projections for the HTTP boundary."""

from app.api.contracts import ModelInteractionLog as ApiModelInteractionLog
from app.core.runtime import sensitive_debug_enabled
from app.inference.model_log import ModelInteractionLog


def to_api_model_log(log: ModelInteractionLog) -> ApiModelInteractionLog:
    """Validate one log for HTTP, suppressing debug data in run mode."""
    value = log.model_dump(mode="json")
    if not sensitive_debug_enabled():
        value["debug"] = None
    return ApiModelInteractionLog.model_validate(value)
