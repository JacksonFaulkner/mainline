from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import TypeAdapter, ValidationError

from app.chess.schemas.api import (
    StockfishAnalysisCompleteEvent,
    StockfishDepthUpdateEvent,
    StockfishStreamEvent,
    StockfishStreamRequest,
)


class StockfishStreamModelTests(unittest.TestCase):
    def test_stream_request_validates_depth_bounds(self) -> None:
        request = StockfishStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            min_depth=8,
            max_depth=20,
            multipv=5,
        )
        self.assertEqual(request.min_depth, 8)
        self.assertEqual(request.max_depth, 20)

        with self.assertRaises(ValidationError):
            StockfishStreamRequest(
                fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                min_depth=18,
                max_depth=12,
            )

    def test_depth_update_accepts_top_five_pv_lines(self) -> None:
        event = StockfishDepthUpdateEvent(
            analysis_id="analysis-123",
            fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
            side_to_move="white",
            depth=14,
            multipv=5,
            bestmove_uci="f1b5",
            generated_at=datetime.now(tz=timezone.utc),
            lines=[
                {
                    "rank": 1,
                    "arrow": {
                        "uci": "f1b5",
                        "from_square": "f1",
                        "to_square": "b5",
                        "color_slot": 1,
                    },
                    "cp": 45,
                    "pv": ["f1b5", "a7a6", "b5a4"],
                },
                {
                    "rank": 2,
                    "arrow": {
                        "uci": "d2d4",
                        "from_square": "d2",
                        "to_square": "d4",
                        "color_slot": 2,
                    },
                    "cp": 38,
                    "pv": ["d2d4", "e5d4", "f3d4"],
                },
                {
                    "rank": 3,
                    "arrow": {
                        "uci": "c2c3",
                        "from_square": "c2",
                        "to_square": "c3",
                        "color_slot": 3,
                    },
                    "cp": 30,
                    "pv": ["c2c3", "g8f6", "d2d4"],
                },
                {
                    "rank": 4,
                    "arrow": {
                        "uci": "b1c3",
                        "from_square": "b1",
                        "to_square": "c3",
                        "color_slot": 4,
                    },
                    "cp": 22,
                    "pv": ["b1c3", "g8f6", "f1c4"],
                },
                {
                    "rank": 5,
                    "arrow": {
                        "uci": "h2h3",
                        "from_square": "h2",
                        "to_square": "h3",
                        "color_slot": 5,
                    },
                    "cp": 15,
                    "pv": ["h2h3", "g8f6", "d2d3"],
                },
            ],
        )
        self.assertEqual(event.depth, 14)
        self.assertEqual(len(event.lines), 5)
        self.assertEqual(event.lines[0].arrow.uci, "f1b5")

    def test_stream_union_discriminator_parses_depth_and_complete_events(self) -> None:
        adapter = TypeAdapter(StockfishStreamEvent)
        depth_event = adapter.validate_python(
            {
                "type": "depth_update",
                "analysis_id": "analysis-123",
                "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
                "side_to_move": "white",
                "depth": 10,
                "multipv": 1,
                "generated_at": datetime.now(tz=timezone.utc),
                "lines": [],
            }
        )
        self.assertIsInstance(depth_event, StockfishDepthUpdateEvent)

        complete_event = adapter.validate_python(
            {
                "type": "analysis_complete",
                "analysis_id": "analysis-123",
                "fen": "8/8/8/8/8/8/8/8 w - - 0 1",
                "final_depth": 18,
                "bestmove_uci": "a2a4",
                "lines": [],
                "reason": "depth_reached",
                "generated_at": datetime.now(tz=timezone.utc),
            }
        )
        self.assertIsInstance(complete_event, StockfishAnalysisCompleteEvent)


if __name__ == "__main__":
    unittest.main()
