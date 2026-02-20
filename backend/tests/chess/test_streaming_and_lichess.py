from __future__ import annotations

import json
import logging
import unittest

import berserk
import requests

from app.chess.services.lichess import to_http_exception
from app.api.routes.chess import _summarize_recent_game
from app.chess.services.streaming import _serialize_exception, iter_sse


class _FakeRequest:
    def __init__(self, disconnect_after: int | None = None) -> None:
        self._disconnect_after = disconnect_after
        self._calls = 0

    async def is_disconnected(self) -> bool:
        self._calls += 1
        if self._disconnect_after is None:
            return False
        return self._calls > self._disconnect_after


class _ErrorWithMetadata(Exception):
    def __init__(self, message: str, status_code: int, cause: dict[str, str]) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.cause = cause


def _play_scholars_mate_against_itself() -> dict[str, object]:
    # Deterministic self-play script ending in Scholar's Mate.
    moves = ["e2e4", "e7e5", "d1h5", "b8c6", "f1c4", "g8f6", "h5f7"]
    game_state: dict[str, object] = {
        "id": "scholars-self-play",
        "players": {
            "white": {"user": {"name": "SelfBot"}, "rating": 1500},
            "black": {"user": {"name": "SelfBot"}, "rating": 1500},
        },
        "rated": False,
        "speed": "blitz",
        "perf": "blitz",
        "variant": "standard",
        "status": "started",
        "moves": [],
    }
    for move in moves:
        cast_moves = game_state["moves"]
        if isinstance(cast_moves, list):
            cast_moves.append(move)
    game_state["status"] = "mate"
    game_state["winner"] = "white"
    return game_state


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_iter_sse_yields_json_data_event(self) -> None:
        request = _FakeRequest()
        iterator_factory = lambda: iter([{"type": "gameState", "moves": "e2e4"}])

        chunks: list[str] = []
        async for chunk in iter_sse(request, iterator_factory):
            chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        self.assertTrue(chunks[0].startswith("data: "))
        payload = json.loads(chunks[0][len("data: ") :].strip())
        self.assertEqual(payload["type"], "gameState")
        self.assertEqual(payload["moves"], "e2e4")

    async def test_iter_sse_emits_proxy_error_event(self) -> None:
        request = _FakeRequest()

        def failing_iterator():
            yield {"type": "gameState", "moves": "e2e4"}
            raise RuntimeError("stream exploded")

        with self.assertLogs("app.chess.services.streaming", level=logging.ERROR) as captured:
            chunks: list[str] = []
            async for chunk in iter_sse(request, failing_iterator):
                chunks.append(chunk)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("data: "))
        self.assertTrue(chunks[1].startswith("event: proxy_error\n"))
        error_payload = json.loads(chunks[1].split("data: ", 1)[1].strip())
        self.assertEqual(error_payload["error"], "stream exploded")
        for line in captured.output:
            print(line)

    async def test_iter_sse_stops_when_disconnected(self) -> None:
        request = _FakeRequest(disconnect_after=0)
        iterator_factory = lambda: iter([{"type": "gameState", "moves": "e2e4"}])

        chunks: list[str] = []
        async for chunk in iter_sse(request, iterator_factory):
            chunks.append(chunk)

        self.assertEqual(chunks, [])

    async def test_iter_sse_background_worker_logs_debug_messages(self) -> None:
        request = _FakeRequest()
        iterator_factory = lambda: iter([{"type": "gameState", "moves": "e2e4"}])

        with self.assertLogs("app.chess.services.streaming", level=logging.DEBUG) as captured:
            chunks: list[str] = []
            async for chunk in iter_sse(request, iterator_factory):
                chunks.append(chunk)

        self.assertEqual(len(chunks), 1)
        joined = "\n".join(captured.output)
        self.assertIn("SSE worker thread started", joined)
        self.assertIn("SSE worker queued payload type=gameState", joined)
        self.assertIn("SSE worker thread finished", joined)
        for line in captured.output:
            print(line)


class StreamingSerializationTests(unittest.TestCase):
    def test_serialize_exception_includes_status_and_cause(self) -> None:
        payload = _serialize_exception(
            _ErrorWithMetadata("downstream failed", 418, {"error": "teapot"})
        )
        self.assertEqual(payload["error"], "downstream failed")
        self.assertEqual(payload["status_code"], 418)
        self.assertEqual(payload["cause"], {"error": "teapot"})

    def test_serialize_exception_without_metadata(self) -> None:
        payload = _serialize_exception(RuntimeError("plain error"))
        self.assertEqual(payload, {"error": "plain error"})


class LichessErrorTests(unittest.TestCase):
    def test_to_http_exception_maps_response_error(self) -> None:
        response = requests.Response()
        response.status_code = 401
        response._content = b'{"error":"bad token"}'
        response.headers["Content-Type"] = "application/json"
        exc = berserk.exceptions.ResponseError(response)

        http_exc = to_http_exception(exc)

        self.assertEqual(http_exc.status_code, 401)
        self.assertIsInstance(http_exc.detail, dict)
        self.assertIn("error", http_exc.detail)

    def test_to_http_exception_wraps_generic_exception(self) -> None:
        http_exc = to_http_exception(RuntimeError("boom"))
        self.assertEqual(http_exc.status_code, 500)
        self.assertEqual(http_exc.detail, {"error": "boom"})


class RecentGameLoggingTests(unittest.TestCase):
    def test_scholars_mate_self_play_logs_winner(self) -> None:
        game = _play_scholars_mate_against_itself()

        with self.assertLogs("app.api.routes.chess", level=logging.INFO) as captured:
            summary = _summarize_recent_game(game, my_username_lower="selfbot")

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.winner, "white")
        self.assertEqual(summary.my_result, "win")
        self.assertEqual(summary.status, "mate")
        joined = "\n".join(captured.output)
        self.assertIn("game_id=scholars-self-play", joined)
        self.assertIn("winner=white", joined)
        for line in captured.output:
            print(line)


if __name__ == "__main__":
    unittest.main()
