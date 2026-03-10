"""
Multi-layer prompt injection detection engine.

Layer 1: Global hash cache (Redis SHA-256)         — < 2ms
Layer 2: Built-in sensitive word matching (AC automaton) — < 1ms
Layer 3: Semantic vector search (Embedding + pgvector)   — 30-60ms
Layer 4: LLM review (gray zone)                         — optional
Layer 5: Arbitration & response assembly                 — < 1ms

Score ranges (0~1 float):
  score >= VEC_SIM_HIGH  → confirmed threat
  VEC_SIM_LOW < score < VEC_SIM_HIGH → LLM review
  score <= VEC_SIM_LOW   → safe
"""

import re
import time
import asyncio
import ahocorasick
from typing import Optional

from fastapi import BackgroundTasks
from cachetools import TTLCache
from sqlalchemy import text as sql_text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.logger import logger
from app.models.claw_sensitive_word import ClawSensitiveWord
from app.models.category_config import CategoryConfig
from app.services.redis_service import (
    get_detection_cache,
    set_detection_cache,
    get_sensitive_words_from_cache,
    load_sensitive_words_to_cache,
)
from app.services.embedding_service import get_embeddings_parallel

SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Local TTL cache for category → severity mapping (5 min)
_category_severity_cache: TTLCache = TTLCache(maxsize=1, ttl=300)
_CATEGORY_SEVERITY_KEY = "global"

# Local cache for sensitive word matchers
_sw_cache: Optional[tuple[ahocorasick.Automaton, list[str], list[tuple[str, re.Pattern]]]] = None


def _slice_long_text(text: str) -> list[str]:
    """Sliding window text chunking with overlap."""
    chunk_size = settings.TEXT_CHUNK_SIZE
    overlap = settings.TEXT_CHUNK_OVERLAP

    if overlap >= chunk_size:
        raise ValueError(f"TEXT_CHUNK_OVERLAP ({overlap}) must be < TEXT_CHUNK_SIZE ({chunk_size})")

    if len(text) <= chunk_size:
        return [text]

    slices = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end > len(text):
            start = max(0, len(text) - chunk_size)
            slices.append(text[start:])
            break
        slices.append(text[start:end])
        start += (chunk_size - overlap)
    return slices


def _build_ac_automaton(words: list[str]) -> ahocorasick.Automaton:
    """Build Aho-Corasick automaton from lowercased words."""
    A = ahocorasick.Automaton()
    for word in words:
        A.add_word(word.lower(), word)
    if words:
        A.make_automaton()
    return A


def _compile_patterns(patterns: list[str]) -> list[tuple[str, re.Pattern]]:
    """Compile regex patterns, skip invalid ones."""
    compiled = []
    for p in patterns:
        try:
            compiled.append((p, re.compile(p, re.IGNORECASE)))
        except re.error:
            logger.warning(f"Invalid regex pattern ignored: {p}")
    return compiled


def invalidate_local_sw_cache() -> None:
    """Clear local sensitive word matcher cache."""
    global _sw_cache
    _sw_cache = None


async def _get_sensitive_word_matchers() -> tuple[ahocorasick.Automaton, list[str], list[tuple[str, re.Pattern]]]:
    """
    Load sensitive word matchers from local cache → Redis → DB.
    Returns (ac_automaton, literal_words, compiled_patterns).
    """
    global _sw_cache
    if _sw_cache is not None:
        return _sw_cache

    cached_words = await get_sensitive_words_from_cache()
    if cached_words is None:
        async with async_session() as db:
            result = await db.execute(select(ClawSensitiveWord))
            db_words = result.scalars().all()
            cached_words = [{"word": w.word, "match_type": w.match_type or "literal"} for w in db_words]
            await load_sensitive_words_to_cache(cached_words)

    literal_words = [w["word"] for w in cached_words if w.get("match_type", "literal") == "literal"]
    pattern_words = [w["word"] for w in cached_words if w.get("match_type") == "pattern"]

    automaton = _build_ac_automaton(literal_words)
    compiled_patterns = _compile_patterns(pattern_words)

    _sw_cache = (automaton, literal_words, compiled_patterns)
    return automaton, literal_words, compiled_patterns


async def _match_sensitive_words(text: str) -> list[dict]:
    """Layer 2: Built-in sensitive word hard matching (AC automaton + regex)."""
    automaton, literal_words, compiled_patterns = await _get_sensitive_word_matchers()
    if not literal_words and not compiled_patterns:
        return []

    hits: list[dict] = []
    seen: set[str] = set()
    text_lower = text.lower()

    if literal_words:
        for _, word in automaton.iter(text_lower):
            if word not in seen:
                seen.add(word)
                hits.append({
                    "category": "custom_sensitive_word",
                    "severity": "critical",
                    "score": 1.0,
                    "word": word,
                })

    for pattern_str, compiled in compiled_patterns:
        if pattern_str not in seen and compiled.search(text):
            seen.add(pattern_str)
            hits.append({
                "category": "custom_sensitive_word",
                "severity": "critical",
                "score": 1.0,
                "word": pattern_str,
            })

    return hits


async def _load_category_severity_map() -> dict[str, str]:
    """Load global category → severity mapping with local TTL cache."""
    if _CATEGORY_SEVERITY_KEY in _category_severity_cache:
        return _category_severity_cache[_CATEGORY_SEVERITY_KEY]

    async with async_session() as db:
        result = await db.execute(
            select(CategoryConfig.category, CategoryConfig.severity)
            .where(CategoryConfig.enabled == True)
        )
        severity_map = {row[0]: row[1] for row in result.all()}

    _category_severity_cache[_CATEGORY_SEVERITY_KEY] = severity_map
    return severity_map


async def _get_enabled_categories() -> set[str]:
    """Get all enabled category IDs."""
    severity_map = await _load_category_severity_map()
    return set(severity_map.keys())


async def _get_category_info_text() -> str:
    """Build category info text for LLM review prompt."""
    from app.services.redis_service import get_cached_category_content, set_cached_category_content

    cached = await get_cached_category_content()
    if cached:
        return cached

    async with async_session() as db:
        result = await db.execute(
            select(CategoryConfig).where(CategoryConfig.enabled == True)
        )
        configs = result.scalars().all()

    lines = []
    for c in configs:
        lines.append(f"- {c.category}: {c.name} ({c.domain}) — {c.description or 'N/A'}")
    content = "\n".join(lines)
    await set_cached_category_content(content)
    return content


async def _search_single_slice(
    slice_idx: int,
    slice_text: str,
    emb: list[float],
    allowed_cats: list[str],
    enabled_categories: set[str],
    category_severity_map: dict[str, str],
    score_threshold: float,
) -> list[dict]:
    """Vector search for a single text slice using an independent session."""
    emb_str = "[" + ",".join(str(v) for v in emb) + "]"
    hits: list[dict] = []

    try:
        async with async_session() as db:
            await db.execute(sql_text(f"SET LOCAL hnsw.ef_search = {settings.VECTOR_HNSW_EF_SEARCH}"))

            limit = 20 if settings.DEBUG_MODE else 5

            result = await db.execute(
                sql_text(
                    "SELECT vp.id, vp.text, vp.categories, vp.enabled, "
                    "1 - (vp.embedding <=> CAST(:emb AS halfvec)) AS similarity "
                    "FROM vector_payloads vp "
                    "WHERE vp.categories ?| CAST(:allowed_cats AS text[]) "
                    "ORDER BY vp.embedding <=> CAST(:emb AS halfvec) LIMIT :limit"
                ),
                {"emb": emb_str, "allowed_cats": allowed_cats, "limit": limit},
            )
            rows = result.fetchall()

            if settings.DEBUG_MODE:
                logger.info(f"[DEBUG] Slice #{slice_idx}: top results")
                for rank, row in enumerate(rows[:3], 1):
                    logger.info(f"  Top-{rank}: sim={row.similarity:.4f}, cats={row.categories}")

            for row in rows:
                if row.similarity < score_threshold or not row.enabled:
                    continue

                hit_cats = [c for c in row.categories if c in enabled_categories]
                if not hit_cats:
                    continue

                best_sev = max(
                    hit_cats,
                    key=lambda c: SEVERITY_RANK.get(category_severity_map.get(c, "medium"), 1)
                )
                severity = category_severity_map.get(best_sev, "medium")
                score = round(row.similarity, 4)

                hits.append({
                    "categories": hit_cats,
                    "severity": severity,
                    "score": score,
                })
    except Exception as e:
        logger.warning(f"Vector search slice #{slice_idx} failed: {e}")

    return hits


async def _vector_search(
    text_slices: list[str],
    enabled_categories: set[str],
    category_severity_map: dict[str, str],
    score_threshold: float,
) -> list[dict]:
    """Layer 3: Semantic vector search with parallel slice processing."""
    if not enabled_categories:
        return []

    t0 = time.perf_counter()
    try:
        embeddings = await get_embeddings_parallel(text_slices)
    except Exception as e:
        logger.warning(f"Embedding service failed, skipping vector detection: {e}")
        return []
    embedding_ms = int((time.perf_counter() - t0) * 1000)

    allowed_cats = list(enabled_categories)

    t1 = time.perf_counter()
    tasks = [
        _search_single_slice(
            slice_idx=idx,
            slice_text=text_slices[idx - 1],
            emb=emb,
            allowed_cats=allowed_cats,
            enabled_categories=enabled_categories,
            category_severity_map=category_severity_map,
            score_threshold=score_threshold,
        )
        for idx, emb in enumerate(embeddings, 1)
    ]
    slice_results = await asyncio.gather(*tasks)

    raw_hits: list[dict] = []
    for hits in slice_results:
        raw_hits.extend(hits)

    vector_ms = int((time.perf_counter() - t1) * 1000)
    logger.debug(f"Vector search: embedding={embedding_ms}ms, search={vector_ms}ms, hits={len(raw_hits)}")
    return raw_hits


async def _augment_attack_payload(input_text: str, categories: list[str]) -> None:
    """Background task: generate attack variants and store in vector_payloads."""
    from app.services.payload_augment_service import augment_attack_payload
    try:
        await augment_attack_payload(input_text, categories)
    except Exception as e:
        logger.warning(f"Failed to augment attack payload: {e}")


async def detect(
    text: str,
    *,
    background_tasks: Optional[BackgroundTasks] = None,
) -> dict:
    """
    Multi-layer prompt injection detection.

    Returns: {"request_id": "...", "result": {"category": [...], "score": N|null, "is_safe": bool}, "latency_ms": N}
    """
    import uuid as _uuid

    start_time = time.perf_counter()
    db_search_threshold = settings.VEC_SIM_LOW

    # Layer 1: Global hash cache
    cached_result = await get_detection_cache(text)
    if cached_result is not None:
        cached_result["request_id"] = str(_uuid.uuid4())
        cached_result["latency_ms"] = int((time.perf_counter() - start_time) * 1000)
        return cached_result

    # Parallel: load category config + sensitive word matching
    enabled_categories_task = _get_enabled_categories()
    category_severity_map_task = _load_category_severity_map()
    sensitive_hits_task = _match_sensitive_words(text)

    enabled_categories, category_severity_map, sensitive_hits = await asyncio.gather(
        enabled_categories_task,
        category_severity_map_task,
        sensitive_hits_task,
    )

    # Layer 2: Sensitive word short-circuit
    if sensitive_hits:
        sw_score_map: dict[str, float] = {}
        for hit in sensitive_hits:
            cat = hit["category"]
            sc = hit["score"]
            if cat not in sw_score_map or sc > sw_score_map[cat]:
                sw_score_map[cat] = sc

        sw_best_score = max(sw_score_map.values()) if sw_score_map else 1.0
        sw_best_cats = sorted([c for c, s in sw_score_map.items() if s == sw_best_score])

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        result = {
            "request_id": str(_uuid.uuid4()),
            "result": {"category": sw_best_cats, "score": sw_best_score, "is_safe": False},
            "latency_ms": elapsed_ms,
        }
        await set_detection_cache(text, result)
        return result

    # Layer 3: Semantic vector search
    text_slices = _slice_long_text(text)
    vector_hits = await _vector_search(text_slices, enabled_categories, category_severity_map, db_search_threshold)

    # Layer 4: Arbitration — select highest scoring match
    score_map: dict[str, float] = {}
    for hit in vector_hits:
        hit_score = hit["score"]
        for cat in hit["categories"]:
            if cat not in score_map or hit_score > score_map[cat]:
                score_map[cat] = hit_score

    best_score: Optional[float] = max(score_map.values()) if score_map else None
    best_categories: list[str] = sorted([c for c, s in score_map.items() if s == best_score]) if best_score else []

    # Layer 5: LLM review for gray zone
    final_result: dict

    if best_score is not None and settings.VEC_SIM_LOW < best_score < settings.VEC_SIM_HIGH:
        from app.services.llm_review_service import llm_review
        categories_info = await _get_category_info_text()

        llm_result = await llm_review(
            text=text,
            categories_info=categories_info,
            vec_categories=best_categories,
            vec_score=best_score,
        )

        if llm_result is not None:
            llm_cats = llm_result.get("category", [])
            llm_conf = llm_result.get("confidence", 0.0)
            is_attack = llm_result.get("is_attack", False)

            if is_attack and llm_cats:
                final_result = {"category": llm_cats, "score": llm_conf, "is_safe": False}
                if llm_conf > settings.SUSPICIOUS_TEXT_TH:
                    if background_tasks is not None:
                        background_tasks.add_task(_augment_attack_payload, text, llm_cats)
                    else:
                        asyncio.create_task(_augment_attack_payload(text, llm_cats))
            else:
                final_result = {"category": [], "score": None, "is_safe": True}
        else:
            final_result = {"category": best_categories, "score": best_score, "is_safe": False}
    elif best_score is not None and best_score >= settings.VEC_SIM_HIGH:
        final_result = {"category": best_categories, "score": best_score, "is_safe": False}
    else:
        final_result = {"category": [], "score": None, "is_safe": True}

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    result = {
        "request_id": str(_uuid.uuid4()),
        "result": final_result,
        "latency_ms": elapsed_ms,
    }

    await set_detection_cache(text, result)
    return result
