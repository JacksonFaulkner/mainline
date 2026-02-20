from __future__ import annotations

import asyncio
import logging
import re
import threading
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from typing import Any, Literal

import chess
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import ValidationError

from app.api.deps import CurrentUser, SessionDep
from app.chess.schemas.api import (
    UCI_MOVE_PATTERN,
    AccountInfo,
    ApiError,
    ApiMessage,
    ChallengeActionResponse,
    ChallengeDeclineRequest,
    CommentaryAnalysisStreamRequest,
    MoveRequest,
    MoveResponse,
    OpeningLookupRequest,
    OpeningLookupResponse,
    PositionSnapshotRequest,
    PositionSnapshotResponse,
    RecentGamesResponse,
    RecentGameSummary,
    SeekRequest,
    SeekResponse,
    StockfishStreamRequest,
)
from app.chess.schemas.review import (
    BedrockReviewResponse,
    GameReview,
    build_bedrock_review_prompt,
    render_game_review_models_html,
    sample_game_review,
)
from app.chess.services.analysis_stream import stream_stockfish_analysis
from app.chess.services.bedrock import converse_bedrock_review
from app.chess.services.commentary_analysis_stream import stream_commentary_analysis
from app.chess.services.lichess import get_client, to_http_exception
from app.chess.services.openings import lookup_opening as resolve_opening
from app.chess.services.persistence import (
    load_game_review,
    save_position_snapshot,
    upsert_game_review,
)
from app.chess.services.review_service import generate_game_review
from app.chess.services.streaming import iter_sse
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chess", tags=["chess"])
_position_persistence_warning_logged = False
_HISTORY_PREVIEW_PLIES = 6


def _client():
    return get_client()


def _timestamp_from_ms(value: Any) -> datetime | None:
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return None


def _player_name(player: dict[str, Any] | None) -> str | None:
    if not isinstance(player, dict):
        return None
    user = player.get("user")
    if isinstance(user, dict):
        name = user.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    name = player.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def _player_rating(player: dict[str, Any] | None) -> int | None:
    if not isinstance(player, dict):
        return None
    rating = player.get("rating")
    return rating if isinstance(rating, int) else None


def _variant_key(variant_payload: Any) -> str | None:
    if isinstance(variant_payload, str):
        return variant_payload
    if isinstance(variant_payload, dict):
        key = variant_payload.get("key")
        if isinstance(key, str):
            return key
    return None


def _normalize_uci_moves(raw_moves: Any) -> list[str]:
    if not isinstance(raw_moves, str):
        return []
    tokens = [token.strip().lower() for token in raw_moves.split() if token.strip()]
    if any(re.match(UCI_MOVE_PATTERN, token) is None for token in tokens):
        return []
    return tokens


def _build_recent_preview(game: dict[str, Any], variant: str | None) -> tuple[list[str], list[str]]:
    moves_uci = _normalize_uci_moves(game.get("moves"))
    if not moves_uci:
        return [], []

    chess960 = variant == "chess960"
    initial_fen_raw = game.get("initialFen")
    initial_fen = (
        initial_fen_raw.strip()
        if isinstance(initial_fen_raw, str) and initial_fen_raw.strip() and initial_fen_raw.strip() != "startpos"
        else chess.STARTING_FEN
    )

    try:
        board = chess.Board(initial_fen, chess960=chess960)
    except ValueError:
        board = chess.Board()
        initial_fen = chess.STARTING_FEN

    legal_moves: list[chess.Move] = []
    sans: list[str] = []
    for uci in moves_uci:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if not board.is_legal(move):
            break
        sans.append(board.san(move))
        legal_moves.append(move)
        board.push(move)

    if not legal_moves:
        return [], []

    preview_count = min(_HISTORY_PREVIEW_PLIES, len(legal_moves))
    start_index = len(legal_moves) - preview_count

    try:
        preview_board = chess.Board(initial_fen, chess960=chess960)
    except ValueError:
        preview_board = chess.Board()
    for move in legal_moves[:start_index]:
        preview_board.push(move)

    preview_fens = [preview_board.fen()]
    preview_sans: list[str] = []
    for index in range(start_index, len(legal_moves)):
        move = legal_moves[index]
        preview_sans.append(sans[index])
        preview_board.push(move)
        preview_fens.append(preview_board.fen())

    return preview_fens, preview_sans


def _summarize_recent_game(game: dict[str, Any], my_username_lower: str) -> RecentGameSummary | None:
    game_id = game.get("id")
    if not isinstance(game_id, str) or not game_id:
        return None

    players = game.get("players") if isinstance(game.get("players"), dict) else {}
    white = players.get("white") if isinstance(players, dict) else None
    black = players.get("black") if isinstance(players, dict) else None
    white_name = _player_name(white)
    black_name = _player_name(black)

    my_color: str | None = None
    opponent: dict[str, Any] | None = None
    if white_name and white_name.lower() == my_username_lower:
        my_color = "white"
        opponent = black if isinstance(black, dict) else None
    elif black_name and black_name.lower() == my_username_lower:
        my_color = "black"
        opponent = white if isinstance(white, dict) else None

    winner = game.get("winner") if isinstance(game.get("winner"), str) else None
    if winner not in {"white", "black"}:
        winner = None

    my_result: str = "unknown"
    if my_color and winner:
        my_result = "win" if winner == my_color else "loss"
    elif winner is None:
        status = game.get("status")
        if isinstance(status, str) and status.lower() in {"draw", "stalemate", "repetition"}:
            my_result = "draw"

    variant = _variant_key(game.get("variant"))
    preview_fens, preview_sans = _build_recent_preview(game, variant)

    summary_payload = {
        "game_id": game_id,
        "url": f"https://lichess.org/{game_id}",
        "my_color": my_color,
        "my_result": my_result,
        "opponent_name": _player_name(opponent),
        "opponent_rating": _player_rating(opponent),
        "rated": game.get("rated") if isinstance(game.get("rated"), bool) else None,
        "speed": game.get("speed") if isinstance(game.get("speed"), str) else None,
        "perf": game.get("perf") if isinstance(game.get("perf"), str) else None,
        "variant": variant,
        "status": game.get("status") if isinstance(game.get("status"), str) else None,
        "winner": winner,
        "created_at": _timestamp_from_ms(game.get("createdAt")),
        "last_move_at": _timestamp_from_ms(game.get("lastMoveAt")),
        "preview_fens": preview_fens,
        "preview_sans": preview_sans,
    }
    if winner:
        logger.info(
            "Resolved game winner game_id=%s winner=%s my_color=%s my_result=%s",
            game_id,
            winner,
            my_color,
            my_result,
        )
    return RecentGameSummary.model_validate(summary_payload)


def _seek_worker(payload: SeekRequest) -> None:
    _client().board.seek(
        time=payload.minutes,
        increment=payload.increment,
        rated=payload.rated,
        variant=payload.variant,
        color=payload.color,
    )


def _sse_stream(
    request: Request,
    factory: Callable[..., Iterator[dict[str, Any]]],
    *,
    typed_events: bool = False,
) -> StreamingResponse:
    return StreamingResponse(
        iter_sse(request, factory, typed_events=typed_events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _resolve_game_review(
    game_id: str,
    session: SessionDep,
    *,
    refresh: bool = False,
) -> tuple[GameReview, Literal["hit", "miss"]]:
    if not refresh:
        try:
            cached = load_game_review(session, game_id)
            if cached is not None:
                return cached, "hit"
        except HTTPException as exc:
            if exc.status_code != 503:
                raise
            logger.warning("Game review cache unavailable, generating without cache lookup.")

    review = await asyncio.to_thread(generate_game_review, game_id)
    try:
        upsert_game_review(session, game_id, review)
    except HTTPException as exc:
        if exc.status_code != 503:
            raise
        logger.warning("Game review persistence unavailable; returning non-cached review.")
    return review, "miss"


@router.get("/health", response_model=ApiMessage)
def health() -> ApiMessage:
    return ApiMessage(ok=True, message="ok")


@router.get("/debug/game-review-models", response_class=HTMLResponse)
def game_review_models_page() -> HTMLResponse:
    return HTMLResponse(render_game_review_models_html())


@router.get("/debug/game-review-models/sample", response_model=GameReview)
def game_review_models_sample() -> GameReview:
    return sample_game_review()


@router.get(
    "/me",
    response_model=AccountInfo,
    responses={
        401: {"model": ApiError, "description": "Invalid token."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def get_me(_current_user: CurrentUser) -> AccountInfo:
    try:
        data = await asyncio.to_thread(_client().account.get)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc
    return AccountInfo.model_validate(data)


@router.get(
    "/me/games/recent",
    response_model=RecentGamesResponse,
    responses={
        401: {"model": ApiError, "description": "Invalid token or insufficient scope."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def get_recent_games(
    _current_user: CurrentUser,
    limit: int = Query(default=10, ge=1, le=30, description="Maximum number of games to return."),
) -> RecentGamesResponse:
    try:
        client = _client()
        account = await asyncio.to_thread(client.account.get)
        username = account.get("username")
        if not isinstance(username, str) or not username.strip():
            raise HTTPException(status_code=500, detail={"error": "Unable to resolve account username."})

        def fetch_games() -> list[dict[str, Any]]:
            iterator = client.games.export_by_player(
                username=username,
                as_pgn=False,
                max=limit,
                sort="dateDesc",
                finished=True,
                ongoing=False,
                opening=False,
                moves=True,
                clocks=False,
                evals=False,
            )
            return [entry for entry in iterator if isinstance(entry, dict)]

        raw_games = await asyncio.to_thread(fetch_games)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc

    summaries: list[RecentGameSummary] = []
    my_username_lower = username.lower()
    for game in raw_games:
        summary = _summarize_recent_game(game, my_username_lower)
        if summary:
            summaries.append(summary)

    return RecentGamesResponse(ok=True, count=len(summaries), games=summaries)


@router.post(
    "/seek",
    response_model=SeekResponse,
    responses={
        400: {"model": ApiError, "description": "Invalid seek payload."},
        401: {"model": ApiError, "description": "Token missing required scopes."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def create_seek(payload: SeekRequest, _current_user: CurrentUser) -> SeekResponse:
    try:
        _client()
    except HTTPException:
        raise

    def run_seek() -> None:
        try:
            _seek_worker(payload)
        except Exception:
            return

    thread = threading.Thread(target=run_seek, daemon=True)
    thread.start()
    return SeekResponse(ok=True, queued=True, requested=payload)


@router.get("/events", responses={503: {"model": ApiError, "description": "Token not configured."}})
async def stream_events(
    request: Request,
    _current_user: CurrentUser,
) -> StreamingResponse:
    try:
        client = _client()
    except HTTPException:
        raise
    return _sse_stream(request, client.board.stream_incoming_events)


@router.get(
    "/games/{game_id}/stream",
    responses={
        401: {"model": ApiError, "description": "Missing board scope or invalid token."},
        404: {"model": ApiError, "description": "Game not found or inaccessible."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def stream_game(
    request: Request,
    game_id: str,
    _current_user: CurrentUser,
) -> StreamingResponse:
    try:
        client = _client()
    except HTTPException:
        raise
    return _sse_stream(request, lambda: client.board.stream_game_state(game_id))


@router.get(
    "/games/{game_id}/review",
    response_model=GameReview,
    responses={
        401: {"model": ApiError, "description": "Invalid token or insufficient scope."},
        404: {"model": ApiError, "description": "Game not found or inaccessible."},
        503: {"model": ApiError, "description": "Lichess unavailable or token not configured."},
    },
)
async def get_game_review(
    game_id: str,
    response: Response,
    session: SessionDep,
    _current_user: CurrentUser,
    refresh: bool = Query(default=False, description="Bypass cache and regenerate review."),
) -> GameReview:
    review, cache_status = await _resolve_game_review(game_id, session, refresh=refresh)
    response.headers["X-Review-Cache"] = cache_status
    return review


@router.post(
    "/games/{game_id}/review/bedrock",
    response_model=BedrockReviewResponse,
    responses={
        401: {"model": ApiError, "description": "Invalid token or insufficient scope."},
        404: {"model": ApiError, "description": "Game not found or inaccessible."},
        502: {"model": ApiError, "description": "Bedrock request failed."},
        503: {"model": ApiError, "description": "Lichess or Bedrock unavailable."},
    },
)
async def generate_bedrock_review(
    game_id: str,
    response: Response,
    session: SessionDep,
    _current_user: CurrentUser,
    refresh_review: bool = Query(default=False, description="Bypass game-review cache and regenerate structured review."),
    model_id: str | None = Query(default=None, min_length=1, max_length=120, description="Optional Bedrock model ID override."),
    max_context_lines: int = Query(default=10, ge=0, le=25, description="Maximum number of structured context lines included in the prompt."),
) -> BedrockReviewResponse:
    review, cache_status = await _resolve_game_review(game_id, session, refresh=refresh_review)
    response.headers["X-Review-Cache"] = cache_status

    resolved_model_id = settings.BEDROCK_MODEL_ID
    if isinstance(model_id, str) and model_id.strip():
        resolved_model_id = model_id.strip()

    prompt = build_bedrock_review_prompt(
        review,
        model_id=resolved_model_id,
        max_context_lines=max_context_lines,
    )
    completion = await asyncio.to_thread(converse_bedrock_review, prompt)

    return BedrockReviewResponse(
        ok=True,
        game_id=game_id,
        cache=cache_status,
        prompt=prompt,
        completion=completion,
    )


@router.get(
    "/analysis/stream",
    responses={422: {"model": ApiError, "description": "Invalid analysis stream parameters."}},
)
async def stream_analysis(
    request: Request,
    _current_user: CurrentUser,
    fen: str = Query(..., min_length=1, max_length=120, description="Position FEN."),
    multipv: int = Query(default=5, ge=1, le=10),
    min_depth: int = Query(default=8, ge=1, le=60),
    max_depth: int = Query(default=22, ge=1, le=60),
    depth_step: int = Query(default=1, ge=1, le=5),
    movetime_ms: int | None = Query(default=None, ge=25, le=60_000),
    throttle_ms: int = Query(default=200, ge=25, le=2_000),
) -> StreamingResponse:
    try:
        params = StockfishStreamRequest(
            fen=fen,
            multipv=multipv,
            min_depth=min_depth,
            max_depth=max_depth,
            depth_step=depth_step,
            movetime_ms=movetime_ms,
            throttle_ms=throttle_ms,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc

    return _sse_stream(
        request,
        lambda stop_event: stream_stockfish_analysis(params, stop_event=stop_event),
        typed_events=True,
    )


@router.get(
    "/analysis/commentary/stream",
    responses={422: {"model": ApiError, "description": "Invalid Commentary stream parameters."}},
)
async def stream_commentary(
    request: Request,
    _current_user: CurrentUser,
    fen: str = Query(..., min_length=1, max_length=120, description="Position FEN."),
    stockfish_context: str | None = Query(
        default=None,
        min_length=1,
        max_length=4000,
        description="Optional Stockfish summary for prompt grounding.",
    ),
) -> StreamingResponse:
    try:
        params = CommentaryAnalysisStreamRequest(
            fen=fen,
            stockfish_context=stockfish_context,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc

    return _sse_stream(
        request,
        lambda stop_event: stream_commentary_analysis(params, stop_event=stop_event),
        typed_events=True,
    )


@router.post(
    "/openings/lookup",
    response_model=OpeningLookupResponse,
    responses={422: {"model": ApiError, "description": "Invalid move format."}},
)
async def lookup_opening(
    payload: OpeningLookupRequest,
    _current_user: CurrentUser,
) -> OpeningLookupResponse:
    result = resolve_opening(payload.moves, initial_fen=payload.initial_fen, max_continuations=5)
    return OpeningLookupResponse(
        ok=True,
        matched=result.match is not None,
        opening=result.match,
        continuations=result.continuations,
        database=result.database,
    )


@router.post(
    "/games/{game_id}/move",
    response_model=MoveResponse,
    responses={
        400: {"model": ApiError, "description": "Illegal move or invalid game state."},
        401: {"model": ApiError, "description": "Missing board scope or invalid token."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def make_move(
    game_id: str,
    payload: MoveRequest,
    _current_user: CurrentUser,
) -> MoveResponse:
    try:
        client = _client()
        await asyncio.to_thread(client.board.make_move, game_id, payload.uci)
        if payload.offering_draw:
            await asyncio.to_thread(client.board.offer_draw, game_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc
    return MoveResponse(ok=True, game_id=game_id, move=payload.uci)


@router.post(
    "/games/{game_id}/positions",
    response_model=PositionSnapshotResponse,
    responses={
        400: {"model": ApiError, "description": "Invalid snapshot payload."},
        503: {"model": ApiError, "description": "Persistence backend unavailable."},
    },
)
async def save_position(
    game_id: str,
    payload: PositionSnapshotRequest,
    session: SessionDep,
    _current_user: CurrentUser,
) -> PositionSnapshotResponse:
    global _position_persistence_warning_logged
    try:
        saved = save_position_snapshot(session, game_id, payload)
    except HTTPException as exc:
        if exc.status_code == 503:
            if not _position_persistence_warning_logged:
                logger.warning("Position snapshot persistence unavailable; falling back to non-persistent response.")
                _position_persistence_warning_logged = True
            saved = {
                "game_id": game_id,
                "fen": payload.fen,
                "move_count": len(payload.moves),
                "saved_at": datetime.now(timezone.utc),
            }
        else:
            raise
    except Exception as exc:
        raise to_http_exception(exc) from exc
    return PositionSnapshotResponse(ok=True, **saved)


@router.post(
    "/challenges/{challenge_id}/accept",
    response_model=ChallengeActionResponse,
    responses={
        400: {"model": ApiError, "description": "Challenge cannot be accepted."},
        401: {"model": ApiError, "description": "Missing challenge scope or invalid token."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def accept_challenge(
    challenge_id: str,
    _current_user: CurrentUser,
) -> ChallengeActionResponse:
    try:
        await asyncio.to_thread(_client().challenges.accept, challenge_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc
    return ChallengeActionResponse(ok=True, challenge_id=challenge_id, action="accept")


@router.post(
    "/challenges/{challenge_id}/decline",
    response_model=ChallengeActionResponse,
    responses={
        400: {"model": ApiError, "description": "Challenge cannot be declined."},
        401: {"model": ApiError, "description": "Missing challenge scope or invalid token."},
        503: {"model": ApiError, "description": "Token not configured."},
    },
)
async def decline_challenge(
    challenge_id: str,
    payload: ChallengeDeclineRequest,
    _current_user: CurrentUser,
) -> ChallengeActionResponse:
    try:
        await asyncio.to_thread(_client().challenges.decline, challenge_id, payload.reason)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc
    return ChallengeActionResponse(ok=True, challenge_id=challenge_id, action="decline")
