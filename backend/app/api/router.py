from fastapi import APIRouter

from app.api.routes import datasets, health, meta, runs

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(datasets.router)
api_router.include_router(runs.router)
