"""Async LLM client wrapper supporting DeepSeek, Qwen (DashScope), and Google GenAI."""

import os
from typing import Optional

from app.logger import logger


async def call_llm(
    provider: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    think_level: str = "LOW",
) -> Optional[str]:
    """Call LLM with the given prompts and return the text response."""
    try:
        if provider == "deepseek":
            return await _call_openai_compatible(
                base_url="https://api.deepseek.com/v1",
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                model=model,
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "qwen":
            return await _call_openai_compatible(
                base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                model=model,
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        elif provider == "genai":
            return await _call_google_genai(
                model=model,
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
                think_level=think_level,
            )
        else:
            logger.error(f"Unsupported LLM provider: {provider}")
            return None
    except Exception as e:
        logger.error(f"LLM call failed ({provider}/{model}): {e}")
        return None


async def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
) -> Optional[str]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content


async def _call_google_genai(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float,
    max_tokens: int,
    think_level: str = "LOW",
) -> Optional[str]:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_GENAI_API_KEY", "")
    client = genai.Client(api_key=api_key)

    thinking_config = None
    if think_level and think_level.upper() != "NONE":
        try:
            level_enum = getattr(types.ThinkingBudget, think_level.upper(), None)
            if level_enum:
                thinking_config = types.ThinkingConfig(thinking_budget=level_enum)
        except Exception:
            pass

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        max_output_tokens=max_tokens,
        thinking_config=thinking_config,
    )

    resp = await client.aio.models.generate_content(
        model=model,
        contents=user_message,
        config=config,
    )
    if resp.candidates and resp.candidates[0].content and resp.candidates[0].content.parts:
        for part in resp.candidates[0].content.parts:
            if part.text:
                return part.text
    return None
