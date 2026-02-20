from __future__ import annotations

import atexit
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import chess
import chess.engine

from app.chess.schemas.api import (
    StockfishAnalysisCompleteEvent,
    StockfishAnalysisErrorEvent,
    StockfishArrow,
    StockfishDepthUpdateEvent,
    StockfishPVLine,
    StockfishStreamRequest,
)
from app.core.config import settings


@dataclass
class _AnalysisLimiter:
    max_concurrent: int
    _inflight: int = 0

    def __post_init__(self) -> None:
        self.max_concurrent = max(1, self.max_concurrent)
        self._condition = threading.Condition()

    def acquire(self, timeout_ms: int) -> tuple[bool, int, int]:
        started_at = time.monotonic()
        timeout_sec = max(timeout_ms, 0) / 1000.0
        deadline = started_at + timeout_sec

        with self._condition:
            while self._inflight >= self.max_concurrent:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    waited_ms = int((time.monotonic() - started_at) * 1000)
                    return False, self._inflight, waited_ms
                self._condition.wait(timeout=remaining)

            self._inflight += 1
            waited_ms = int((time.monotonic() - started_at) * 1000)
            return True, self._inflight, waited_ms

    def release(self) -> None:
        with self._condition:
            if self._inflight > 0:
                self._inflight -= 1
            self._condition.notify()


_ANALYSIS_LIMITER = _AnalysisLimiter(settings.STOCKFISH_MAX_CONCURRENT_STREAMS)


@dataclass
class _StockfishWorkerPool:
    max_workers: int
    _created: int = 0
    _idle: list[chess.engine.SimpleEngine] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.max_workers = max(1, self.max_workers)
        self._condition = threading.Condition()

    def acquire(self, engine_path: str) -> chess.engine.SimpleEngine:
        with self._condition:
            if self._idle:
                return self._idle.pop()
            if self._created >= self.max_workers:
                raise RuntimeError("stockfish pool exhausted")
            self._created += 1

        try:
            return chess.engine.SimpleEngine.popen_uci(engine_path)
        except Exception:
            with self._condition:
                if self._created > 0:
                    self._created -= 1
                self._condition.notify()
            raise

    def release(self, engine: chess.engine.SimpleEngine, *, discard: bool = False) -> None:
        if discard:
            try:
                engine.quit()
            except Exception:
                pass
            with self._condition:
                if self._created > 0:
                    self._created -= 1
                self._condition.notify()
            return

        with self._condition:
            self._idle.append(engine)
            self._condition.notify()

    def close_idle(self) -> None:
        with self._condition:
            idle = self._idle
            self._idle = []
            self._created = max(0, self._created - len(idle))
            self._condition.notify_all()

        for engine in idle:
            try:
                engine.quit()
            except Exception:
                pass


_ENGINE_POOL = _StockfishWorkerPool(settings.STOCKFISH_MAX_CONCURRENT_STREAMS)
atexit.register(_ENGINE_POOL.close_idle)


def _side_to_move(board: chess.Board) -> str:
    return "white" if board.turn == chess.WHITE else "black"


def _resolve_stockfish_path() -> str | None:
    configured = settings.STOCKFISH_PATH.strip() if settings.STOCKFISH_PATH else ""
    if configured:
        candidate = Path(configured).expanduser()
        return str(candidate) if candidate.exists() else configured
    return shutil.which("stockfish")


def _score_to_cp_mate(score: Any, turn: chess.Color) -> tuple[int | None, int | None]:
    if score is None:
        return None, None
    try:
        pov = score.pov(turn)
    except Exception:
        return None, None
    if pov.is_mate():
        return None, pov.mate()
    return pov.score(), None


def _extract_info_lines(raw_info: Any) -> list[dict[str, Any]]:
    if isinstance(raw_info, dict):
        return [raw_info]
    if isinstance(raw_info, list):
        return [item for item in raw_info if isinstance(item, dict)]
    return []


def _analysis_info_mask() -> chess.engine.Info:
    return chess.engine.INFO_BASIC | chess.engine.INFO_SCORE | chess.engine.INFO_PV


def _top_info(raw_info: Any) -> dict[str, Any]:
    lines = _extract_info_lines(raw_info)
    if not lines:
        return {}
    indexed = list(enumerate(lines, start=1))
    ordered = sorted(
        indexed,
        key=lambda item: item[1].get("multipv")
        if isinstance(item[1].get("multipv"), int)
        else item[0],
    )
    return ordered[0][1]


def _effective_analysis_budget(
    params: StockfishStreamRequest,
    inflight: int,
) -> tuple[int, int]:
    if _ANALYSIS_LIMITER.max_concurrent <= 0:
        return params.multipv, params.max_depth

    load_pct = (inflight / _ANALYSIS_LIMITER.max_concurrent) * 100
    if load_pct < settings.STOCKFISH_LOAD_SHED_PCT:
        return params.multipv, params.max_depth

    capped_multipv = min(params.multipv, max(1, settings.STOCKFISH_LOAD_SHED_MULTIPV))
    capped_max_depth = min(
        params.max_depth,
        max(params.min_depth, settings.STOCKFISH_LOAD_SHED_MAX_DEPTH),
    )
    return capped_multipv, capped_max_depth


def _depth_event(
    *,
    analysis_id: str,
    fen: str,
    board: chess.Board,
    depth: int,
    seldepth: Any,
    multipv: int,
    nps: Any,
    nodes: Any,
    bestmove_uci: str | None,
    lines: list[StockfishPVLine],
) -> dict:
    return StockfishDepthUpdateEvent(
        analysis_id=analysis_id,
        fen=fen,
        side_to_move=_side_to_move(board),
        depth=depth,
        seldepth=seldepth if isinstance(seldepth, int) else None,
        multipv=multipv,
        nps=nps if isinstance(nps, int) else None,
        nodes=nodes if isinstance(nodes, int) else None,
        bestmove_uci=bestmove_uci,
        lines=lines,
        generated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")


def _build_lines(board: chess.Board, raw_info: Any, multipv: int) -> list[StockfishPVLine]:
    infos = _extract_info_lines(raw_info)
    if not infos:
        return []

    def _rank(info: dict[str, Any], fallback_index: int) -> int:
        value = info.get("multipv")
        if isinstance(value, int) and value >= 1:
            return value
        return fallback_index

    indexed = list(enumerate(infos, start=1))
    ordered = [info for _, info in sorted(indexed, key=lambda item: _rank(item[1], item[0]))]

    lines: list[StockfishPVLine] = []
    seen_uci: set[str] = set()
    next_rank = 1
    for info in ordered:
        if next_rank > multipv:
            break
        pv_moves = info.get("pv")
        if not isinstance(pv_moves, list) or not pv_moves:
            continue
        top_move = pv_moves[0]
        if not isinstance(top_move, chess.Move):
            continue

        uci = top_move.uci()
        if uci in seen_uci:
            continue
        seen_uci.add(uci)
        cp, mate = _score_to_cp_mate(info.get("score"), board.turn)
        try:
            san = board.san(top_move)
        except Exception:
            san = uci

        pv_uci = [move.uci() for move in pv_moves if isinstance(move, chess.Move)]
        lines.append(
            StockfishPVLine(
                rank=next_rank,
                arrow=StockfishArrow(
                    uci=uci,
                    from_square=uci[:2],
                    to_square=uci[2:4],
                    color_slot=next_rank,
                ),
                san=san,
                cp=cp,
                mate=mate,
                pv=pv_uci,
            )
        )
        next_rank += 1
    return lines


def _stream_with_legacy_depth_loop(
    *,
    engine: Any,
    board: chess.Board,
    params: StockfishStreamRequest,
    analysis_id: str,
    multipv: int,
    max_depth: int,
    stop_event: threading.Event | None,
) -> Iterator[dict]:
    started_at = time.monotonic()
    last_emit_at = 0.0
    last_depth = params.min_depth
    last_lines: list[StockfishPVLine] = []
    last_bestmove: str | None = None
    reason: str = "depth_reached"

    depth = params.min_depth
    while depth <= max_depth:
        if stop_event is not None and stop_event.is_set():
            reason = "client_cancelled"
            break

        remaining_sec: float | None = None
        if params.movetime_ms is not None:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            remaining_ms = params.movetime_ms - elapsed_ms
            if remaining_ms <= 0:
                reason = "movetime_elapsed"
                break
            remaining_sec = max(remaining_ms / 1000.0, 0.01)

        limit = chess.engine.Limit(depth=depth, time=remaining_sec)
        raw_info = engine.analyse(
            board,
            limit=limit,
            multipv=multipv,
            info=_analysis_info_mask(),
        )
        lines = _build_lines(board, raw_info, multipv)
        bestmove_uci = lines[0].arrow.uci if lines else None

        top_info = _top_info(raw_info)
        info_depth = top_info.get("depth")
        current_depth = info_depth if isinstance(info_depth, int) and info_depth > 0 else depth
        current_depth = min(current_depth, max_depth)

        last_depth = current_depth
        last_lines = lines
        last_bestmove = bestmove_uci

        now = time.monotonic()
        elapsed_since_emit_ms = (now - last_emit_at) * 1000 if last_emit_at else params.throttle_ms
        if elapsed_since_emit_ms < params.throttle_ms:
            sleep_sec = (params.throttle_ms - elapsed_since_emit_ms) / 1000
            time.sleep(max(sleep_sec, 0))

        last_emit_at = time.monotonic()
        yield _depth_event(
            analysis_id=analysis_id,
            fen=params.fen,
            board=board,
            depth=current_depth,
            seldepth=top_info.get("seldepth"),
            multipv=multipv,
            nps=top_info.get("nps"),
            nodes=top_info.get("nodes"),
            bestmove_uci=bestmove_uci,
            lines=lines,
        )
        depth += params.depth_step

    return last_depth, last_lines, last_bestmove, reason


def _stream_with_continuous_analysis(
    *,
    engine: Any,
    board: chess.Board,
    params: StockfishStreamRequest,
    analysis_id: str,
    multipv: int,
    max_depth: int,
    stop_event: threading.Event | None,
) -> Iterator[dict]:
    time_limit_sec = params.movetime_ms / 1000.0 if params.movetime_ms is not None else None
    limit = chess.engine.Limit(depth=max_depth, time=time_limit_sec)

    last_depth = params.min_depth
    last_lines: list[StockfishPVLine] = []
    last_bestmove: str | None = None
    reason: str = "engine_stopped"
    last_emit_at = 0.0
    next_emit_depth = params.min_depth

    info_by_rank: dict[int, dict[str, Any]] = {}

    with engine.analysis(
        board,
        limit=limit,
        multipv=multipv,
        info=_analysis_info_mask(),
    ) as analysis_result:
        for raw_info in analysis_result:
            if stop_event is not None and stop_event.is_set():
                reason = "client_cancelled"
                analysis_result.stop()
                break

            if not isinstance(raw_info, dict):
                continue

            rank = raw_info.get("multipv")
            rank_index = rank if isinstance(rank, int) and rank >= 1 else 1
            info_by_rank[rank_index] = raw_info

            top_info = info_by_rank.get(1) or raw_info
            info_depth = top_info.get("depth")
            if not isinstance(info_depth, int) or info_depth <= 0:
                continue

            current_depth = min(info_depth, max_depth)
            if current_depth < next_emit_depth:
                continue

            now = time.monotonic()
            elapsed_since_emit_ms = (now - last_emit_at) * 1000 if last_emit_at else params.throttle_ms
            if elapsed_since_emit_ms < params.throttle_ms and current_depth < max_depth:
                continue

            latest_lines = [info_by_rank[index] for index in sorted(info_by_rank.keys())]
            lines = _build_lines(board, latest_lines, multipv)
            if not lines:
                continue

            bestmove_uci = lines[0].arrow.uci if lines else None
            while next_emit_depth <= current_depth and next_emit_depth <= max_depth:
                last_depth = next_emit_depth
                last_lines = lines
                last_bestmove = bestmove_uci
                last_emit_at = time.monotonic()
                yield _depth_event(
                    analysis_id=analysis_id,
                    fen=params.fen,
                    board=board,
                    depth=next_emit_depth,
                    seldepth=top_info.get("seldepth"),
                    multipv=multipv,
                    nps=top_info.get("nps"),
                    nodes=top_info.get("nodes"),
                    bestmove_uci=bestmove_uci,
                    lines=lines,
                )
                next_emit_depth += params.depth_step

            if next_emit_depth > max_depth:
                reason = "depth_reached"
                analysis_result.stop()
                break

    if reason == "engine_stopped":
        if stop_event is not None and stop_event.is_set():
            reason = "client_cancelled"
        elif params.movetime_ms is not None and last_depth < max_depth:
            reason = "movetime_elapsed"
        elif last_depth >= max_depth:
            reason = "depth_reached"

    return last_depth, last_lines, last_bestmove, reason


def stream_stockfish_analysis(
    params: StockfishStreamRequest,
    stop_event: threading.Event | None = None,
) -> Iterator[dict]:
    """Yield incremental MultiPV depth updates from Stockfish for SSE consumers."""
    analysis_id = f"analysis-{uuid.uuid4().hex[:12]}"

    try:
        board = chess.Board(params.fen)
    except ValueError as exc:
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="invalid_fen",
            message=str(exc),
            retryable=False,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return

    stockfish_path = _resolve_stockfish_path()
    if not stockfish_path:
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="stockfish_unavailable",
            message="Stockfish binary not found. Set STOCKFISH_PATH or install stockfish in PATH.",
            retryable=True,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return

    acquired, inflight, waited_ms = _ANALYSIS_LIMITER.acquire(
        settings.STOCKFISH_QUEUE_TIMEOUT_MS
    )
    if not acquired:
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="engine_busy",
            message=(
                "Analysis capacity is currently full. "
                f"Timed out after waiting {waited_ms}ms for an engine slot."
            ),
            retryable=True,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return

    engine: chess.engine.SimpleEngine | None = None
    discard_engine = False
    try:
        engine = _ENGINE_POOL.acquire(stockfish_path)
        if not hasattr(engine, "analysis") and not hasattr(engine, "analyse"):
            raise RuntimeError("stockfish engine does not expose analysis methods")

        effective_multipv, effective_max_depth = _effective_analysis_budget(
            params,
            inflight,
        )
        if hasattr(engine, "analysis") and callable(getattr(engine, "analysis")):
            last_depth, last_lines, last_bestmove, reason = yield from _stream_with_continuous_analysis(
                engine=engine,
                board=board,
                params=params,
                analysis_id=analysis_id,
                multipv=effective_multipv,
                max_depth=effective_max_depth,
                stop_event=stop_event,
            )
        else:
            last_depth, last_lines, last_bestmove, reason = yield from _stream_with_legacy_depth_loop(
                engine=engine,
                board=board,
                params=params,
                analysis_id=analysis_id,
                multipv=effective_multipv,
                max_depth=effective_max_depth,
                stop_event=stop_event,
            )
    except chess.engine.EngineError as exc:
        discard_engine = True
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="engine_error",
            message=str(exc),
            retryable=True,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return
    except FileNotFoundError as exc:
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="stockfish_not_found",
            message=str(exc),
            retryable=True,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return
    except Exception as exc:
        yield StockfishAnalysisErrorEvent(
            analysis_id=analysis_id,
            code="stream_failed",
            message=str(exc),
            retryable=False,
            generated_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        return
    finally:
        if engine is not None:
            _ENGINE_POOL.release(engine, discard=discard_engine)
        _ANALYSIS_LIMITER.release()

    if stop_event is not None and stop_event.is_set():
        reason = "client_cancelled"

    yield StockfishAnalysisCompleteEvent(
        analysis_id=analysis_id,
        fen=params.fen,
        final_depth=last_depth,
        bestmove_uci=last_bestmove,
        lines=last_lines,
        reason=reason,
        generated_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
