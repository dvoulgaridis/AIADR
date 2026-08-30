"""Pure token-budget admission rules shared by every provider format."""

from __future__ import annotations

from app.errors import ErrorCode, app_error
from app.inference.provider import InputTokenCount, TokenBudget, TokenConstraints


def maximum_input_tokens(
    constraints: TokenConstraints,
    *,
    requested_output_tokens: int | None,
) -> int | None:
    """Return the strictest known input allowance for one request."""
    limits = [constraints.max_input_tokens]
    if constraints.context_window_tokens is not None:
        limits.append(constraints.context_window_tokens - (requested_output_tokens or 0))
    known_limits = [limit for limit in limits if limit is not None]
    return min(known_limits) if known_limits else None


def validate_token_budget(
    count: InputTokenCount,
    constraints: TokenConstraints,
    *,
    requested_output_tokens: int | None,
) -> TokenBudget:
    """Validate one counted request without silently changing generation settings."""
    output_limit = constraints.max_output_tokens
    if (
        output_limit is not None
        and requested_output_tokens is not None
        and requested_output_tokens > output_limit
    ):
        raise app_error(
            ErrorCode.MODEL_OUTPUT_LIMIT_EXCEEDED,
            details={
                "requested_output_tokens": requested_output_tokens,
                "max_output_tokens": output_limit,
            },
        )

    input_limit = constraints.max_input_tokens
    if input_limit is not None and count.tokens > input_limit:
        raise app_error(
            ErrorCode.MODEL_INPUT_LIMIT_EXCEEDED,
            details={
                "input_tokens": count.tokens,
                "max_input_tokens": input_limit,
                "input_count_method": count.method,
            },
        )

    context_window = constraints.context_window_tokens
    requested_total = requested_output_tokens or 0
    if context_window is not None and count.tokens + requested_total > context_window:
        raise app_error(
            ErrorCode.MODEL_CONTEXT_LIMIT_EXCEEDED,
            details={
                "input_tokens": count.tokens,
                "requested_output_tokens": requested_output_tokens,
                "context_window_tokens": context_window,
                "input_count_method": count.method,
            },
        )

    return TokenBudget(
        input_tokens=count.tokens,
        input_count_method=count.method,
        requested_output_tokens=requested_output_tokens,
    )
