"""
infra-ai-agent — API entrypoint (Part-1 foundation).

Run locally:
    poetry run uvicorn api.main:app --reload --port 8000

This module intentionally does nothing beyond prove the foundation is
wired correctly: settings load, logging is structured, the process
boots, and a health check responds. RAG/agent/terraform routers are
added in later parts and included here via `app.include_router`.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from configs.logging_config import configure_logging, get_logger
from configs.settings import settings

configure_logging()
log = get_logger("api")

START_TIME = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "infra-ai-agent starting | env={} | region={} | llm_provider={}",
        settings.environment.value,
        settings.aws_region,
        settings.llm_provider.value,
    )
    yield
    log.info("infra-ai-agent shutting down")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Production RAG + AI Agent for AWS infrastructure provisioning via Terraform",
    lifespan=lifespan,
)


@app.get("/health", tags=["system"])
async def health() -> JSONResponse:
    """Liveness/readiness probe target for Docker/Kubernetes."""
    return JSONResponse(
        {
            "status": "ok",
            "service": settings.app_name,
            "environment": settings.environment.value,
            "uptime_seconds": round(time.time() - START_TIME, 2),
        }
    )


@app.get("/", tags=["system"])
async def root() -> dict:
    return {
        "service": settings.app_name,
        "message": "Foundation online. RAG, agent, and terraform-engine routers land in Part-2+.",
    }


# --- Routers added in later parts (kept here as the wiring point) ---
# from rag.router import router as rag_router
# from agent.router import router as agent_router
# from terraform_engine.router import router as terraform_router
# app.include_router(rag_router, prefix="/rag", tags=["rag"])
# app.include_router(agent_router, prefix="/agent", tags=["agent"])
# app.include_router(terraform_router, prefix="/terraform", tags=["terraform"])
