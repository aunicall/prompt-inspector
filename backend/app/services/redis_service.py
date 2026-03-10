"""Redis service: detection result cache + sensitive word cache."""

import json
import hashlib
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.logger import logger

_redis: Optional[aioredis.Redis] = None


async def init_redis() -> aioredis.Redis:
    """Initialize Redis connection and flush detection cache."""
    global _redis
    _redis = aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        max_connections=20,
    )
    await _redis.ping()
    logger.info("Redis connected successfully")
    await flush_detection_cache()
    return _redis


async def close_redis():
    """Close Redis connection."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialized, call init_redis() first")
    return _redis


# ======================== Detection cache ========================

def _make_detection_cache_key(text: str) -> str:
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{settings.REDIS_DETECTION_CACHE_PREFIX}{text_hash}"


async def get_detection_cache(text: str) -> Optional[dict]:
    """Lookup detection result cache, refresh TTL on hit."""
    r = get_redis()
    key = _make_detection_cache_key(text)
    cached = await r.get(key)
    if cached is not None:
        await r.expire(key, settings.REDIS_DETECTION_CACHE_TTL)
        return json.loads(cached)
    return None


async def set_detection_cache(text: str, result: dict):
    """Store detection result in cache."""
    r = get_redis()
    key = _make_detection_cache_key(text)
    await r.set(key, json.dumps(result, ensure_ascii=False), ex=settings.REDIS_DETECTION_CACHE_TTL)


async def flush_detection_cache():
    """Flush all detection cache entries by prefix scan."""
    r = get_redis()
    prefix = settings.REDIS_DETECTION_CACHE_PREFIX
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = await r.scan(cursor, match=f"{prefix}*", count=500)
        if keys:
            await r.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    if deleted > 0:
        logger.info(f"Flushed {deleted} detection cache entries")


# ======================== Sensitive word cache ========================

_SW_CACHE_KEY = "pi:sw:global"


async def load_sensitive_words_to_cache(words: list[dict]):
    """Load all sensitive words into Redis set."""
    r = get_redis()
    await r.delete(_SW_CACHE_KEY)
    if words:
        members = [json.dumps(w, ensure_ascii=False) for w in words]
        await r.sadd(_SW_CACHE_KEY, *members)


async def get_sensitive_words_from_cache() -> Optional[list[dict]]:
    """Get sensitive words from Redis. Returns None if cache miss."""
    r = get_redis()
    exists = await r.exists(_SW_CACHE_KEY)
    if not exists:
        return None
    members = await r.smembers(_SW_CACHE_KEY)
    return [json.loads(m) for m in members]


async def invalidate_sensitive_words_cache():
    """Invalidate the sensitive words cache."""
    r = get_redis()
    await r.delete(_SW_CACHE_KEY)


# ======================== Category config cache ========================

_CATEGORY_CONFIGS_KEY = "pi:category_configs_content"


async def get_cached_category_content() -> Optional[str]:
    r = get_redis()
    return await r.get(_CATEGORY_CONFIGS_KEY)


async def set_cached_category_content(content: str):
    r = get_redis()
    await r.set(_CATEGORY_CONFIGS_KEY, content, ex=3600)
