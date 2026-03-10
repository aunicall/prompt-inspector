"""Detection request/response schemas."""

from typing import Optional
from pydantic import BaseModel, Field


class DetectionRequest(BaseModel):
    """Detection request: input text to analyze."""
    input_text: str = Field(..., min_length=1, description="Text content to detect")


class DetectionResult(BaseModel):
    """Single detection result."""
    category: list[str] = Field(default_factory=list, description="Detected threat categories")
    score: Optional[float] = Field(default=None, description="Threat score (0-1), null if safe")
    is_safe: bool = Field(..., description="Whether the input is safe")


class DetectionResponse(BaseModel):
    """Detection API response."""
    request_id: str
    result: DetectionResult
    latency_ms: int
