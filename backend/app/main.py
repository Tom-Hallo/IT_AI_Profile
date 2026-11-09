"""Điểm vào của FastAPI: uvicorn app.main:app."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.db.models
from app.api.router import API_PREFIX, api_router
from app.core.config import APP_NAME, APP_VERSION, Settings, settings
from app.core.logging import configure_logging
from app.db.models import init_models

logger = logging.getLogger(__name__)


def create_app(config: Settings | None = None) -> FastAPI:
    init_models()
    cfg = config or settings
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="IT Talent AI Profile API",
        version=APP_VERSION,
        docs_url=f"{API_PREFIX}/docs" if cfg.docs_enabled else None,
        openapi_url=(f"{API_PREFIX}/openapi.json" if cfg.docs_enabled else None),
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=[
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
            "OPTIONS",
        ],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Authorization",
        ],
    )

    app.include_router(api_router, prefix=API_PREFIX)

    logger.info(
        "%s %s khởi động (APP_ENV=%s)",
        APP_NAME,
        APP_VERSION,
        cfg.app_env,
    )

    return app


app = create_app()
