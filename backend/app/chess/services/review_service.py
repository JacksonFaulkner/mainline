from __future__ import annotations

from datetime import datetime, timezone
import io
import re
from typing import Any

import chess
import chess.pgn
from fastapi import HTTPException

from app.chess.schemas.api import UCI_MOVE_PATTERN
from app.chess.schemas.review import (
    EngineContext,
    GameMetadata,
    GameReview,
    MoveReview,
    OpeningMetadata,
    ReviewPlayer,
    ReviewPointOfInterest,
    ReviewSummary,
)
from app.chess.services.lichess import get_client, to_http_exception

_VALID_WINNERS = {"white", "black"}
_DRAW_STATUSES = {
    "draw",
    "stalemate",
    "repetition",
    "timeoutVsInsufficientMaterial",
    "insufficientMaterial",
    "50moves",
    "threefold",
}

_PIECE_CP = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def _timestamp_from_ms(value: Any) -> datetime | None:
    if isinstance(value, int):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    return None


def _player_username(player: dict[str, Any] | None, fallback: str) -> str:
    if not isinstance(player, dict):
        return fallback
    user = player.get("user")
    if isinstance(user, dict):
        name = user.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    name = player.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return fallback


def _player_rating(player: dict[str, Any] | None) -> int | None:
    if not isinstance(player, dict):
        return None
    rating = player.get("rating")
    return rating if isinstance(rating, int) else None


def _player_title(player: dict[str, Any] | None) -> str | None:
    if not isinstance(player, dict):
        return None
    user = player.get("user")
    if isinstance(user, dict):
        title = user.get("title")
        if isinstance(title, str) and title.strip():
            return title.strip()
    title = player.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return None


def _variant_key(raw_variant: Any) -> str | None:
    if isinstance(raw_variant, str):
        return raw_variant
    if isinstance(raw_variant, dict):
        key = raw_variant.get("key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def _result_token(winner: str | None, status: str | None) -> str:
    if winner == "white":
        return "1-0"
    if winner == "black":
        return "0-1"
    if isinstance(status, str) and status in _DRAW_STATUSES:
        return "1/2-1/2"
    return "*"


def _opening_from_payload(payload: dict[str, Any]) -> OpeningMetadata | None:
    opening = payload.get("opening")
    if not isinstance(opening, dict):
        return None

    eco = opening.get("eco")
    name = opening.get("name")
    if not isinstance(eco, str) or not eco.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None

    variation = opening.get("variation")
    normalized_variation = variation.strip() if isinstance(variation, str) and variation.strip() else None

    return OpeningMetadata(
        eco=eco.strip(),
        name=name.strip(),
        variation=normalized_variation,
        source="lichess-export",
    )


def _normalize_uci_moves(raw_moves: Any) -> list[str]:
    if isinstance(raw_moves, str):
        tokens = [token.strip().lower() for token in raw_moves.split() if token.strip()]
    elif isinstance(raw_moves, list):
        tokens = [token.strip().lower() for token in raw_moves if isinstance(token, str) and token.strip()]
    else:
        return []

    if not tokens:
        return []

    if any(re.match(UCI_MOVE_PATTERN, token) is None for token in tokens):
        return []
    return tokens


def _uci_moves_from_pgn(raw_pgn: str) -> list[str]:
    game = chess.pgn.read_game(io.StringIO(raw_pgn))
    if game is None:
        return []
    board = game.board()
    moves: list[str] = []
    for move in game.mainline_moves():
        moves.append(move.uci())
        board.push(move)
    return moves


def _extract_moves(payload: dict[str, Any], raw_pgn: str | None) -> list[str]:
    moves = _normalize_uci_moves(payload.get("moves"))
    if moves:
        return moves
    if raw_pgn and raw_pgn.strip():
        return _uci_moves_from_pgn(raw_pgn)
    return []


def _material_eval_white_cp(board: chess.Board) -> int:
    score = 0
    for piece in board.piece_map().values():
        value = _PIECE_CP[piece.piece_type]
        score += value if piece.color == chess.WHITE else -value
    return score


def _poi_kind(abs_swing_cp: int) -> str:
    if abs_swing_cp >= 300:
        return "blunder"
    if abs_swing_cp >= 180:
        return "mistake"
    if abs_swing_cp >= 80:
        return "inaccuracy"
    return "critical"


def _build_move_reviews(initial_board: chess.Board, moves: list[str]) -> tuple[list[MoveReview], list[ReviewPointOfInterest], ReviewSummary]:
    board = initial_board.copy(stack=False)
    reviews: list[MoveReview] = []
    swings: list[tuple[int, int, str, str, int]] = []
    eval_track: list[tuple[int, int]] = [(0, _material_eval_white_cp(board))]

    for index, uci in enumerate(moves, start=1):
        turn = "white" if index % 2 == 1 else "black"
        fen_before = board.fen()
        eval_before = _material_eval_white_cp(board)

        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break

        if not board.is_legal(move):
            break

        san = board.san(move)
        board.push(move)

        fen_after = board.fen()
        eval_after = _material_eval_white_cp(board)
        swing = eval_after - eval_before

        review = MoveReview(
            ply=index,
            turn=turn,
            san=san,
            uci=uci,
            fen_before=fen_before,
            fen_after=fen_after,
            eval_before_cp=eval_before,
            eval_after_cp=eval_after,
            eval_swing_cp=swing,
        )
        reviews.append(review)
        eval_track.append((index, eval_after))

        if abs(swing) >= 80:
            swings.append((abs(swing), index, turn, san, swing))

    points_of_interest: list[ReviewPointOfInterest] = []
    for _, ply, side, san, swing in sorted(swings, reverse=True)[:5]:
        tail = moves[ply : ply + 3]
        points_of_interest.append(
            ReviewPointOfInterest(
                ply=ply,
                side=side,
                kind=_poi_kind(abs(swing)),
                title=f"{side.title()} played {san} ({swing:+}cp swing)",
                detail="Material balance shifted sharply on this move.",
                swing_cp=swing,
                played_line=tail,
            )
        )

    if eval_track:
        final_eval = eval_track[-1][1]
        white_peak = max(score for _, score in eval_track)
        black_peak = min(score for _, score in eval_track)
        decisive_ply = max(eval_track[1:] or [(0, 0)], key=lambda item: abs(item[1]))[0] or None
    else:
        final_eval = 0
        white_peak = 0
        black_peak = 0
        decisive_ply = None

    summary = ReviewSummary(
        final_eval_white_cp=final_eval,
        decisive_ply=decisive_ply,
        white_advantage_peak_cp=white_peak,
        black_advantage_peak_cp=black_peak,
        notes=["Review uses a material-based heuristic when full engine analysis is unavailable."],
    )

    return reviews, points_of_interest, summary


def _build_review(game_id: str, payload: dict[str, Any], raw_pgn: str | None) -> GameReview:
    resolved_game_id = payload.get("id") if isinstance(payload.get("id"), str) else game_id

    players = payload.get("players") if isinstance(payload.get("players"), dict) else {}
    white_raw = players.get("white") if isinstance(players, dict) else None
    black_raw = players.get("black") if isinstance(players, dict) else None

    winner = payload.get("winner") if payload.get("winner") in _VALID_WINNERS else None
    status = payload.get("status") if isinstance(payload.get("status"), str) else None
    result = _result_token(winner, status)
    variant = _variant_key(payload.get("variant"))

    initial_fen_raw = payload.get("initialFen")
    initial_fen = initial_fen_raw.strip() if isinstance(initial_fen_raw, str) and initial_fen_raw.strip() else None
    board_fen = initial_fen if initial_fen and initial_fen != "startpos" else chess.STARTING_FEN
    try:
        board = chess.Board(board_fen, chess960=(variant == "chess960"))
    except ValueError:
        board = chess.Board()
        initial_fen = None

    moves = _extract_moves(payload, raw_pgn)
    move_reviews, points_of_interest, summary = _build_move_reviews(board, moves)

    metadata = GameMetadata(
        game_id=resolved_game_id,
        url=f"https://lichess.org/{resolved_game_id}",
        played_at=_timestamp_from_ms(payload.get("createdAt")) or _timestamp_from_ms(payload.get("lastMoveAt")),
        white=ReviewPlayer(
            username=_player_username(white_raw, "White"),
            rating=_player_rating(white_raw),
            title=_player_title(white_raw),
        ),
        black=ReviewPlayer(
            username=_player_username(black_raw, "Black"),
            rating=_player_rating(black_raw),
            title=_player_title(black_raw),
        ),
        result=result,
        winner=winner,
        rated=payload.get("rated") if isinstance(payload.get("rated"), bool) else None,
        speed=payload.get("speed") if isinstance(payload.get("speed"), str) else None,
        perf=payload.get("perf") if isinstance(payload.get("perf"), str) else None,
        variant=variant,
        initialFen=initial_fen,
        total_plies=len(move_reviews),
        termination=status,
    )

    return GameReview(
        game=metadata,
        opening=_opening_from_payload(payload),
        engine=EngineContext(name="material-heuristic", depth=1, multipv=1),
        moves=move_reviews,
        points_of_interest=points_of_interest,
        summary=summary,
        raw_pgn=raw_pgn,
    )


def generate_game_review(game_id: str) -> GameReview:
    """Fetch a game from Lichess and build a review payload."""
    try:
        client = get_client()
        payload = client.games.export(game_id, as_pgn=False)
        raw_pgn = client.games.export(game_id, as_pgn=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise to_http_exception(exc) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=502,
            detail={"error": "Unexpected game export response format from Lichess."},
        )

    pgn_text = raw_pgn if isinstance(raw_pgn, str) else None

    try:
        return _build_review(game_id, payload, pgn_text)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to build game review: {exc}"},
        ) from exc
