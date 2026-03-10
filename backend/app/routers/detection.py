"""Detection API router with fixed API Key authentication."""

from fastapi import APIRouter, HTTPException, Header, BackgroundTasks, status

from app.config import settings
from app.schemas.detection import DetectionRequest, DetectionResponse
from app.services.detection import detect
from app.logger import logger

router = APIRouter(prefix="/api/v1", tags=["detection"])


def _verify_api_key(x_api_key: str | None = Header(None, alias="X-API-Key")) -> str:
    """Verify fixed API Key from request header."""
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key. Provide X-API-Key header.",
        )
    return x_api_key


@router.post("/detect", response_model=DetectionResponse)
async def detect_endpoint(
    req: DetectionRequest,
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
):
    """
    Detect prompt injection threats in the given text.

    Requires `X-API-Key` header for authentication.
    """
    _verify_api_key(x_api_key)

    input_text = req.input_text.strip()
    if not input_text:
        raise HTTPException(status_code=400, detail="input_text must not be empty")

    if len(input_text) > settings.MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Input text exceeds maximum length ({settings.MAX_TEXT_LENGTH} chars)",
        )

    result = await detect(input_text, background_tasks=background_tasks)

    logger.info(
        f"Detection: safe={result['result'].get('is_safe', True)}, "
        f"score={result['result'].get('score')}, "
        f"latency={result['latency_ms']}ms"
    )

    return result
