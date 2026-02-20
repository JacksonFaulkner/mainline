from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

UCI_MOVE_PATTERN = r"^[a-h][1-8][a-h][1-8][nbrq]?$"


class APIModel(BaseModel):
    """Base model settings shared across API schemas."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ApiMessage(APIModel):
    """Simple success/failure response payload."""

    ok: bool = Field(description="Whether the request completed successfully.", default=True)
    message: str | None = Field(
        default=None,
        description="Optional human-readable status message.",
    )


class ApiError(APIModel):
    """Standardized downstream API error details."""

    error: str = Field(description="Primary error message.")
    status_code: int | None = Field(
        default=None,
        description="HTTP status code from the upstream source, if available.",
    )
    cause: dict[str, Any] | None = Field(
        default=None,
        description="Raw structured error payload returned by Lichess, if available.",
    )


class SeekRequest(APIModel):
    """Request body for creating a public seek."""

    minutes: int = Field(
        default=5,
        ge=1,
        le=180,
        description="Initial clock time in minutes.",
        examples=[5, 10, 15],
    )
    increment: int = Field(
        default=0,
        ge=0,
        le=180,
        description="Per-move increment in seconds.",
        examples=[0, 3, 5],
    )
    rated: bool = Field(
        default=False,
        description="Whether the seeked game should be rated.",
    )
    color: Literal["random", "white", "black"] = Field(
        default="random",
        description="Preferred color for the created game.",
    )
    variant: str = Field(
        default="standard",
        description="Lichess variant key (for example: standard, chess960).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "minutes": 10,
                "increment": 5,
                "rated": False,
                "color": "random",
                "variant": "standard",
            }
        }
    )


class SeekResponse(APIModel):
    """Response payload for seek creation."""

    ok: bool = Field(default=True, description="Whether seek registration succeeded.")
    queued: bool = Field(
        default=True,
        description="Whether a background seek process was started.",
    )
    requested: SeekRequest = Field(description="Echo of the request payload.")


class MoveRequest(APIModel):
    """Request body for posting a move in UCI notation."""

    uci: str = Field(
        min_length=4,
        max_length=5,
        pattern=UCI_MOVE_PATTERN,
        description="Move in UCI notation, e.g. e2e4 or e7e8q.",
        examples=["e2e4", "a7a8q"],
    )
    offering_draw: bool = Field(
        default=False,
        description="Whether to offer a draw alongside the move.",
    )

    @field_validator("uci", mode="before")
    @classmethod
    def normalize_uci(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        return value

    model_config = ConfigDict(
        json_schema_extra={"example": {"uci": "e2e4", "offering_draw": False}}
    )


class MoveResponse(APIModel):
    """Response payload for a move submission."""

    ok: bool = Field(default=True, description="Whether move submission succeeded.")
    game_id: str = Field(description="Lichess game id.")
    move: str = Field(description="Normalized UCI move that was submitted.")


def _normalize_uci_moves(value: object) -> list[str]:
    if isinstance(value, str):
        raw_moves = value.strip().split()
    elif isinstance(value, list):
        raw_moves = value
    else:
        raise ValueError("moves must be a space-separated string or a list of UCI moves")

    normalized: list[str] = []
    for move in raw_moves:
        if not isinstance(move, str):
            raise ValueError("moves must contain strings")
        candidate = move.strip().lower()
        if not re.match(UCI_MOVE_PATTERN, candidate):
            raise ValueError(f"invalid UCI move: {move}")
        normalized.append(candidate)
    return normalized


class OpeningMatch(APIModel):
    """Resolved opening metadata for a move sequence."""

    eco: str = Field(description="ECO code for the matched opening.")
    name: str = Field(description="Human-readable opening name.")
    ply: int = Field(description="Matched opening length in plies.")
    pgn: str | None = Field(default=None, description="Canonical PGN move sequence for the opening.")
    uci: str | None = Field(default=None, description="Canonical UCI move sequence for the opening.")
    epd: str | None = Field(default=None, description="Terminal EPD position for the opening line.")


class OpeningContinuation(APIModel):
    """Next candidate move from the current opening-book position."""

    uci: str = Field(
        min_length=4,
        max_length=5,
        pattern=UCI_MOVE_PATTERN,
        description="Continuation move in UCI notation.",
    )
    from_square: str = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[a-h][1-8]$",
        description="Source square for board arrow rendering.",
    )
    to_square: str = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[a-h][1-8]$",
        description="Destination square for board arrow rendering.",
    )
    rank: int = Field(ge=1, le=20, description="1-based ordering rank among continuations.")
    color_slot: int = Field(ge=1, le=20, description="Color slot index for stable arrow coloring.")
    eco: str | None = Field(default=None, description="Representative ECO code for this branch.")
    name: str | None = Field(default=None, description="Representative opening name for this branch.")
    ply: int | None = Field(default=None, description="Representative opening line ply for this branch.")
    pgn: str | None = Field(default=None, description="Representative PGN for this branch.")


class OpeningDatabaseInfo(APIModel):
    """Metadata about which opening dataset was used for lookup."""

    source: Literal["missing", "starter", "full"] = Field(
        description="Resolved opening source. 'full' means at least one non-starter TSV file was loaded."
    )
    file_count: int = Field(ge=0, description="Number of TSV files loaded for this lookup.")


class OpeningLookupRequest(APIModel):
    """Lookup payload for opening identification."""

    moves: list[str] = Field(
        default_factory=list,
        description="UCI moves as a list or space-separated string.",
    )
    initial_fen: str | None = Field(
        default=None,
        alias="initialFen",
        description="Optional starting FEN. Non-standard start positions are ignored.",
    )

    @field_validator("moves", mode="before")
    @classmethod
    def validate_moves(cls, value: object) -> list[str]:
        return _normalize_uci_moves(value)


class OpeningLookupResponse(APIModel):
    """Opening lookup result payload."""

    ok: bool = Field(default=True, description="Whether lookup completed.")
    matched: bool = Field(description="Whether an opening match was found.")
    opening: OpeningMatch | None = Field(
        default=None,
        description="Matched opening details, if found.",
    )
    continuations: list[OpeningContinuation] = Field(
        default_factory=list,
        description="Top opening-book continuation moves from the current line.",
    )
    database: OpeningDatabaseInfo = Field(
        description="Resolved opening dataset metadata for this lookup.",
    )


class EngineLine(APIModel):
    """Single engine principal-variation line."""

    pv: list[str] = Field(default_factory=list, description="Principal variation UCI moves.")
    cp: int | None = Field(default=None, description="Centipawn score from side to move.")
    mate: int | None = Field(default=None, description="Mate score in plies, if applicable.")


class GameAnalysisRequest(APIModel):
    """Optional overrides for analysis parameters."""

    fen: str | None = Field(default=None, description="Optional FEN override.")
    depth: int | None = Field(default=None, ge=1, le=40, description="Optional search depth.")
    movetime_ms: int | None = Field(
        default=None,
        ge=25,
        le=10_000,
        description="Optional fixed search time in milliseconds.",
    )
    multipv: int | None = Field(default=None, ge=1, le=10, description="Optional number of PV lines.")


class GameAnalysisResponse(APIModel):
    """Stockfish analysis payload for a game."""

    ok: bool = Field(default=True)
    game_id: str = Field(description="Lichess game id.")
    fen: str = Field(description="Analyzed position in FEN format.")
    side_to_move: Literal["white", "black"] = Field(description="Color to move in analyzed position.")
    bestmove: str | None = Field(default=None, description="Best move in UCI notation.")
    evaluation: EngineLine = Field(description="Primary evaluation line.")
    alternatives: list[EngineLine] = Field(default_factory=list, description="Additional PV lines.")
    analyzed_at: datetime = Field(description="UTC timestamp of analysis generation.")


class StockfishStreamRequest(APIModel):
    """Query contract for starting live Stockfish SSE analysis."""

    fen: str = Field(
        min_length=1,
        max_length=120,
        description="Target board position in FEN format.",
    )
    multipv: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of principal variations to stream (top-N moves).",
    )
    min_depth: int = Field(
        default=8,
        ge=1,
        le=60,
        description="Starting depth for incremental analysis stream.",
    )
    max_depth: int = Field(
        default=22,
        ge=1,
        le=60,
        description="Maximum depth before stream completion.",
    )
    depth_step: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Depth increment between streamed updates.",
    )
    movetime_ms: int | None = Field(
        default=None,
        ge=25,
        le=60_000,
        description="Optional fixed think time cap per streamed analysis request.",
    )
    throttle_ms: int = Field(
        default=200,
        ge=25,
        le=2_000,
        description="Minimum interval between depth update events.",
    )

    @field_validator("fen")
    @classmethod
    def normalize_fen(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("fen must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_depth_bounds(self) -> StockfishStreamRequest:
        if self.max_depth < self.min_depth:
            raise ValueError("max_depth must be >= min_depth")
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
                "multipv": 5,
                "min_depth": 8,
                "max_depth": 20,
                "depth_step": 1,
                "movetime_ms": 1200,
                "throttle_ms": 200,
            }
        }
    )


class StockfishArrow(APIModel):
    """Frontend-ready arrow descriptor for one candidate move."""

    uci: str = Field(
        min_length=4,
        max_length=5,
        pattern=UCI_MOVE_PATTERN,
        description="Candidate move in UCI notation.",
    )
    from_square: str = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[a-h][1-8]$",
        description="UCI origin square.",
    )
    to_square: str = Field(
        min_length=2,
        max_length=2,
        pattern=r"^[a-h][1-8]$",
        description="UCI target square.",
    )
    color_slot: int = Field(
        ge=1,
        le=10,
        description="Deterministic color slot index used by frontend to style arrows.",
    )


class StockfishPVLine(APIModel):
    """One streamed principal variation line."""

    rank: int = Field(default=1, ge=1, le=10, description="PV rank where 1 is best.")
    arrow: StockfishArrow = Field(description="Top move arrow info for this PV.")
    san: str | None = Field(default=None, description="Optional SAN for the top PV move.")
    cp: int | None = Field(default=None, description="Centipawn score from side to move.")
    mate: int | None = Field(default=None, description="Mate score in plies, if available.")
    pv: list[str] = Field(default_factory=list, description="Principal variation UCI sequence.")

    @field_validator("pv", mode="before")
    @classmethod
    def normalize_pv(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_uci_moves(value)


class StockfishDepthUpdateEvent(APIModel):
    """Incremental depth update event for SSE streaming analysis."""

    type: Literal["depth_update"] = "depth_update"
    analysis_id: str = Field(description="Server-generated analysis session id.")
    fen: str = Field(description="Analyzed position in FEN.")
    side_to_move: Literal["white", "black"] = Field(description="Side to move in analyzed position.")
    depth: int = Field(ge=1, le=60, description="Current completed depth for this update.")
    seldepth: int | None = Field(default=None, ge=1, le=80, description="Selective depth, if available.")
    multipv: int = Field(ge=1, le=10, description="Number of PV lines returned in this update.")
    nps: int | None = Field(default=None, ge=0, description="Nodes per second, if available.")
    nodes: int | None = Field(default=None, ge=0, description="Total searched nodes, if available.")
    bestmove_uci: str | None = Field(
        default=None,
        min_length=4,
        max_length=5,
        pattern=UCI_MOVE_PATTERN,
        description="Current best move in UCI notation.",
    )
    lines: list[StockfishPVLine] = Field(default_factory=list, description="Top principal variations.")
    generated_at: datetime = Field(description="UTC timestamp when this update was emitted.")


class StockfishAnalysisCompleteEvent(APIModel):
    """Final completion event for a live SSE analysis session."""

    type: Literal["analysis_complete"] = "analysis_complete"
    analysis_id: str = Field(description="Server-generated analysis session id.")
    fen: str = Field(description="Analyzed position in FEN.")
    final_depth: int = Field(ge=1, le=60, description="Last completed depth before completion.")
    bestmove_uci: str | None = Field(
        default=None,
        min_length=4,
        max_length=5,
        pattern=UCI_MOVE_PATTERN,
        description="Final best move in UCI notation.",
    )
    lines: list[StockfishPVLine] = Field(default_factory=list, description="Final top principal variations.")
    reason: Literal["depth_reached", "movetime_elapsed", "client_cancelled", "engine_stopped"] = Field(
        description="Terminal reason for stream completion."
    )
    generated_at: datetime = Field(description="UTC timestamp when completion event was emitted.")


class StockfishAnalysisErrorEvent(APIModel):
    """Error event for SSE analysis stream failures."""

    type: Literal["analysis_error"] = "analysis_error"
    analysis_id: str | None = Field(default=None, description="Analysis session id if available.")
    code: str = Field(description="Stable error code identifier.")
    message: str = Field(description="Human-readable error message.")
    retryable: bool = Field(default=False, description="Whether client may retry with same parameters.")
    generated_at: datetime = Field(description="UTC timestamp when error event was emitted.")


StockfishStreamEvent = Annotated[
    StockfishDepthUpdateEvent | StockfishAnalysisCompleteEvent | StockfishAnalysisErrorEvent,
    Field(discriminator="type"),
]


class CommentaryAnalysisStreamRequest(APIModel):
    """Query contract for starting live Commentary SSE commentary."""

    fen: str = Field(
        min_length=1,
        max_length=120,
        description="Target board position in FEN format.",
    )
    stockfish_context: str | None = Field(
        default=None,
        max_length=4000,
        description="Optional Stockfish summary string for grounding Commentary output.",
    )

    @field_validator("fen")
    @classmethod
    def normalize_fen(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("fen must not be empty")
        return normalized

    @field_validator("stockfish_context")
    @classmethod
    def normalize_stockfish_context(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CommentaryUsageStats(APIModel):
    """Optional Bedrock token usage stats attached to completion events."""

    input_tokens: int | None = Field(default=None, ge=0, description="Input token count, if available.")
    output_tokens: int | None = Field(default=None, ge=0, description="Output token count, if available.")
    total_tokens: int | None = Field(default=None, ge=0, description="Total token count, if available.")


class CommentaryTextDeltaEvent(APIModel):
    """Incremental text fragment emitted by Commentary stream."""

    type: Literal["commentary_text_delta"] = "commentary_text_delta"
    analysis_id: str = Field(description="Server-generated Commentary analysis session id.")
    text_delta: str = Field(description="New text fragment emitted for this chunk.")
    text: str = Field(description="Accumulated text received so far.")
    generated_at: datetime = Field(description="UTC timestamp when this text delta was emitted.")


class CommentaryConcreteIdea(APIModel):
    """Concrete line-based idea selected from Stockfish candidate branches."""

    title: str = Field(
        min_length=1,
        max_length=72,
        description="Short idea title for menu display.",
    )
    description: str = Field(
        min_length=1,
        max_length=320,
        description="Compact explanation of why this line matters.",
    )
    selected_line_id: str = Field(
        min_length=1,
        max_length=12,
        description="Identifier of selected Stockfish candidate line (for example: L01).",
    )
    playback_pv_uci: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Playable PV in UCI notation used by the UI Play action.",
    )

    @field_validator("title", "description", "selected_line_id")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("concrete idea text fields must not be empty")
        return normalized

    @field_validator("playback_pv_uci", mode="before")
    @classmethod
    def normalize_pv_uci(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for move in value:
            if isinstance(move, str):
                normalized.append(move.strip().lower())
            else:
                normalized.append("")
        return normalized

    @model_validator(mode="after")
    def validate_playback_moves(self) -> "CommentaryConcreteIdea":
        for move in self.playback_pv_uci:
            if not re.match(UCI_MOVE_PATTERN, move):
                raise ValueError("playback_pv_uci must contain valid UCI moves")
        return self


class CommentaryStructuredCommentary(APIModel):
    """Structured chess commentary payload validated from model JSON output."""

    position_plan_title: str = Field(
        min_length=1,
        max_length=48,
        description="Short plan title for this position, at most four words.",
    )
    advantage_side: Literal["white", "black", "equal", "unclear"] = Field(
        description="Which side is better in the current position."
    )
    advantage_summary: str = Field(
        min_length=1,
        max_length=320,
        description="Concise reason for the evaluation in plain language.",
    )
    best_move_san: str = Field(
        min_length=1,
        max_length=24,
        description="Recommended best move in SAN notation.",
    )
    best_move_reason: str = Field(
        min_length=1,
        max_length=240,
        description="Short tactical or strategic reason the best move works.",
    )
    danger_to_watch: str = Field(
        min_length=1,
        max_length=240,
        description="Main tactical or strategic danger in the next phase.",
    )
    white_plan: list[str] = Field(
        min_length=2,
        max_length=2,
        description="Exactly two bullet points describing White's plan.",
    )
    black_plan: list[str] = Field(
        min_length=2,
        max_length=2,
        description="Exactly two bullet points describing Black's plan.",
    )
    concrete_ideas: list[CommentaryConcreteIdea] = Field(
        min_length=1,
        max_length=2,
        description="One or two concrete line ideas selected from candidate Stockfish branches.",
    )

    @field_validator("position_plan_title")
    @classmethod
    def validate_position_plan_title(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("position_plan_title must not be empty")
        if len(normalized.split()) > 4:
            raise ValueError("position_plan_title must be less than 5 words")
        return normalized

    @field_validator("advantage_summary", "best_move_san", "best_move_reason", "danger_to_watch")
    @classmethod
    def normalize_text_fields(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("structured commentary fields must not be empty")
        return normalized

    @field_validator("white_plan", "black_plan", mode="before")
    @classmethod
    def normalize_side_plan(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        normalized: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                normalized.append("")
                continue
            cleaned = " ".join(entry.split())
            normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def validate_side_plan_bullets(self) -> "CommentaryStructuredCommentary":
        for side_name, plan in (("white_plan", self.white_plan), ("black_plan", self.black_plan)):
            if len(plan) != 2:
                raise ValueError(f"{side_name} must contain exactly 2 bullet points")
            for entry in plan:
                if not entry:
                    raise ValueError(f"{side_name} bullet points must not be empty")
        line_ids = [idea.selected_line_id for idea in self.concrete_ideas]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("concrete_ideas selected_line_id values must be unique")
        return self


class CommentaryAnalysisCompleteEvent(APIModel):
    """Final completion event for Commentary commentary stream."""

    type: Literal["commentary_complete"] = "commentary_complete"
    analysis_id: str = Field(description="Server-generated Commentary analysis session id.")
    text: str = Field(description="Final accumulated completion text.")
    structured: CommentaryStructuredCommentary | None = Field(
        default=None,
        description="Optional structured commentary parsed from model JSON output.",
    )
    stop_reason: str | None = Field(default=None, description="Provider stop reason, if available.")
    usage: CommentaryUsageStats | None = Field(default=None, description="Optional provider usage metrics.")
    latency_ms: int | None = Field(default=None, ge=0, description="Provider-reported latency in milliseconds.")
    generated_at: datetime = Field(description="UTC timestamp when stream completion was emitted.")


class CommentaryAnalysisErrorEvent(APIModel):
    """Error event for Commentary commentary stream failures."""

    type: Literal["commentary_error"] = "commentary_error"
    analysis_id: str | None = Field(default=None, description="Commentary analysis session id if available.")
    code: str = Field(description="Stable error code identifier.")
    message: str = Field(description="Human-readable error message.")
    retryable: bool = Field(default=False, description="Whether client may retry with same parameters.")
    generated_at: datetime = Field(description="UTC timestamp when error event was emitted.")


CommentaryAnalysisStreamEvent = Annotated[
    CommentaryTextDeltaEvent | CommentaryAnalysisCompleteEvent | CommentaryAnalysisErrorEvent,
    Field(discriminator="type"),
]


class PositionSnapshotRequest(APIModel):
    """Request body for persisting a board position snapshot."""

    fen: str = Field(
        min_length=1,
        max_length=120,
        description="Current board position in FEN format.",
    )
    moves: list[str] = Field(
        default_factory=list,
        description="Move list in normalized UCI notation.",
    )
    status: str | None = Field(
        default=None,
        description="Optional game status from the latest stream event.",
    )

    @field_validator("fen")
    @classmethod
    def normalize_fen(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("fen must not be empty")
        return normalized

    @field_validator("moves")
    @classmethod
    def validate_moves(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for move in value:
            if not isinstance(move, str):
                raise ValueError("moves must contain strings")
            candidate = move.strip().lower()
            if not re.match(UCI_MOVE_PATTERN, candidate):
                raise ValueError(f"invalid UCI move: {move}")
            normalized.append(candidate)
        return normalized

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
                "moves": ["e2e4"],
                "status": "started",
            }
        }
    )


class PositionSnapshotResponse(APIModel):
    """Response payload for persisted board snapshots."""

    ok: bool = Field(default=True)
    game_id: str = Field(description="Lichess game id.")
    fen: str = Field(description="Current board position in FEN format.")
    move_count: int = Field(description="Number of moves in the move list.")
    saved_at: datetime = Field(description="UTC timestamp of the persisted snapshot.")


class RecentGameSummary(APIModel):
    """Compact summary of a finished game for account history views."""

    game_id: str = Field(description="Lichess game id.")
    url: str = Field(description="Public Lichess game URL.")
    my_color: Literal["white", "black"] | None = Field(
        default=None,
        description="Authenticated player's color in this game.",
    )
    my_result: Literal["win", "loss", "draw", "unknown"] = Field(
        default="unknown",
        description="Outcome for the authenticated player.",
    )
    opponent_name: str | None = Field(default=None, description="Opponent username, if known.")
    opponent_rating: int | None = Field(default=None, description="Opponent rating, if available.")
    rated: bool | None = Field(default=None, description="Whether the game was rated.")
    speed: str | None = Field(default=None, description="Lichess speed key (blitz, rapid, etc).")
    perf: str | None = Field(default=None, description="Lichess performance category.")
    variant: str | None = Field(default=None, description="Variant key.")
    status: str | None = Field(default=None, description="Terminal status from Lichess.")
    winner: Literal["white", "black"] | None = Field(default=None, description="Winning side, if any.")
    created_at: datetime | None = Field(default=None, description="Game creation timestamp (UTC).")
    last_move_at: datetime | None = Field(default=None, description="Last move timestamp (UTC).")
    preview_fens: list[str] = Field(
        default_factory=list,
        description=(
            "FEN sequence for a compact last-phase preview. "
            "Includes the start position before the final window and one FEN per preview ply."
        ),
    )
    preview_sans: list[str] = Field(
        default_factory=list,
        description="SAN moves for the preview window (typically last 6 plies).",
    )


class RecentGamesResponse(APIModel):
    """Response payload for recent completed games."""

    ok: bool = Field(default=True)
    count: int = Field(description="Number of game summaries returned.")
    games: list[RecentGameSummary] = Field(
        default_factory=list,
        description="Most recent completed games for the authenticated account.",
    )


class ChallengeDeclineRequest(APIModel):
    """Request body for declining a challenge."""

    reason: str = Field(
        default="generic",
        description=(
            "Lichess decline reason key. Examples: generic, tooFast, tooSlow, casual,"
            " rated, later, standard, variant, noBot."
        ),
    )


class ChallengeActionResponse(APIModel):
    """Response payload for challenge accept/decline endpoints."""

    ok: bool = Field(default=True)
    challenge_id: str = Field(description="Lichess challenge id.")
    action: Literal["accept", "decline"] = Field(description="Action performed.")


class AccountInfo(APIModel):
    """Public account profile from `/api/account`."""

    id: str = Field(description="Account id.")
    username: str = Field(description="Username.")
    title: str | None = Field(default=None, description="User title, if any.")
    perfs: dict[str, Any] = Field(
        default_factory=dict,
        description="Performance ratings by time control.",
    )
    disabled: bool | None = Field(default=None, description="Whether the account is disabled.")


class PlayerSummary(APIModel):
    """Compact player descriptor in board stream payloads."""

    id: str | None = None
    name: str | None = None
    title: str | None = None
    rating: int | None = None
    provisional: bool | None = None


class GameState(APIModel):
    """Incremental game state event payload from board stream."""

    type: Literal["gameState"] = "gameState"
    moves: str = Field(default="", description="Space-separated UCI moves.")
    status: str | None = None
    wtime: int | None = Field(default=None, description="White remaining milliseconds.")
    btime: int | None = Field(default=None, description="Black remaining milliseconds.")
    winc: int | None = Field(default=None, description="White increment milliseconds.")
    binc: int | None = Field(default=None, description="Black increment milliseconds.")
    wdraw: bool | None = Field(default=None, description="White draw offer state.")
    bdraw: bool | None = Field(default=None, description="Black draw offer state.")


class GameFull(APIModel):
    """Initial full game payload from board stream."""

    type: Literal["gameFull"] = "gameFull"
    id: str | None = None
    white: PlayerSummary | None = None
    black: PlayerSummary | None = None
    state: GameState | None = None
    initial_fen: str | None = Field(default=None, alias="initialFen")
    variant: dict[str, Any] | None = None
    speed: str | None = None
    rated: bool | None = None


class ChallengeEvent(APIModel):
    """Incoming challenge event from account stream."""

    type: Literal["challenge"] = "challenge"
    challenge: dict[str, Any]


class ChallengeCanceledEvent(APIModel):
    """Challenge canceled event from account stream."""

    type: Literal["challengeCanceled"] = "challengeCanceled"
    challenge: dict[str, Any]


class GameStartEvent(APIModel):
    """Game start event from account stream."""

    type: Literal["gameStart"] = "gameStart"
    game: dict[str, Any]


class GameFinishEvent(APIModel):
    """Game finish event from account stream."""

    type: Literal["gameFinish"] = "gameFinish"
    game: dict[str, Any]


IncomingBoardEvent = Annotated[
    ChallengeEvent | ChallengeCanceledEvent | GameStartEvent | GameFinishEvent,
    Field(discriminator="type"),
]

BoardGameEvent = Annotated[GameFull | GameState, Field(discriminator="type")]
