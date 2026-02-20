from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from app.chess.schemas.api import PositionSnapshotRequest
from app.chess.schemas.review import GameReview
from app.models import ChessGameReview, ChessPositionSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def save_position_snapshot(
    session: Session,
    game_id: str,
    payload: PositionSnapshotRequest,
) -> dict[str, Any]:
    move_count = len(payload.moves)

    try:
        snapshot = session.exec(
            select(ChessPositionSnapshot).where(
                ChessPositionSnapshot.game_id == game_id,
                ChessPositionSnapshot.move_count == move_count,
            )
        ).first()
        if snapshot is None:
            snapshot = ChessPositionSnapshot(
                game_id=game_id,
                move_count=move_count,
                fen=payload.fen,
                moves_json=payload.moves,
                status=payload.status,
                saved_at=_utcnow(),
                created_at=_utcnow(),
            )
        else:
            snapshot.fen = payload.fen
            snapshot.moves_json = payload.moves
            snapshot.status = payload.status
            snapshot.saved_at = _utcnow()

        session.add(snapshot)
        session.commit()
        session.refresh(snapshot)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": f"Database write failed: {exc}"},
        ) from exc

    return {
        "game_id": snapshot.game_id,
        "fen": snapshot.fen,
        "move_count": snapshot.move_count,
        "saved_at": snapshot.saved_at,
    }


def load_game_review(session: Session, game_id: str) -> GameReview | None:
    try:
        stored = session.exec(
            select(ChessGameReview).where(ChessGameReview.game_id == game_id)
        ).first()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": f"Database read failed: {exc}"},
        ) from exc

    if stored is None:
        return None
    if not isinstance(stored.review_json, dict):
        return None
    return GameReview.model_validate(stored.review_json)


def upsert_game_review(session: Session, game_id: str, review: GameReview) -> GameReview:
    payload = review.model_dump(mode="python", by_alias=True)
    now = _utcnow()

    try:
        stored = session.exec(
            select(ChessGameReview).where(ChessGameReview.game_id == game_id)
        ).first()
        if stored is None:
            stored = ChessGameReview(
                game_id=game_id,
                review_json=payload,
                updated_at=now,
                created_at=now,
            )
        else:
            stored.review_json = payload
            stored.updated_at = now

        session.add(stored)
        session.commit()
        session.refresh(stored)
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=503,
            detail={"error": f"Database write failed: {exc}"},
        ) from exc

    if not isinstance(stored.review_json, dict):
        raise HTTPException(
            status_code=500,
            detail={"error": "Database write succeeded but no review payload was returned."},
        )
    return GameReview.model_validate(stored.review_json)

