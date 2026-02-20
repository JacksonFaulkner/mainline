from __future__ import annotations

import json
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.chess.schemas.api import (
    CommentaryAnalysisCompleteEvent,
    CommentaryAnalysisStreamRequest,
    CommentaryTextDeltaEvent,
    StockfishAnalysisCompleteEvent,
    StockfishDepthUpdateEvent,
    StockfishStreamRequest,
)
from app.main import app
from tests.chess.auth import disable_auth_override, enable_auth_override


class AnalysisStreamApiTests(unittest.TestCase):
    def setUp(self) -> None:
        enable_auth_override()
        self.client = TestClient(app)
        self.fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"

    def tearDown(self) -> None:
        disable_auth_override()

    @staticmethod
    def _collect_sse_events(response, limit: int) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        current_event = "message"
        for raw_line in response.iter_lines():
            line = raw_line.decode() if isinstance(raw_line, bytes) else raw_line
            if not line:
                continue
            if line.startswith("event: "):
                current_event = line.split("event: ", 1)[1]
                continue
            if line.startswith("data: "):
                payload = json.loads(line.split("data: ", 1)[1])
                events.append((current_event, payload))
                if len(events) >= limit:
                    break
        return events

    def test_stream_endpoint_emits_depth_update_then_complete(self) -> None:
        def fake_stream(
            params: StockfishStreamRequest,
            stop_event: threading.Event | None = None,
        ):
            self.assertEqual(params.multipv, 2)
            self.assertIsNotNone(stop_event)
            generated_at = datetime.now(timezone.utc)
            yield StockfishDepthUpdateEvent(
                analysis_id="analysis-abc",
                fen=params.fen,
                side_to_move="white",
                depth=10,
                multipv=2,
                bestmove_uci="f1b5",
                lines=[],
                generated_at=generated_at,
            ).model_dump(mode="json")
            yield StockfishAnalysisCompleteEvent(
                analysis_id="analysis-abc",
                fen=params.fen,
                final_depth=12,
                bestmove_uci="f1b5",
                lines=[],
                reason="depth_reached",
                generated_at=generated_at,
            ).model_dump(mode="json")

        with patch("app.api.routes.chess.stream_stockfish_analysis", side_effect=fake_stream) as mocked_stream:
            with self.client.stream(
                "GET",
                "/api/v1/chess/analysis/stream",
                params={
                    "fen": self.fen,
                    "multipv": 2,
                    "min_depth": 8,
                    "max_depth": 12,
                    "depth_step": 2,
                    "throttle_ms": 25,
                },
            ) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/event-stream", response.headers.get("content-type", ""))
                events = self._collect_sse_events(response, limit=2)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][0], "depth_update")
        self.assertEqual(events[0][1]["type"], "depth_update")
        self.assertEqual(events[1][0], "analysis_complete")
        self.assertEqual(events[1][1]["type"], "analysis_complete")
        mocked_stream.assert_called_once()

    def test_stream_endpoint_rejects_invalid_depth_range(self) -> None:
        response = self.client.get(
            "/api/v1/chess/analysis/stream",
            params={"fen": self.fen, "min_depth": 20, "max_depth": 12, "throttle_ms": 25},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("max_depth must be >= min_depth", response.text)

    def test_stream_endpoint_propagates_cancel_signal_to_stream_service(self) -> None:
        cancel_seen = threading.Event()
        started = threading.Event()

        def cancellable_stream(
            params: StockfishStreamRequest,
            stop_event: threading.Event | None = None,
        ):
            started.set()
            generated_at = datetime.now(timezone.utc)
            yield StockfishDepthUpdateEvent(
                analysis_id="analysis-cancel",
                fen=params.fen,
                side_to_move="white",
                depth=8,
                multipv=1,
                bestmove_uci="f1b5",
                lines=[],
                generated_at=generated_at,
            ).model_dump(mode="json")
            while stop_event is not None and not stop_event.is_set():
                time.sleep(0.01)
            cancel_seen.set()

        async def fake_iter_sse(_request, iterator_factory, typed_events: bool = False):
            self.assertTrue(typed_events)
            stop_event = threading.Event()
            iterator = iterator_factory(stop_event)
            next(iterator, None)
            stop_event.set()
            for _ in iterator:
                break
            yield "event: analysis_complete\ndata: {}\n\n"

        with patch("app.api.routes.chess.stream_stockfish_analysis", side_effect=cancellable_stream), patch(
            "app.api.routes.chess.iter_sse", side_effect=fake_iter_sse
        ):
            response = self.client.get(
                "/api/v1/chess/analysis/stream",
                params={"fen": self.fen, "min_depth": 8, "max_depth": 8, "multipv": 1, "throttle_ms": 25},
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("analysis_complete", response.text)

        self.assertTrue(started.is_set())
        self.assertTrue(cancel_seen.wait(timeout=1.5))

    def test_commentary_stream_endpoint_emits_delta_then_complete(self) -> None:
        def fake_commentary_stream(
            params: CommentaryAnalysisStreamRequest,
            stop_event: threading.Event | None = None,
        ):
            self.assertEqual(params.fen, self.fen)
            self.assertEqual(
                params.stockfish_context,
                "Depth 12. Best move Nf3 (+0.28). Top lines: #1 Nf3 (+0.28)",
            )
            self.assertIsNotNone(stop_event)
            generated_at = datetime.now(timezone.utc)
            yield CommentaryTextDeltaEvent(
                analysis_id="commentary-abc",
                text_delta="White is slightly better. ",
                text="White is slightly better. ",
                generated_at=generated_at,
            ).model_dump(mode="json")
            yield CommentaryAnalysisCompleteEvent(
                analysis_id="commentary-abc",
                text="White is slightly better. Develop with tempo and pressure e5.",
                stop_reason="end_turn",
                generated_at=generated_at,
            ).model_dump(mode="json")

        with patch("app.api.routes.chess.stream_commentary_analysis", side_effect=fake_commentary_stream) as mocked_stream:
            with self.client.stream(
                "GET",
                "/api/v1/chess/analysis/commentary/stream",
                params={
                    "fen": self.fen,
                    "stockfish_context": "Depth 12. Best move Nf3 (+0.28). Top lines: #1 Nf3 (+0.28)",
                },
            ) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/event-stream", response.headers.get("content-type", ""))
                events = self._collect_sse_events(response, limit=2)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0][0], "commentary_text_delta")
        self.assertEqual(events[0][1]["type"], "commentary_text_delta")
        self.assertEqual(events[1][0], "commentary_complete")
        self.assertEqual(events[1][1]["type"], "commentary_complete")
        mocked_stream.assert_called_once()


if __name__ == "__main__":
    unittest.main()
