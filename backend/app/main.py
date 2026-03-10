"""Prompt Inspector — open-source prompt injection detection engine."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logger import logger
from app.database import init_db
from app.services.redis_service import init_redis, close_redis
from app.services.embedding_service import init_embedding_client
from app.routers import detection


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(f"Starting {settings.APP_NAME}...")

    # Initialize infrastructure
    await init_db()
    await init_redis()
    init_embedding_client()

    logger.info(f"{settings.APP_NAME} is ready.")
    yield

    # Shutdown
    await close_redis()
    logger.info(f"{settings.APP_NAME} stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Open-source prompt injection detection API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(detection.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
