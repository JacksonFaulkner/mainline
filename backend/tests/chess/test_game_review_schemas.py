from __future__ import annotations

import unittest

from pydantic import ValidationError

from fastapi.testclient import TestClient

from app.chess.schemas.review import (
    BedrockContextLine,
    BedrockReviewPrompt,
    EngineContext,
    EngineLine,
    GameMetadata,
    GameReview,
    MoveReview,
    OpeningMetadata,
    ReviewPlayer,
    ReviewPointOfInterest,
    ReviewSummary,
    build_bedrock_review_prompt,
    sample_game_review,
)
from app.main import app


class GameReviewModelTests(unittest.TestCase):
    def test_game_review_accepts_comprehensive_payload(self) -> None:
        review = GameReview(
            game={
                "game_id": "game-123",
                "url": "https://lichess.org/game-123",
                "white": {"username": "alpha"},
                "black": {"username": "beta"},
                "result": "1-0",
                "winner": "white",
                "total_plies": 3,
            },
            opening={"eco": "C20", "name": "King's Pawn Game"},
            moves=[
                {"ply": 1, "turn": "white", "san": "e4", "uci": "e2e4"},
                {"ply": 2, "turn": "black", "san": "e5", "uci": "e7e5"},
                {"ply": 3, "turn": "white", "san": "Nf3", "uci": "g1f3"},
            ],
            points_of_interest=[
                {
                    "ply": 3,
                    "side": "white",
                    "kind": "critical",
                    "title": "Develops with tempo",
                }
            ],
            summary={"decisive_ply": 3},
        )

        self.assertEqual(review.game.game_id, "game-123")
        self.assertEqual(len(review.moves), 3)
        self.assertEqual(review.moves[1].ply, 2)
        self.assertEqual(review.moves[1].uci, "e7e5")

    def test_game_review_rejects_bad_ply_order(self) -> None:
        with self.assertRaises(ValidationError):
            GameReview(
                game={
                    "game_id": "game-123",
                    "url": "https://lichess.org/game-123",
                    "white": {"username": "alpha"},
                    "black": {"username": "beta"},
                    "result": "1-0",
                    "winner": "white",
                },
                moves=[
                    {"ply": 1, "turn": "white", "san": "e4", "uci": "e2e4"},
                    {"ply": 3, "turn": "black", "san": "e5", "uci": "e7e5"},
                ],
                )

    def test_every_model_field_has_description(self) -> None:
        model_types = (
            ReviewPlayer,
            GameMetadata,
            OpeningMetadata,
            EngineContext,
            EngineLine,
            MoveReview,
            ReviewPointOfInterest,
            ReviewSummary,
            BedrockContextLine,
            BedrockReviewPrompt,
            GameReview,
        )
        missing: list[str] = []
        for model_type in model_types:
            for field_name, field in model_type.model_fields.items():
                description = field.description
                if not isinstance(description, str) or not description.strip():
                    missing.append(f"{model_type.__name__}.{field_name}")
        self.assertEqual(missing, [], msg=f"Missing descriptions for: {missing}")

    def test_build_bedrock_review_prompt_includes_high_signal_context(self) -> None:
        review = sample_game_review()
        prompt = build_bedrock_review_prompt(review)

        self.assertEqual(
            prompt.model_id,
            "arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        self.assertGreaterEqual(len(prompt.context_lines), 4)
        rendered = prompt.rendered_user_message()
        self.assertIn("What decided the game", rendered)
        self.assertIn("Context:", rendered)
        self.assertTrue(any(line.label == "Opening" for line in prompt.context_lines))
        self.assertTrue(any(line.label == "Critical" for line in prompt.context_lines))


class GameReviewDebugRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_game_review_model_map_page_renders(self) -> None:
        response = self.client.get("/api/v1/chess/debug/game-review-models")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Game Review Data Map", response.text)
        self.assertIn("GameReview", response.text)

    def test_game_review_sample_payload_renders(self) -> None:
        response = self.client.get("/api/v1/chess/debug/game-review-models/sample")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("game", body)
        self.assertIn("moves", body)
        self.assertIn("points_of_interest", body)


if __name__ == "__main__":
    unittest.main()
