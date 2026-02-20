from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.chess.schemas.api import PositionSnapshotRequest
from app.chess.services.persistence import save_position_snapshot
from app.main import app
from app.models import ChessPositionSnapshot
from tests.chess.auth import disable_auth_override, enable_auth_override


class SnapshotPersistenceTests(unittest.TestCase):
    def test_save_position_snapshot_upserts_by_game_and_move_count(self) -> None:
        payload = PositionSnapshotRequest(
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            moves=["e2e4"],
            status="started",
        )
        existing = ChessPositionSnapshot(
            game_id="abc123",
            move_count=1,
            fen=payload.fen,
            moves_json=payload.moves,
            status="started",
            saved_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        session = MagicMock()
        session.exec.return_value.first.return_value = existing

        saved = save_position_snapshot(session, "abc123", payload)

        self.assertEqual(saved["game_id"], "abc123")
        self.assertEqual(saved["move_count"], 1)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(existing)

    def test_save_position_snapshot_maps_database_error(self) -> None:
        payload = PositionSnapshotRequest(
            fen="8/8/8/8/8/8/8/8 w - - 0 1",
            moves=[],
            status="started",
        )
        session = MagicMock()
        session.exec.side_effect = SQLAlchemyError("db is down")

        with self.assertRaises(HTTPException) as exc_info:
            save_position_snapshot(session, "abc123", payload)

        self.assertEqual(exc_info.exception.status_code, 503)


class StorageApiTests(unittest.TestCase):
    def setUp(self) -> None:
        enable_auth_override()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        disable_auth_override()

    def test_save_position_endpoint_returns_snapshot(self) -> None:
        saved_at = datetime.now(timezone.utc)
        saved_doc = {
            "game_id": "abc123",
            "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            "move_count": 1,
            "saved_at": saved_at,
        }
        with patch("app.api.routes.chess.save_position_snapshot", return_value=saved_doc):
            response = self.client.post(
                "/api/v1/chess/games/abc123/positions",
                json={
                    "fen": saved_doc["fen"],
                    "moves": ["e2e4"],
                    "status": "started",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["game_id"], "abc123")
        self.assertEqual(body["move_count"], 1)

    def test_save_position_endpoint_validates_moves(self) -> None:
        response = self.client.post(
            "/api/v1/chess/games/abc123/positions",
            json={
                "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
                "moves": ["not-a-move"],
                "status": "started",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_save_position_endpoint_falls_back_when_persistence_unavailable(self) -> None:
        with patch(
            "app.api.routes.chess.save_position_snapshot",
            side_effect=HTTPException(
                status_code=503,
                detail={"error": "Persistence unavailable."},
            ),
        ):
            response = self.client.post(
                "/api/v1/chess/games/abc123/positions",
                json={
                    "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
                    "moves": ["e2e4"],
                    "status": "started",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["game_id"], "abc123")
        self.assertEqual(body["move_count"], 1)
        self.assertIsNotNone(body["saved_at"])

    def test_recent_games_endpoint_returns_summaries(self) -> None:
        fake_games = MagicMock()
        fake_games.export_by_player.return_value = iter(
            [
                {
                    "id": "g123",
                    "players": {
                        "white": {"user": {"name": "MyUser"}, "rating": 1550},
                        "black": {"user": {"name": "Opponent"}, "rating": 1620},
                    },
                    "winner": "white",
                    "rated": True,
                    "speed": "rapid",
                    "perf": "rapid",
                    "variant": "standard",
                    "status": "mate",
                    "createdAt": 1736000000000,
                    "lastMoveAt": 1736000900000,
                }
            ]
        )
        fake_client = MagicMock()
        fake_client.account.get.return_value = {"username": "MyUser"}
        fake_client.games = fake_games

        with patch("app.api.routes.chess._client", return_value=fake_client):
            response = self.client.get("/api/v1/chess/me/games/recent?limit=5")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["games"][0]["game_id"], "g123")
        self.assertEqual(body["games"][0]["my_result"], "win")
        self.assertEqual(body["games"][0]["opponent_name"], "Opponent")
        self.assertEqual(body["games"][0]["speed"], "rapid")
        self.assertEqual(body["games"][0]["preview_fens"], [])
        self.assertEqual(body["games"][0]["preview_sans"], [])
        fake_games.export_by_player.assert_called_once()
        self.assertTrue(fake_games.export_by_player.call_args.kwargs["moves"])


if __name__ == "__main__":
    unittest.main()
