from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.chess.schemas.review import (
    BedrockCompletion,
    BedrockReviewPrompt,
    BedrockUsageStats,
)
from app.core.config import settings

_BEDROCK_RUNTIME_SERVICE = "bedrock-runtime"


def _import_bedrock_modules() -> tuple[Any, Any, Any, Any, Any]:
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Bedrock runtime dependencies are unavailable. Install boto3/botocore in the backend environment."
            },
        ) from exc
    return boto3, Config, ClientError, NoCredentialsError, NoRegionError


def _build_runtime_client() -> tuple[Any, Any, Any]:
    boto3, config_type, client_error_type, no_credentials_type, no_region_type = _import_bedrock_modules()
    region = settings.BEDROCK_REGION.strip() if isinstance(settings.BEDROCK_REGION, str) else ""
    client_kwargs: dict[str, Any] = {
        "config": config_type(
            connect_timeout=settings.BEDROCK_CONNECT_TIMEOUT_SEC,
            read_timeout=settings.BEDROCK_READ_TIMEOUT_SEC,
            retries={"max_attempts": 2, "mode": "standard"},
        )
    }
    if region:
        client_kwargs["region_name"] = region
    try:
        client = boto3.client(_BEDROCK_RUNTIME_SERVICE, **client_kwargs)
    except no_region_type as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "No AWS region configured for Bedrock. Set BEDROCK_REGION (for example: us-east-1)."},
        ) from exc
    return client, client_error_type, no_credentials_type


def _normalize_usage(raw_usage: Any) -> BedrockUsageStats | None:
    if not isinstance(raw_usage, dict):
        return None

    def _int_or_none(value: Any) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None

    usage = BedrockUsageStats(
        input_tokens=_int_or_none(raw_usage.get("inputTokens")),
        output_tokens=_int_or_none(raw_usage.get("outputTokens")),
        total_tokens=_int_or_none(raw_usage.get("totalTokens")),
    )
    if usage.input_tokens is None and usage.output_tokens is None and usage.total_tokens is None:
        return None
    return usage


def _extract_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if not isinstance(output, dict):
        raise HTTPException(status_code=502, detail={"error": "Bedrock response missing output field."})

    message = output.get("message")
    if not isinstance(message, dict):
        raise HTTPException(status_code=502, detail={"error": "Bedrock response missing output.message field."})

    content = message.get("content")
    if not isinstance(content, list):
        raise HTTPException(status_code=502, detail={"error": "Bedrock response missing output.message.content field."})

    chunks: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())

    if not chunks:
        raise HTTPException(status_code=502, detail={"error": "Bedrock returned no text content."})
    return "\n".join(chunks)


def converse_bedrock_review(prompt: BedrockReviewPrompt) -> BedrockCompletion:
    client, client_error_type, no_credentials_type = _build_runtime_client()
    try:
        response = client.converse(
            modelId=prompt.model_id,
            system=[{"text": prompt.system_prompt}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt.rendered_user_message()}],
                }
            ],
            inferenceConfig={
                "maxTokens": prompt.max_output_tokens,
                "temperature": prompt.temperature,
            },
        )
    except no_credentials_type as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "No AWS credentials found for Bedrock. Configure default AWS credentials and region."},
        ) from exc
    except client_error_type as exc:
        error_payload = exc.response.get("Error", {}) if isinstance(getattr(exc, "response", None), dict) else {}
        code = error_payload.get("Code", "ClientError")
        message = error_payload.get("Message", str(exc))
        raise HTTPException(
            status_code=502,
            detail={"error": f"Bedrock request failed ({code}): {message}"},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"error": f"Bedrock request failed: {exc}"},
        ) from exc

    if not isinstance(response, dict):
        raise HTTPException(status_code=502, detail={"error": "Unexpected Bedrock response payload."})

    text = _extract_text(response)
    metrics = response.get("metrics")
    latency_ms = metrics.get("latencyMs") if isinstance(metrics, dict) and isinstance(metrics.get("latencyMs"), int) else None

    stop_reason_raw = response.get("stopReason")
    stop_reason = stop_reason_raw if isinstance(stop_reason_raw, str) and stop_reason_raw.strip() else None

    return BedrockCompletion(
        model_id=prompt.model_id,
        text=text,
        stop_reason=stop_reason,
        usage=_normalize_usage(response.get("usage")),
        latency_ms=latency_ms,
    )
