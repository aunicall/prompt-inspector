"""Generate attack payload variants via LLM and store them as new vector payloads."""

import json
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.services.llm_client import call_llm
from app.services.embedding_service import get_embeddings_parallel
from app.logger import logger

AUGMENT_SYSTEM_PROMPT = """You are a cybersecurity researcher generating adversarial prompt injection variants.

Given an attack payload and its categories, generate diverse variants that:
1. Preserve the same attack intent and categories
2. Use different phrasing, languages, encodings, or obfuscation techniques
3. Include both subtle and obvious variants

Respond in strict JSON array format (no markdown fences):
[
  {"text": "variant text here", "categories": ["cat1", "cat2"]},
  ...
]

Generate exactly 5 variants. Keep each variant under 500 characters."""


async def augment_attack_payload(
    original_text: str,
    categories: list[str],
    source_label: str = "llm_augment",
) -> int:
    """
    Generate variants of an attack payload and store them in vector_payloads.

    Returns:
        Number of successfully stored variants.
    """
    variants = await _generate_variants(original_text, categories)
    if not variants:
        return 0

    texts = [v["text"] for v in variants]
    try:
        embeddings = await get_embeddings_parallel(texts)
    except Exception as e:
        logger.error(f"Embedding failed during augmentation: {e}")
        return 0

    stored = 0
    async with async_session() as db:
        for variant, embedding in zip(variants, embeddings):
            try:
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                cats_json = json.dumps(variant["categories"])
                await db.execute(
                    text(
                        "INSERT INTO vector_payloads (id, categories, text, embedding, source, enabled) "
                        "VALUES (:id, CAST(:categories AS jsonb), :text, CAST(:embedding AS halfvec), :source, :enabled)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "categories": cats_json,
                        "text": variant["text"],
                        "embedding": embedding_str,
                        "source": source_label,
                        "enabled": True,
                    },
                )
                stored += 1
            except Exception as e:
                logger.warning(f"Failed to store augmented variant: {e}")
        await db.commit()

    if stored > 0:
        logger.info(f"Augmented {stored} variants for categories {categories}")
    return stored


async def _generate_variants(
    original_text: str,
    categories: list[str],
) -> Optional[list[dict]]:
    user_message = (
        f"Original attack payload:\n{original_text}\n\n"
        f"Categories: {', '.join(categories)}"
    )

    raw = await call_llm(
        provider=settings.LLM_AUGMENT_PROVIDER,
        model=settings.LLM_AUGMENT_MODEL,
        system_prompt=AUGMENT_SYSTEM_PROMPT,
        user_message=user_message,
        temperature=0.7,
        max_tokens=2048,
        think_level=settings.LLM_AUGMENT_THINK_LEVEL,
    )

    if not raw:
        return None

    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        result = []
        for item in data:
            if isinstance(item, dict) and "text" in item:
                cats = item.get("categories", categories)
                if isinstance(cats, str):
                    cats = [cats]
                result.append({"text": item["text"], "categories": cats})
        return result if result else None
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse augmentation response: {e}")
        return None
