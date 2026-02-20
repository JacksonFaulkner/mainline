from __future__ import annotations

import unittest
from unittest.mock import patch

import chess
import chess.engine

import app.chess.services.analysis_stream as analysis_stream_module
from app.chess.schemas.api import StockfishStreamRequest
from app.chess.services.analysis_stream import _build_lines, stream_stockfish_analysis


class StockfishStreamServiceTests(unittest.TestCase):
    def test_build_lines_orders_by_multipv_and_maps_cp(self) -> None:
        board = chess.Board()
        raw_info = [
            {
                "multipv": 2,
                "score": chess.engine.PovScore(chess.engine.Cp(22), chess.WHITE),
                "pv": [chess.Move.from_uci("d2d4"), chess.Move.from_uci("d7d5")],
            },
            {
                "multipv": 1,
                "score": chess.engine.PovScore(chess.engine.Cp(34), chess.WHITE),
                "pv": [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
            },
        ]

        lines = _build_lines(board, raw_info, multipv=5)

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].rank, 1)
        self.assertEqual(lines[0].arrow.uci, "e2e4")
        self.assertEqual(lines[0].cp, 34)
        self.assertEqual(lines[1].rank, 2)
        self.assertEqual(lines[1].arrow.uci, "d2d4")
        self.assertEqual(lines[1].cp, 22)

    def test_build_lines_maps_mate_scores(self) -> None:
        board = chess.Board()
        raw_info = [
            {
                "multipv": 1,
                "score": chess.engine.PovScore(chess.engine.Mate(3), chess.WHITE),
                "pv": [chess.Move.from_uci("e2e4")],
            }
        ]

        lines = _build_lines(board, raw_info, multipv=1)

        self.assertEqual(len(lines), 1)
        self.assertIsNone(lines[0].cp)
        self.assertEqual(lines[0].mate, 3)

    def test_stream_returns_error_when_stockfish_missing(self) -> None:
        params = StockfishStreamRequest(fen=chess.STARTING_FEN, multipv=5, min_depth=6, max_depth=8)

        with patch("app.chess.services.analysis_stream._resolve_stockfish_path", return_value=None):
            events = list(stream_stockfish_analysis(params))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "analysis_error")
        self.assertEqual(events[0]["code"], "stockfish_unavailable")

    def test_stream_returns_engine_busy_when_slot_wait_times_out(self) -> None:
        params = StockfishStreamRequest(fen=chess.STARTING_FEN, multipv=5, min_depth=6, max_depth=8)

        with patch(
            "app.chess.services.analysis_stream._resolve_stockfish_path",
            return_value="/usr/bin/stockfish",
        ), patch("app.chess.services.analysis_stream._ANALYSIS_LIMITER.acquire", return_value=(False, 8, 1500)):
            events = list(stream_stockfish_analysis(params))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "analysis_error")
        self.assertEqual(events[0]["code"], "engine_busy")
        self.assertTrue(events[0]["retryable"])

    def test_stream_emits_consecutive_top_five_updates_with_scores(self) -> None:
        def info_line(rank: int, uci: str, cp: int, depth: int, nps: int, nodes: int):
            return {
                "multipv": rank,
                "score": chess.engine.PovScore(chess.engine.Cp(cp), chess.WHITE),
                "pv": [chess.Move.from_uci(uci)],
                "depth": depth,
                "seldepth": depth + 2,
                "nps": nps,
                "nodes": nodes,
            }

        first_read = [
            info_line(1, "e2e4", 38, depth=6, nps=100_000, nodes=20_000),
            info_line(2, "d2d4", 30, depth=6, nps=100_000, nodes=20_000),
            info_line(3, "c2c4", 24, depth=6, nps=100_000, nodes=20_000),
            info_line(4, "g1f3", 19, depth=6, nps=100_000, nodes=20_000),
            info_line(5, "b1c3", 15, depth=6, nps=100_000, nodes=20_000),
        ]
        second_read = [
            info_line(1, "e2e4", 42, depth=7, nps=120_000, nodes=26_000),
            info_line(2, "d2d4", 34, depth=7, nps=120_000, nodes=26_000),
            info_line(3, "c2c4", 29, depth=7, nps=120_000, nodes=26_000),
            info_line(4, "f2f4", 21, depth=7, nps=120_000, nodes=26_000),
            info_line(5, "g1f3", 18, depth=7, nps=120_000, nodes=26_000),
        ]

        class FakeEngine:
            def __init__(self) -> None:
                self.reads = [first_read, second_read]
                self.index = 0

            def analyse(self, board, limit, multipv, info):
                self.assert_is_starting_board(board)
                assert multipv == 5
                result = self.reads[self.index]
                self.index += 1
                return result

            @staticmethod
            def assert_is_starting_board(board: chess.Board) -> None:
                assert board.board_fen() == chess.Board().board_fen()

        params = StockfishStreamRequest(
            fen=chess.STARTING_FEN,
            multipv=5,
            min_depth=6,
            max_depth=7,
            depth_step=1,
            throttle_ms=25,
        )

        with patch("app.chess.services.analysis_stream._resolve_stockfish_path", return_value="/usr/bin/stockfish"), patch(
            "app.chess.services.analysis_stream.chess.engine.SimpleEngine.popen_uci",
            return_value=FakeEngine(),
        ), patch("app.chess.services.analysis_stream.time.sleep", return_value=None):
            events = list(stream_stockfish_analysis(params))

        self.assertEqual([event["type"] for event in events], ["depth_update", "depth_update", "analysis_complete"])
        first_update = events[0]
        second_update = events[1]
        complete = events[2]

        self.assertEqual(first_update["multipv"], 5)
        self.assertEqual(second_update["multipv"], 5)
        self.assertEqual(first_update["depth"], 6)
        self.assertEqual(second_update["depth"], 7)
        self.assertEqual(len(first_update["lines"]), 5)
        self.assertEqual(len(second_update["lines"]), 5)
        self.assertEqual([line["rank"] for line in second_update["lines"]], [1, 2, 3, 4, 5])
        self.assertEqual(first_update["lines"][0]["arrow"]["uci"], "e2e4")
        self.assertEqual(first_update["lines"][0]["cp"], 38)
        self.assertEqual(second_update["lines"][3]["arrow"]["uci"], "f2f4")
        self.assertEqual(second_update["lines"][3]["cp"], 21)
        self.assertNotIn("b1c3", [line["arrow"]["uci"] for line in second_update["lines"]])

        self.assertEqual(complete["bestmove_uci"], second_update["bestmove_uci"])
        self.assertEqual(complete["lines"], second_update["lines"])

    def test_stream_reuses_worker_engine_between_requests(self) -> None:
        class FakeEngine:
            def analyse(self, board, limit, multipv, info):
                del limit, multipv, info
                assert board.board_fen() == chess.Board().board_fen()
                return [
                    {
                        "multipv": 1,
                        "score": chess.engine.PovScore(chess.engine.Cp(12), chess.WHITE),
                        "pv": [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")],
                        "depth": 8,
                        "seldepth": 10,
                        "nps": 200_000,
                        "nodes": 50_000,
                    }
                ]

            def quit(self):
                return None

        params = StockfishStreamRequest(
            fen=chess.STARTING_FEN,
            multipv=1,
            min_depth=8,
            max_depth=8,
            depth_step=1,
            throttle_ms=25,
        )
        fake_pool = analysis_stream_module._StockfishWorkerPool(1)
        created_engines: list[FakeEngine] = []

        def fake_popen(_path: str) -> FakeEngine:
            engine = FakeEngine()
            created_engines.append(engine)
            return engine

        with patch("app.chess.services.analysis_stream._ENGINE_POOL", fake_pool), patch(
            "app.chess.services.analysis_stream._resolve_stockfish_path",
            return_value="/usr/bin/stockfish",
        ), patch(
            "app.chess.services.analysis_stream.chess.engine.SimpleEngine.popen_uci",
            side_effect=fake_popen,
        ):
            first_events = list(stream_stockfish_analysis(params))
            second_events = list(stream_stockfish_analysis(params))

        self.assertEqual(len(created_engines), 1)
        self.assertEqual(first_events[-1]["type"], "analysis_complete")
        self.assertEqual(second_events[-1]["type"], "analysis_complete")


if __name__ == "__main__":
    unittest.main()
