/**
 * Backend API client with API Key authentication.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DetectionResult {
  category: string[];
  score: number | null;
  is_safe: boolean;
}

export interface DetectionResponse {
  request_id: string;
  result: DetectionResult;
  latency_ms: number;
}

/**
 * Call the detection API with the given text and API Key.
 */
export async function detectText(
  inputText: string,
  apiKey: string
): Promise<DetectionResponse> {
  const res = await fetch(`${API_BASE}/api/v1/detect`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": apiKey,
    },
    body: JSON.stringify({ input_text: inputText }),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Request failed" }));
    const err: any = new Error(error.detail || `HTTP ${res.status}`);
    err.response = { status: res.status };
    throw err;
  }

  return res.json();
}

/**
 * Health check endpoint.
 */
export async function healthCheck(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}
