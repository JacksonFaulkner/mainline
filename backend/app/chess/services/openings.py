from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
from typing import Literal

import chess

from app.chess.schemas.api import (
    OpeningContinuation,
    OpeningDatabaseInfo,
    OpeningMatch,
)
from app.core.config import settings


STANDARD_START_FEN_PREFIX = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR"
DEFAULT_OPENINGS_DB_DIR = Path(__file__).resolve().parents[2] / "data" / "chess-openings"
STARTER_OPENINGS_FILE = DEFAULT_OPENINGS_DB_DIR / "starter.tsv"
_PGN_MOVE_NUMBER_PATTERN = re.compile(r"^\d+\.(?:\.\.)?$")
_PGN_COMMENT_PATTERN = re.compile(r"\{[^}]*\}")
_PGN_NAG_PATTERN = re.compile(r"\$\d+")
_PGN_VARIATION_PATTERN = re.compile(r"\([^)]*\)")
_PGN_ANNOTATION_PATTERN = re.compile(r"[!?]+")


@dataclass(frozen=True)
class OpeningLine:
    eco: str
    name: str
    pgn: str | None
    uci: str | None
    epd: str | None
    moves: tuple[str, ...]


@dataclass(frozen=True)
class OpeningLookupResult:
    match: OpeningMatch | None
    continuations: list[OpeningContinuation]
    database: OpeningDatabaseInfo


class _TrieNode(dict[str, "_TrieNode"]):
    line: OpeningLine | None
    sample_line: OpeningLine | None
    branch_size: int

    def __init__(self) -> None:
        super().__init__()
        self.line = None
        self.sample_line = None
        self.branch_size = 0


def _resolve_openings_dir(openings_dir: str | Path | None) -> Path:
    if openings_dir is not None:
        return Path(openings_dir)
    if settings.OPENINGS_DB_DIR:
        return Path(settings.OPENINGS_DB_DIR)
    configured = os.getenv("OPENINGS_DB_DIR")
    if configured:
        return Path(configured)
    return DEFAULT_OPENINGS_DB_DIR


def _parse_opening_line(raw: str) -> OpeningLine | None:
    line = raw.strip()
    if not line:
        return None
    parts = line.split("\t")
    if len(parts) < 3:
        return None

    eco, name, pgn = parts[0], parts[1], parts[2]
    uci = parts[3] if len(parts) > 3 else ""
    epd = parts[4] if len(parts) > 4 else None
    uci_moves = tuple(move for move in uci.split() if move)
    if not uci_moves and pgn:
        uci_moves = _uci_moves_from_pgn(pgn)
    if not eco or not name or not uci_moves:
        return None
    return OpeningLine(
        eco=eco,
        name=name,
        pgn=pgn or None,
        uci=uci or None,
        epd=epd or None,
        moves=uci_moves,
    )


def _uci_moves_from_pgn(pgn: str) -> tuple[str, ...]:
    cleaned = _PGN_COMMENT_PATTERN.sub(" ", pgn)
    cleaned = _PGN_VARIATION_PATTERN.sub(" ", cleaned)
    cleaned = _PGN_NAG_PATTERN.sub(" ", cleaned)
    tokens = [token.strip() for token in cleaned.split() if token.strip()]
    board = chess.Board()
    moves: list[str] = []

    for token in tokens:
        if token in {"*", "1-0", "0-1", "1/2-1/2"}:
            break
        if _PGN_MOVE_NUMBER_PATTERN.match(token):
            continue
        san = _PGN_ANNOTATION_PATTERN.sub("", token)
        try:
            move = board.parse_san(san)
        except ValueError:
            return ()
        moves.append(move.uci())
        board.push(move)
    return tuple(moves)


def _build_index(openings_path: Path) -> _TrieNode:
    root = _TrieNode()
    root_files, _ = _resolve_tsv_files(openings_path)
    for tsv_path in root_files:
        for raw in tsv_path.read_text(encoding="utf-8").splitlines():
            line = _parse_opening_line(raw)
            if line is None:
                continue
            node = root
            node.branch_size += 1
            if node.sample_line is None:
                node.sample_line = line
            for move in line.moves:
                next_node = node.get(move)
                if next_node is None:
                    next_node = _TrieNode()
                    node[move] = next_node
                node = next_node
                node.branch_size += 1
                if node.sample_line is None:
                    node.sample_line = line
            if node.line is None:
                node.line = line
    return root


def _compute_cache_stamp(openings_path: Path) -> str:
    stamp_parts: list[str] = []
    files, source = _resolve_tsv_files(openings_path)
    stamp_parts.append(f"source:{source}")
    for tsv_path in files:
        stat = tsv_path.stat()
        stamp_parts.append(f"{tsv_path.name}:{stat.st_size}:{stat.st_mtime_ns}")
    return "|".join(stamp_parts) or "empty"


def _resolve_tsv_files(openings_path: Path) -> tuple[list[Path], Literal["missing", "starter", "full"]]:
    if openings_path.exists() and openings_path.is_dir():
        files = sorted(openings_path.glob("*.tsv"))
        if files:
            non_starter_files = [path for path in files if path.name != STARTER_OPENINGS_FILE.name]
            if non_starter_files:
                return non_starter_files, "full"
            return files, "starter"
    if STARTER_OPENINGS_FILE.exists():
        return [STARTER_OPENINGS_FILE], "starter"
    return [], "missing"


@lru_cache(maxsize=8)
def _get_index_cached(openings_path: str, cache_stamp: str) -> _TrieNode:
    _ = cache_stamp
    return _build_index(Path(openings_path))


def clear_opening_index_cache() -> None:
    _get_index_cached.cache_clear()


def _to_opening_match(line: OpeningLine) -> OpeningMatch:
    return OpeningMatch(
        eco=line.eco,
        name=line.name,
        ply=len(line.moves),
        pgn=line.pgn,
        uci=line.uci,
        epd=line.epd,
    )


def _traverse_line(root: _TrieNode, moves: list[str]) -> tuple[_TrieNode, OpeningLine | None, bool]:
    node = root
    best: OpeningLine | None = None
    for move in moves:
        next_node = node.get(move)
        if next_node is None:
            return node, best, False
        node = next_node
        if node.line is not None:
            best = node.line
    return node, best, True


def _build_continuations(node: _TrieNode, *, max_continuations: int) -> list[OpeningContinuation]:
    if max_continuations <= 0:
        return []

    ranked: list[tuple[int, str, OpeningLine | None]] = []
    for move, child in node.items():
        ranked.append((child.branch_size, move, child.line or child.sample_line))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    continuations: list[OpeningContinuation] = []
    for rank, (_, move, representative) in enumerate(ranked[:max_continuations], start=1):
        continuations.append(
            OpeningContinuation(
                uci=move,
                from_square=move[:2],
                to_square=move[2:4],
                rank=rank,
                color_slot=rank,
                eco=representative.eco if representative else None,
                name=representative.name if representative else None,
                ply=len(representative.moves) if representative else None,
                pgn=representative.pgn if representative else None,
            )
        )
    return continuations


def lookup_opening(
    moves: list[str],
    initial_fen: str | None = None,
    openings_dir: str | Path | None = None,
    *,
    max_continuations: int = 5,
) -> OpeningLookupResult:
    openings_path = _resolve_openings_dir(openings_dir)
    files, source = _resolve_tsv_files(openings_path)
    if initial_fen and not initial_fen.strip().startswith(STANDARD_START_FEN_PREFIX):
        return OpeningLookupResult(
            match=None,
            continuations=[],
            database=OpeningDatabaseInfo(source=source, file_count=len(files)),
        )

    root = _get_index_cached(str(openings_path), _compute_cache_stamp(openings_path))
    node, best, fully_matched = _traverse_line(root, moves)
    continuations = _build_continuations(node, max_continuations=max_continuations) if fully_matched else []

    return OpeningLookupResult(
        match=_to_opening_match(best) if best else None,
        continuations=continuations,
        database=OpeningDatabaseInfo(source=source, file_count=len(files)),
    )


def lookup_opening_by_moves(
    moves: list[str],
    initial_fen: str | None = None,
    openings_dir: str | Path | None = None,
) -> OpeningMatch | None:
    return lookup_opening(
        moves,
        initial_fen=initial_fen,
        openings_dir=openings_dir,
        max_continuations=0,
    ).match
