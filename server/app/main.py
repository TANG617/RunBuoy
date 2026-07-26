from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from .api import router
from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    configured.validate()
    application = FastAPI(
        title="RunBuoy API",
        version="1.0.0",
        description=(
            "One-way Machine-to-iPhone execution projection. "
            "No remote command or terminal control plane exists."
        ),
    )
    application.state.settings = configured
    application.include_router(router)

    @application.get("/healthz", include_in_schema=False)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
