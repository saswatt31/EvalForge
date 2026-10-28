from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.reference.bootstrap import ensure_reference_index
from app.services.demo import seed_demo_data
from app.storage.session import SessionFactory, engine
from app.workers.manager import RunManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.reference_index_on_startup:
        try:
            await asyncio.to_thread(ensure_reference_index, settings)
        except Exception:
            # The API stays available so /health and the dashboard can explain the failure.
            # Reference runs retry indexing on demand and report a concrete error if Qdrant is down.
            logger.exception("Reference index startup check failed")
    if settings.demo_mode:
        async with SessionFactory() as session:
            await seed_demo_data(session, settings)
    manager = RunManager(settings, SessionFactory)
    application.state.run_manager = manager
    await manager.start()
    try:
        yield
    finally:
        await manager.stop()
        await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="RAG quality evaluation and latency benchmarking.",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(api_router, prefix=settings.api_prefix)

    @application.get("/health", include_in_schema=False)
    async def root_health() -> dict[str, str]:
        """Unauthenticated liveness endpoint used by Render and container health checks."""

        return {
            "status": "ok",
            "service": settings.app_name,
            "version": __version__,
            "environment": settings.environment,
        }

    return application


app = create_app()
