from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.chess.services.openings import (
    clear_opening_index_cache,
    lookup_opening,
    lookup_opening_by_moves,
)
from tests.chess.auth import disable_auth_override, enable_auth_override


SAMPLE_TSV = "\n".join(
    [
        "C20\tKing's Pawn Game\t1. e4\te2e4\trnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -",
        "C50\tItalian Game\t1. e4 e5 2. Nf3 Nc6 3. Bc4\te2e4 e7e5 g1f3 b8c6 f1c4\tr1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq -",
        "C60\tRuy Lopez\t1. e4 e5 2. Nf3 Nc6 3. Bb5\te2e4 e7e5 g1f3 b8c6 f1b5\tr1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq -",
    ]
)


class OpeningLookupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.openings_dir = Path(self.tmpdir.name)
        (self.openings_dir / "c.tsv").write_text(SAMPLE_TSV + "\n", encoding="utf-8")
        os.environ["OPENINGS_DB_DIR"] = self.tmpdir.name
        clear_opening_index_cache()

    def tearDown(self) -> None:
        clear_opening_index_cache()
        os.environ.pop("OPENINGS_DB_DIR", None)
        self.tmpdir.cleanup()

    def test_lookup_opening_returns_longest_prefix_match(self) -> None:
        match = lookup_opening_by_moves(
            ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "g8f6"]
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.eco, "C50")
        self.assertEqual(match.name, "Italian Game")
        self.assertEqual(match.ply, 5)

    def test_lookup_opening_returns_none_for_non_standard_start_fen(self) -> None:
        match = lookup_opening_by_moves(
            ["e2e4", "e7e5"],
            initial_fen="8/8/8/8/8/8/8/8 w - - 0 1",
        )
        self.assertIsNone(match)


class OpeningLookupApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.openings_dir = Path(self.tmpdir.name)
        (self.openings_dir / "c.tsv").write_text(SAMPLE_TSV + "\n", encoding="utf-8")
        os.environ["OPENINGS_DB_DIR"] = self.tmpdir.name
        clear_opening_index_cache()
        enable_auth_override()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        disable_auth_override()
        clear_opening_index_cache()
        os.environ.pop("OPENINGS_DB_DIR", None)
        self.tmpdir.cleanup()

    def test_lookup_endpoint_accepts_space_separated_move_string(self) -> None:
        response = self.client.post(
            "/api/v1/chess/openings/lookup",
            json={"moves": "e2e4 e7e5 g1f3 b8c6 f1b5"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["matched"])
        self.assertEqual(body["opening"]["eco"], "C60")
        self.assertEqual(body["opening"]["name"], "Ruy Lopez")

    def test_lookup_endpoint_returns_unmatched_for_unknown_line(self) -> None:
        response = self.client.post(
            "/api/v1/chess/openings/lookup",
            json={"moves": ["d2d4", "g8f6"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["matched"])
        self.assertIsNone(body["opening"])

    def test_lookup_endpoint_returns_continuation_arrows(self) -> None:
        response = self.client.post(
            "/api/v1/chess/openings/lookup",
            json={"moves": ["e2e4", "e7e5", "g1f3", "b8c6"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["matched"])
        continuations = body["continuations"]
        self.assertEqual(len(continuations), 2)
        self.assertEqual(continuations[0]["uci"], "f1b5")
        self.assertEqual(continuations[0]["from_square"], "f1")
        self.assertEqual(continuations[0]["to_square"], "b5")
        self.assertEqual(continuations[0]["rank"], 1)
        self.assertEqual(continuations[0]["color_slot"], 1)
        self.assertEqual(continuations[1]["uci"], "f1c4")
        self.assertEqual(body["database"]["source"], "full")


class OpeningLookupFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        os.environ["OPENINGS_DB_DIR"] = self.tmpdir.name
        clear_opening_index_cache()

    def tearDown(self) -> None:
        clear_opening_index_cache()
        os.environ.pop("OPENINGS_DB_DIR", None)
        self.tmpdir.cleanup()

    def test_lookup_falls_back_to_starter_dataset_when_override_is_empty(self) -> None:
        match = lookup_opening_by_moves(["d2d4", "d7d5", "c2c4"])
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.eco, "D06")
        self.assertEqual(match.name, "Queen's Gambit")

    def test_lookup_metadata_reports_starter_source(self) -> None:
        result = lookup_opening(["d2d4", "d7d5", "c2c4"])
        self.assertEqual(result.database.source, "starter")
        self.assertGreaterEqual(result.database.file_count, 1)
        self.assertGreaterEqual(len(result.continuations), 1)


class OpeningLookupPgnOnlyTsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.openings_dir = Path(self.tmpdir.name)
        (self.openings_dir / "d.tsv").write_text(
            "\n".join(
                [
                    "D30\tQueen's Gambit Declined\t1. d4 d5 2. c4 e6",
                    "D31\tQueen's Gambit Declined: Semi-Slav setup\t1. d4 d5 2. c4 e6 3. Nc3",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["OPENINGS_DB_DIR"] = self.tmpdir.name
        clear_opening_index_cache()

    def tearDown(self) -> None:
        clear_opening_index_cache()
        os.environ.pop("OPENINGS_DB_DIR", None)
        self.tmpdir.cleanup()

    def test_lookup_parses_pgn_only_tsv_rows(self) -> None:
        result = lookup_opening(["d2d4", "d7d5", "c2c4", "e7e6"])
        self.assertIsNotNone(result.match)
        assert result.match is not None
        self.assertEqual(result.match.eco, "D30")
        self.assertEqual(result.database.source, "full")
        self.assertEqual(len(result.continuations), 1)
        self.assertEqual(result.continuations[0].uci, "b1c3")


if __name__ == "__main__":
    unittest.main()
