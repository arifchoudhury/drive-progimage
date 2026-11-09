from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.images.api.body_limit import MaxBodySizeMiddleware
from app.images.api.router import router as images_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory. Run with `uvicorn --factory app.main:create_app`; tests pass their own Settings."""
    settings = settings or get_settings()
    app = FastAPI(title="ProgImage")
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_request_bytes)
    app.include_router(images_router)
    return app
