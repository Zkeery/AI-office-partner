from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.catalog import router as catalog_router
from app.api.feishu import router as feishu_router
from app.api.schedules import router as schedules_router
from app.api.tasks import router as tasks_router, cancel_running_jobs
from app.api.workspace import router as workspace_router
from app.core.config import get_settings
from app.core.errors import AppError, register_exception_handlers
from app.core.process_lock import data_lock
from app.db import session as db_session
from app.db.session import init_db
from app.services.scheduler_loop import scheduler_loop
from app.services.tasks import recover_running_tasks
from app.services.schedules import DEFAULT_SCHEDULE_TOKEN_BUDGET, recover_schedule_runs
from app.services.models import selection_metadata


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    with data_lock(settings.data_path):
        async with service_lifespan(settings):
            yield


@asynccontextmanager
async def service_lifespan(settings):
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    settings.artifacts_path.mkdir(parents=True, exist_ok=True)
    init_db()
    db = db_session.SessionLocal()
    try:
        recover_running_tasks(db)
        recover_schedule_runs(db)
    finally:
        db.close()

    stop = asyncio.Event()
    task = asyncio.create_task(scheduler_loop(stop, interval_sec=30.0))
    try:
        yield
    finally:
        stop.set()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await cancel_running_jobs()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI办公搭子", version="0.1.0", lifespan=lifespan)
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin, "http://localhost:3040"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health():
        s = get_settings()
        try:
            default_model = selection_metadata(s)["model_id"]
        except AppError:
            default_model = None
        return {
            "status": "ok",
            "service": "AI办公搭子",
            "llm_mock": s.llm_mock,
            "search_mock": s.search_mock,
            "feishu_mock": s.feishu_mock,
            "llm_configured": bool(s.llm_api_key),
            "search_configured": bool(s.tavily_api_key),
            "llm_model": s.llm_model,
            "default_model_id": default_model,
            "default_schedule_token_budget": DEFAULT_SCHEDULE_TOKEN_BUDGET,
        }

    app.include_router(tasks_router)
    app.include_router(workspace_router)
    app.include_router(catalog_router)
    app.include_router(schedules_router)
    app.include_router(feishu_router)
    return app


app = create_app()
