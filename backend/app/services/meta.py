from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.schemas.run import LiveRunPolicy, MetaResponse
from app.services.health import database_is_ready


async def build_meta(session: AsyncSession, settings: Settings) -> MetaResponse:
    """Build the workspace metadata response from the active settings.

    Kept outside the route so the recorded-demo exporter produces exactly the shape the dashboard
    reads at runtime.
    """

    return MetaResponse(
        demo_mode=settings.demo_mode,
        write_protected=settings.demo_mode or settings.write_api_token is not None,
        target_kinds=["reference", "http"],
        providers=[
            {
                "id": "mock",
                "label": "Mock extractive (offline)",
                "available": True,
                "requires_key": False,
            },
            {
                "id": "groq",
                "label": "Groq / OpenAI-compatible",
                "available": settings.groq_api_key is not None,
                "requires_key": True,
            },
            {
                "id": "ollama",
                "label": "Ollama (local)",
                "available": True,
                "requires_key": False,
                "base_url": settings.ollama_base_url,
            },
        ],
        judge_modes=["mock", "llm"],
        max_dataset_bytes=settings.max_dataset_bytes,
        max_dataset_items=settings.max_dataset_items,
        max_result_page_size=settings.max_result_page_size,
        sample_dataset_available=settings.sample_dataset_path.exists(),
        database_ready=await database_is_ready(session),
        live_runs=LiveRunPolicy(
            enabled=settings.live_run_protection,
            max_queries_per_run=settings.live_run_max_queries,
            daily_run_cap=settings.live_run_daily_cap if settings.live_run_protection else None,
            per_ip_runs_per_window=(
                settings.live_run_per_ip_limit if settings.live_run_protection else None
            ),
            window_seconds=(
                settings.live_run_rate_window_seconds if settings.live_run_protection else None
            ),
        ),
    )
