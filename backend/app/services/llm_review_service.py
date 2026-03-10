"""LLM-based review for texts in the gray zone of vector detection."""

import json
from typing import Optional

from app.config import settings
from app.services.llm_client import call_llm
from app.logger import logger


async def llm_review(
    text: str,
    categories_info: str,
    vec_categories: list[str],
    vec_score: float,
) -> Optional[dict]:
    """
    Ask LLM to review whether the text is a genuine attack.

    Returns:
        dict with "is_attack" (bool), "category" (list[str]), "confidence" (float)
        or None on failure.
    """
    system_prompt = _build_system_prompt(categories_info, vec_categories, vec_score)

    raw = await call_llm(
        provider=settings.LLM_REVIEW_PROVIDER,
        model=settings.LLM_REVIEW_MODEL,
        system_prompt=system_prompt,
        user_message=text,
        temperature=0.1,
        max_tokens=512,
        think_level=settings.LLM_REVIEW_THINK_LEVEL,
    )

    if not raw:
        return None

    return _parse_llm_response(raw)


def _build_system_prompt(categories_info: str, vec_categories: list[str], vec_score: float) -> str:
    return f"""You are a cybersecurity expert specializing in prompt injection detection.

## Known threat categories
{categories_info}

## Context
Our vector-based detector flagged this text as suspicious:
- Matched categories: {', '.join(vec_categories)}
- Similarity score: {vec_score:.3f}

## Task
Analyze the text and determine if it's a genuine prompt injection attack.
Respond in **strict JSON** (no markdown fences):
{{"is_attack": true/false, "category": ["category_id", ...], "confidence": 0.0-1.0}}

Rules:
- Only use category IDs from the known threat categories above.
- If not an attack, return {{"is_attack": false, "category": [], "confidence": 0.0}}
- Be conservative: only flag clear attacks."""


def _parse_llm_response(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    raw = raw.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    try:
        data = json.loads(raw)
        is_attack = bool(data.get("is_attack", False))
        category = data.get("category", [])
        confidence = float(data.get("confidence", 0.0))
        if isinstance(category, str):
            category = [category]
        return {
            "is_attack": is_attack,
            "category": category if is_attack else [],
            "confidence": confidence,
        }
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM review response: {e}, raw={raw[:200]}")
        return None
