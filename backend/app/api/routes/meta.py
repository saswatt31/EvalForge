from fastapi import APIRouter

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.schemas.run import MetaResponse
from app.services.health import database_is_ready

router = APIRouter(tags=["meta"])


@router.get("/meta", response_model=MetaResponse)
async def get_meta(session: SessionDep) -> MetaResponse:
    settings = get_settings()
    database_ready = await database_is_ready(session)
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
        database_ready=database_ready,
    )
