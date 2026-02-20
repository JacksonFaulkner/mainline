from __future__ import annotations

import json
import re
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

import chess
from fastapi import HTTPException

from app.chess.schemas.api import (
    CommentaryAnalysisCompleteEvent,
    CommentaryAnalysisErrorEvent,
    CommentaryAnalysisStreamRequest,
    CommentaryStructuredCommentary,
    CommentaryTextDeltaEvent,
    CommentaryUsageStats,
)
from app.chess.schemas.review import BedrockContextLine, BedrockReviewPrompt
from app.chess.services.bedrock import (
    _build_runtime_client,
    _normalize_usage,
    converse_bedrock_review,
)
from app.core.config import settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _build_prompt(params: CommentaryAnalysisStreamRequest, board: chess.Board) -> BedrockReviewPrompt:
    side_to_move = "White" if board.turn == chess.WHITE else "Black"
    context_lines = [
        BedrockContextLine(label="FEN", value=params.fen),
        BedrockContextLine(label="Side to move", value=side_to_move),
    ]
    if params.stockfish_context:
        context_lines.append(
            BedrockContextLine(label="Stockfish context", value=params.stockfish_context)
        )

    return BedrockReviewPrompt(
        model_id=settings.BEDROCK_MODEL_ID,
        system_prompt=(
            "You are a chess UI assistant. Return exactly one JSON object and nothing else. "
            "No markdown, no code fences, no prose outside JSON. "
            "Keep all values concise and grounded in the provided position and Stockfish context."
        ),
        user_message=(
            "Return a JSON object with these fields only:\n"
            "{\n"
            '  "position_plan_title": "string, less than 5 words",\n'
            '  "advantage_side": "white|black|equal|unclear",\n'
            '  "advantage_summary": "string",\n'
            '  "best_move_san": "string",\n'
            '  "best_move_reason": "string",\n'
            '  "danger_to_watch": "string",\n'
            '  "white_plan": ["bullet 1", "bullet 2"],\n'
            '  "black_plan": ["bullet 1", "bullet 2"],\n'
            '  "concrete_ideas": [\n'
            "    {\n"
            '      "title": "string",\n'
            '      "description": "string",\n'
            '      "selected_line_id": "L01",\n'
            '      "playback_pv_uci": ["e2e4", "e7e5"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Requirements:\n"
            "- position_plan_title must be less than 5 words.\n"
            "- best_move_san must be SAN notation.\n"
            "- Use plain language and keep each string short.\n"
            "- white_plan and black_plan must contain exactly 2 bullets each.\n"
            "- concrete_ideas must contain 1 or 2 ideas.\n"
            "- selected_line_id must reference candidate lines from Stockfish context (Lxx format).\n"
            "- playback_pv_uci must be a legal UCI prefix from the selected candidate line.\n"
            "- Do not include any keys other than the keys above."
        ),
        context_lines=context_lines,
        max_output_tokens=min(settings.BEDROCK_MAX_OUTPUT_TOKENS, 320),
        temperature=settings.BEDROCK_TEMPERATURE,
    )


def _to_commentary_usage(raw_usage: Any) -> CommentaryUsageStats | None:
    normalized = _normalize_usage(raw_usage)
    if normalized is None:
        return None
    return CommentaryUsageStats(
        input_tokens=normalized.input_tokens,
        output_tokens=normalized.output_tokens,
        total_tokens=normalized.total_tokens,
    )


def _text_chunks(text: str, chunk_size: int = 36) -> Iterator[str]:
    clean = text.strip()
    if not clean:
        return
    for index in range(0, len(clean), chunk_size):
        yield clean[index : index + chunk_size]


def _extract_text_delta(delta: Any) -> str | None:
    if not isinstance(delta, dict):
        return None

    direct = delta.get("text")
    if isinstance(direct, str) and direct:
        return direct

    return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    if lines[-1].strip() != "```":
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _extract_json_object_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    depth = 0
    start_index: int | None = None
    in_string = False
    escape_next = False

    for index, char in enumerate(text):
        if in_string:
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            if depth == 0:
                start_index = index
            depth += 1
            continue
        if char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start_index is not None:
                candidate = text[start_index : index + 1].strip()
                if candidate:
                    candidates.append(candidate)
                start_index = None

    return candidates


def _normalize_json_candidate(text: str) -> str:
    candidate = text.strip().lstrip("\ufeff")
    if candidate.lower().startswith("json\n"):
        candidate = candidate.split("\n", 1)[1].strip()
    return candidate


def _repair_json_candidate(candidate: str) -> str:
    # Recover from common model mistakes like trailing commas before } or ].
    return re.sub(r",\s*([}\]])", r"\1", candidate)


def _parse_structured_commentary(raw_text: str) -> CommentaryStructuredCommentary | None:
    if not raw_text.strip():
        return None

    candidates: list[str] = []
    stripped = raw_text.strip()
    candidates.append(_normalize_json_candidate(stripped))
    fence_stripped = _normalize_json_candidate(_strip_code_fence(stripped))
    if fence_stripped and fence_stripped != stripped:
        candidates.append(fence_stripped)
    candidates.extend(_extract_json_object_candidates(stripped))
    if fence_stripped and fence_stripped != stripped:
        candidates.extend(_extract_json_object_candidates(fence_stripped))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized_candidate = _normalize_json_candidate(candidate)
        try:
            return CommentaryStructuredCommentary.model_validate_json(normalized_candidate)
        except Exception:
            pass

        repaired_candidate = _repair_json_candidate(normalized_candidate)
        if repaired_candidate != normalized_candidate:
            try:
                return CommentaryStructuredCommentary.model_validate_json(repaired_candidate)
            except Exception:
                pass

        try:
            parsed = json.loads(normalized_candidate)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(repaired_candidate)
            except json.JSONDecodeError:
                continue
        try:
            return CommentaryStructuredCommentary.model_validate(parsed)
        except Exception:
            continue
    return None


def _with_terminal_punctuation(text: str) -> str:
    clean = " ".join(text.split())
    if not clean:
        return clean
    if clean[-1] in ".!?":
        return clean
    return f"{clean}."


def _render_structured_commentary(structured: CommentaryStructuredCommentary) -> str:
    side = structured.advantage_side
    if side == "white":
        sentence_1 = f"White is better: {structured.advantage_summary}"
    elif side == "black":
        sentence_1 = f"Black is better: {structured.advantage_summary}"
    elif side == "equal":
        sentence_1 = f"The position is roughly equal: {structured.advantage_summary}"
    else:
        sentence_1 = f"The evaluation is unclear: {structured.advantage_summary}"

    sentence_2 = f"Best move is {structured.best_move_san} because {structured.best_move_reason}"
    sentence_3 = f"Main danger to watch is {structured.danger_to_watch}"

    return " ".join(
        [
            _with_terminal_punctuation(sentence_1),
            _with_terminal_punctuation(sentence_2),
            _with_terminal_punctuation(sentence_3),
        ]
    )


def _prepare_completion_text(raw_text: str) -> tuple[str, CommentaryStructuredCommentary | None]:
    clean_text = raw_text.strip()
    if not clean_text:
        return "", None
    structured = _parse_structured_commentary(clean_text)
    if structured is None:
        return clean_text, None
    return _render_structured_commentary(structured), structured


def _emit_fallback_completion(
    *,
    analysis_id: str,
    prompt: BedrockReviewPrompt,
    stop_event: threading.Event | None,
) -> Iterator[dict[str, Any]]:
    try:
        completion = converse_bedrock_review(prompt)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        message = detail.get("error") if isinstance(detail.get("error"), str) else "Commentary request failed."
        yield CommentaryAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="bedrock_request_failed",
            message=message,
            retryable=True,
            generated_at=_now_utc(),
        ).model_dump(mode="json")
        return

    rendered_text, structured = _prepare_completion_text(completion.text)
    full_text = ""
    for chunk in _text_chunks(rendered_text):
        if stop_event is not None and stop_event.is_set():
            break
        full_text += chunk
        yield CommentaryTextDeltaEvent(
            analysis_id=analysis_id,
            text_delta=chunk,
            text=full_text,
            generated_at=_now_utc(),
        ).model_dump(mode="json")

    if not full_text.strip():
        yield CommentaryAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="empty_completion",
            message="Commentary returned no text content.",
            retryable=True,
            generated_at=_now_utc(),
        ).model_dump(mode="json")
        return

    usage = None
    if completion.usage is not None:
        usage = CommentaryUsageStats(
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
            total_tokens=completion.usage.total_tokens,
        )

    yield CommentaryAnalysisCompleteEvent(
        analysis_id=analysis_id,
        text=full_text,
        structured=structured,
        stop_reason=completion.stop_reason,
        usage=usage,
        latency_ms=completion.latency_ms,
        generated_at=_now_utc(),
    ).model_dump(mode="json")


def stream_commentary_analysis(
    params: CommentaryAnalysisStreamRequest,
    stop_event: threading.Event | None = None,
) -> Iterator[dict[str, Any]]:
    analysis_id = f"commentary-{uuid.uuid4().hex[:12]}"
    try:
        board = chess.Board(params.fen)
    except ValueError as exc:
        yield CommentaryAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="invalid_fen",
            message=str(exc),
            retryable=False,
            generated_at=_now_utc(),
        ).model_dump(mode="json")
        return

    prompt = _build_prompt(params, board)

    try:
        client, client_error_type, no_credentials_type = _build_runtime_client()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
        message = detail.get("error") if isinstance(detail.get("error"), str) else "Failed to initialize Bedrock runtime client."
        yield CommentaryAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="bedrock_init_failed",
            message=message,
            retryable=True,
            generated_at=_now_utc(),
        ).model_dump(mode="json")
        return

    converse_stream = client.converse_stream if hasattr(client, "converse_stream") else None
    if callable(converse_stream):
        full_text = ""
        stop_reason: str | None = None
        usage: CommentaryUsageStats | None = None
        latency_ms: int | None = None
        try:
            response = converse_stream(
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
            stream = response.get("stream")
            if stream is None or not hasattr(stream, "__iter__"):
                raise RuntimeError("Bedrock stream payload missing stream iterator.")

            for event in stream:
                if stop_event is not None and stop_event.is_set():
                    stop_reason = "client_cancelled"
                    break
                if not isinstance(event, dict):
                    continue

                delta_block = event.get("contentBlockDelta")
                if isinstance(delta_block, dict):
                    delta = delta_block.get("delta")
                    text_delta = _extract_text_delta(delta)
                    if isinstance(text_delta, str) and text_delta:
                        full_text += text_delta

                message_stop = event.get("messageStop")
                if isinstance(message_stop, dict):
                    raw_stop_reason = message_stop.get("stopReason")
                    if isinstance(raw_stop_reason, str) and raw_stop_reason.strip():
                        stop_reason = raw_stop_reason

                metadata = event.get("metadata")
                if isinstance(metadata, dict):
                    usage = _to_commentary_usage(metadata.get("usage"))
                    metrics = metadata.get("metrics")
                    if isinstance(metrics, dict) and isinstance(metrics.get("latencyMs"), int):
                        latency_ms = metrics.get("latencyMs")
        except no_credentials_type:
            yield CommentaryAnalysisErrorEvent(
                analysis_id=analysis_id,
                code="bedrock_no_credentials",
                message="No AWS credentials found for Bedrock. Configure default AWS credentials and region.",
                retryable=True,
                generated_at=_now_utc(),
            ).model_dump(mode="json")
            return
        except client_error_type as exc:
            error_payload = exc.response.get("Error", {}) if isinstance(getattr(exc, "response", None), dict) else {}
            code = error_payload.get("Code", "ClientError")
            message = error_payload.get("Message", str(exc))
            yield CommentaryAnalysisErrorEvent(
                analysis_id=analysis_id,
                code="bedrock_request_failed",
                message=f"Bedrock request failed ({code}): {message}",
                retryable=True,
                generated_at=_now_utc(),
            ).model_dump(mode="json")
            return
        except Exception as exc:
            yield CommentaryAnalysisErrorEvent(
                analysis_id=analysis_id,
                code="stream_failed",
                message=f"Bedrock stream failed: {exc}",
                retryable=True,
                generated_at=_now_utc(),
            ).model_dump(mode="json")
            return

        if not full_text.strip():
            yield from _emit_fallback_completion(
                analysis_id=analysis_id,
                prompt=prompt,
                stop_event=stop_event,
            )
            return

        rendered_text, structured = _prepare_completion_text(full_text)
        streamed_text = ""
        for chunk in _text_chunks(rendered_text):
            if stop_event is not None and stop_event.is_set():
                break
            streamed_text += chunk
            yield CommentaryTextDeltaEvent(
                analysis_id=analysis_id,
                text_delta=chunk,
                text=streamed_text,
                generated_at=_now_utc(),
            ).model_dump(mode="json")

        yield CommentaryAnalysisCompleteEvent(
            analysis_id=analysis_id,
            text=streamed_text,
            structured=structured,
            stop_reason=stop_reason,
            usage=usage,
            latency_ms=latency_ms,
            generated_at=_now_utc(),
        ).model_dump(mode="json")
        return

    yield from _emit_fallback_completion(
        analysis_id=analysis_id,
        prompt=prompt,
        stop_event=stop_event,
    )
