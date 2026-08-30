"""Construct and run the AIADR API and WebUI."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint

PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_SRC = PROJECT_ROOT / "backend" / "src"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
logger = logging.getLogger("aiadr.startup")
_API_PREFIX = "/api/v1"
_SESSION_PREFIX = f"{_API_PREFIX}/sessions/"


def _add_backend_source() -> None:
    if not (BACKEND_SRC / "app").is_dir():
        raise RuntimeError(f"Backend source not found under {BACKEND_SRC}.")

    source = str(BACKEND_SRC)
    if source not in sys.path:
        sys.path.insert(0, source)


def _load_environment() -> None:
    from app.core.env import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")


def _bootstrap() -> None:
    _add_backend_source()
    _load_environment()


_bootstrap()

from app.core.runtime import (  # noqa: E402, I001
    RuntimeMode,
    configure_runtime_mode,
    runtime_mode as configured_runtime_mode,
)


def _public_file(root: Path, requested_path: str) -> Path | None:
    candidate = (root / requested_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _api_cache_control(path: str) -> str | None:
    if path != _API_PREFIX and not path.startswith(f"{_API_PREFIX}/"):
        return None

    if path.startswith(_SESSION_PREFIX):
        session_path = path.removeprefix(_SESSION_PREFIX)
        if session_path.count("/") == 1 and session_path.endswith("/preview"):
            return "private, no-cache"

    return "no-store"


async def _set_api_cache_control(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    response = await call_next(request)
    if cache_control := _api_cache_control(request.url.path):
        response.headers["Cache-Control"] = cache_control
    return response


def _mount_webui(application: FastAPI) -> None:
    dist = FRONTEND_DIST.resolve()
    index = dist / "index.html"
    assets = dist / "assets"

    if not index.is_file() or not assets.is_dir():
        raise RuntimeError(
            f"Compiled WebUI not found under {dist}. Run `pnpm --dir frontend run build`."
        )

    application.mount("/assets", StaticFiles(directory=assets), name="webui-assets")

    @application.get("/", include_in_schema=False)
    async def webui_index() -> FileResponse:
        return FileResponse(index)

    @application.get("/{requested_path:path}", include_in_schema=False)
    async def webui_route(requested_path: str) -> FileResponse:
        if requested_path == "api" or requested_path.startswith("api/"):
            raise HTTPException(status_code=404)

        public_file = _public_file(dist, requested_path)
        return FileResponse(public_file or index)


def create_app(*, runtime_mode: RuntimeMode | None = None) -> FastAPI:
    """Create the AIADR application for the selected runtime mode."""
    mode = runtime_mode or configured_runtime_mode()
    configure_runtime_mode(mode)

    from app.adapters.docx import close_runtime, configure_runtime
    from app.api import (
        routes_analysis,
        routes_audit,
        routes_events,
        routes_exports,
        routes_instruction_sets,
        routes_review,
        routes_sessions,
        routes_settings,
        routes_sources,
        routes_uploads,
    )
    from app.api.contracts import HealthResponse
    from app.api.error_handlers import register_exception_handlers
    from app.api.openapi import install_openapi_contract
    from app.core.paths import ensure_data_dirs
    from app.core.version import application_version, source_identity
    from app.storage.bootstrap import initialize_storage

    configure_runtime(development=mode is RuntimeMode.DEV)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        source = source_identity()
        logger.info(
            "AIADR started application_version=%s source_revision=%s "
            "source_modified=%s runtime_mode=%s",
            application_version(),
            source.revision,
            source.modified,
            mode,
        )
        yield
        await close_runtime()

    application = FastAPI(
        title="AIADR",
        description="AI-Assisted Data Review",
        version=application_version(),
        lifespan=lifespan,
    )
    application.middleware("http")(_set_api_cache_control)

    register_exception_handlers(application)
    ensure_data_dirs()
    initialize_storage()

    routers = (
        routes_instruction_sets.router,
        routes_settings.router,
        routes_uploads.router,
        routes_sessions.router,
        routes_sources.router,
        routes_analysis.router,
        routes_review.router,
        routes_events.router,
        routes_exports.router,
        routes_audit.router,
    )
    for router in routers:
        application.include_router(router, prefix="/api/v1")

    async def health() -> HealthResponse:
        source = source_identity()
        return HealthResponse(
            status="ok",
            application_version=application_version(),
            source_revision=source.revision,
            source_modified=source.modified,
        )

    application.add_api_route(
        "/api/v1/health",
        health,
        methods=["GET"],
        response_model=HealthResponse,
        tags=["health"],
    )

    install_openapi_contract(application)
    if mode is RuntimeMode.RUN:
        _mount_webui(application)

    return application


def _parse_mode(arguments: Sequence[str] | None = None) -> RuntimeMode:
    parser = argparse.ArgumentParser(prog="AIADR")
    parser.add_argument(
        "mode",
        nargs="?",
        choices=tuple(mode.value for mode in RuntimeMode),
        default=RuntimeMode.RUN.value,
        help="Use 'dev' for the reloadable API; the default serves the compiled WebUI.",
    )
    return RuntimeMode(parser.parse_args(arguments).mode)


def main(arguments: Sequence[str] | None = None) -> None:
    """Run AIADR in normal or backend-development mode."""
    mode = _parse_mode(arguments)
    development = mode is RuntimeMode.DEV

    configure_runtime_mode(mode)

    from app.core.config import HOST, LOG_LEVEL, PORT

    uvicorn.run(
        "main:create_app",
        factory=True,
        host="127.0.0.1" if development else HOST,
        port=8000 if development else PORT,
        log_level=LOG_LEVEL.lower(),
        reload=development,
        workers=1,
        timeout_graceful_shutdown=2 if development else None,
    )


if __name__ == "__main__":
    main()
