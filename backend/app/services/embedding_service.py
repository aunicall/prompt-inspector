"""Embedding service: generate text embeddings via self-hosted or Bailian (DashScope)."""

import asyncio
from typing import Optional

from openai import AsyncOpenAI

from app.config import settings
from app.logger import logger

_client: Optional[AsyncOpenAI] = None


def init_embedding_client() -> AsyncOpenAI:
    """Initialize the embedding client based on provider config."""
    global _client
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "bailian":
        _client = AsyncOpenAI(
            base_url=settings.DASHSCOPE_BASE_URL,
            api_key=settings.DASHSCOPE_API_KEY,
        )
        logger.info(f"Embedding client initialized: Bailian ({settings.DASHSCOPE_MODEL})")
    else:
        _client = AsyncOpenAI(
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
        )
        logger.info(f"Embedding client initialized: self-hosted ({settings.EMBEDDING_MODEL})")
    return _client


def get_embedding_client() -> AsyncOpenAI:
    if _client is None:
        raise RuntimeError("Embedding client not initialized")
    return _client


async def get_embedding(text: str) -> list[float]:
    """Compute embedding for a single text string."""
    client = get_embedding_client()
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "bailian":
        resp = await client.embeddings.create(
            model=settings.DASHSCOPE_MODEL,
            input=[text],
            dimensions=settings.DASHSCOPE_DIMENSIONS,
            encoding_format="float",
        )
    else:
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=[text],
        )
    return resp.data[0].embedding


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Compute embeddings for a batch of texts."""
    client = get_embedding_client()
    provider = settings.EMBEDDING_PROVIDER.lower()

    if provider == "bailian":
        resp = await client.embeddings.create(
            model=settings.DASHSCOPE_MODEL,
            input=texts,
            dimensions=settings.DASHSCOPE_DIMENSIONS,
            encoding_format="float",
        )
    else:
        resp = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )
    sorted_data = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in sorted_data]


async def get_embeddings_parallel(texts: list[str], batch_size: int = 0) -> list[list[float]]:
    """Split texts into batches and compute embeddings in parallel."""
    if batch_size <= 0:
        batch_size = settings.EMBEDDING_BATCH_SIZE

    if len(texts) <= batch_size:
        return await get_embeddings_batch(texts)

    batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
    results = await asyncio.gather(*[get_embeddings_batch(b) for b in batches])
    return [emb for batch_result in results for emb in batch_result]
