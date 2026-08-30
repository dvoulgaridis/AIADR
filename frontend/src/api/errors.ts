import type { ErrorResponse } from "./contracts";

export class ApiError extends Error {
  readonly response: ErrorResponse;

  constructor(response: ErrorResponse) {
    super(response.message);
    this.response = response;
  }

  get code(): ErrorResponse["code"] {
    return this.response.code;
  }

  get retryable(): boolean {
    return this.response.retryable;
  }

  get correlationId(): string {
    return this.response.correlation_id;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
