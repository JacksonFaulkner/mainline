from __future__ import annotations

import unittest
from unittest.mock import ANY, patch

from fastapi.testclient import TestClient

from app.chess.schemas.review import BedrockCompletion, sample_game_review
from app.main import app
from tests.chess.auth import disable_auth_override, enable_auth_override


class GameReviewApiTests(unittest.TestCase):
    def setUp(self) -> None:
        enable_auth_override()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        disable_auth_override()

    def test_review_endpoint_returns_cached_review_when_available(self) -> None:
        cached_review = sample_game_review()
        with patch("app.api.routes.chess.load_game_review", return_value=cached_review) as load_review, patch(
            "app.api.routes.chess.generate_game_review"
        ) as generate_review:
            response = self.client.get(f"/api/v1/chess/games/{cached_review.game.game_id}/review")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-review-cache"), "hit")
        body = response.json()
        self.assertEqual(body["game"]["game_id"], cached_review.game.game_id)
        load_review.assert_called_once()
        generate_review.assert_not_called()

    def test_review_endpoint_generates_and_persists_on_cache_miss(self) -> None:
        generated_review = sample_game_review().model_copy(
            update={
                "game": sample_game_review().game.model_copy(
                    update={"game_id": "fresh123", "url": "https://lichess.org/fresh123"}
                )
            }
        )

        with patch("app.api.routes.chess.load_game_review", return_value=None) as load_review, patch(
            "app.api.routes.chess.generate_game_review", return_value=generated_review
        ) as generate_review, patch(
            "app.api.routes.chess.upsert_game_review", return_value=generated_review
        ) as upsert_review:
            response = self.client.get("/api/v1/chess/games/fresh123/review")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-review-cache"), "miss")
        body = response.json()
        self.assertEqual(body["game"]["game_id"], "fresh123")
        load_review.assert_called_once_with(ANY, "fresh123")
        generate_review.assert_called_once_with("fresh123")
        upsert_review.assert_called_once_with(ANY, "fresh123", generated_review)

    def test_review_endpoint_refresh_bypasses_cache_lookup(self) -> None:
        generated_review = sample_game_review()

        with patch("app.api.routes.chess.load_game_review") as load_review, patch(
            "app.api.routes.chess.generate_game_review", return_value=generated_review
        ) as generate_review, patch(
            "app.api.routes.chess.upsert_game_review", return_value=generated_review
        ):
            response = self.client.get(
                f"/api/v1/chess/games/{generated_review.game.game_id}/review?refresh=true"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-review-cache"), "miss")
        load_review.assert_not_called()
        generate_review.assert_called_once()

    def test_bedrock_review_endpoint_returns_completion_payload(self) -> None:
        cached_review = sample_game_review()
        completion = BedrockCompletion(
            model_id="arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
            text="The game turned on move 4 where black centralized the queen.",
            stop_reason="end_turn",
            latency_ms=320,
        )

        with patch("app.api.routes.chess.load_game_review", return_value=cached_review) as load_review, patch(
            "app.api.routes.chess.generate_game_review"
        ) as generate_review, patch(
            "app.api.routes.chess.converse_bedrock_review", return_value=completion
        ) as bedrock_call:
            response = self.client.post(f"/api/v1/chess/games/{cached_review.game.game_id}/review/bedrock")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-review-cache"), "hit")
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["game_id"], cached_review.game.game_id)
        self.assertEqual(body["cache"], "hit")
        self.assertEqual(
            body["prompt"]["model_id"],
            "arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
        self.assertIn("What decided the game", body["prompt"]["user_message"])
        self.assertEqual(body["completion"]["text"], completion.text)
        load_review.assert_called_once_with(ANY, cached_review.game.game_id)
        generate_review.assert_not_called()
        bedrock_call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
