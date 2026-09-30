"""FastAPI application entry point.

Run from the ``backend/`` directory:
    uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import alerts, analysis, datasets, geo, health, model, transactions, wallets
from app.config import Settings, get_settings
from app.logging_config import setup_logging
from app.preprocessing.ip_geolocation import geo_service_for_settings
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging(settings.log_level, settings.logs_dir if settings.log_to_file else None)
        settings.ensure_directories()
        app.state.settings = settings
        app.state.store = DuckDBStore(settings.duckdb_path)
        app.state.store.init_schema()
        app.state.geo = geo_service_for_settings(settings)
        logger.info("Backend started (%s, v%s)", settings.environment, __version__)
        try:
            yield
        finally:
            app.state.geo.close()
            app.state.store.close()
            logger.info("Backend stopped")

    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    for module in (health, geo, datasets, transactions, wallets, alerts, analysis, model):
        app.include_router(module.router)
    app.include_router(datasets.summary_router)
    return app


app = create_app()
