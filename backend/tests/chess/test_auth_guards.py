from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app


class ChessAuthGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides.clear()
        self.client = TestClient(app)
        self.fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    def test_health_route_is_public(self) -> None:
        response = self.client.get("/api/v1/chess/health")
        self.assertEqual(response.status_code, 200)

    def test_analysis_stream_requires_auth(self) -> None:
        response = self.client.get(
            "/api/v1/chess/analysis/stream",
            params={"fen": self.fen},
        )
        self.assertEqual(response.status_code, 401)

    def test_commentary_stream_requires_auth(self) -> None:
        response = self.client.get(
            "/api/v1/chess/analysis/commentary/stream",
            params={"fen": self.fen},
        )
        self.assertEqual(response.status_code, 401)

    def test_opening_lookup_requires_auth(self) -> None:
        response = self.client.post(
            "/api/v1/chess/openings/lookup",
            json={"moves": ["e2e4", "e7e5"]},
        )
        self.assertEqual(response.status_code, 401)

    def test_game_review_requires_auth(self) -> None:
        response = self.client.get("/api/v1/chess/games/example/review")
        self.assertEqual(response.status_code, 401)

    def test_bedrock_game_review_requires_auth(self) -> None:
        response = self.client.post("/api/v1/chess/games/example/review/bedrock")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
