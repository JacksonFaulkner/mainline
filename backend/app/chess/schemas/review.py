from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.chess.schemas.api import UCI_MOVE_PATTERN


def _normalize_uci(value: str) -> str:
    normalized = value.strip().lower()
    if not re.match(UCI_MOVE_PATTERN, normalized):
        raise ValueError(f"invalid UCI move: {value}")
    return normalized


def _normalize_uci_list(value: list[str]) -> list[str]:
    normalized: list[str] = []
    for move in value:
        if not isinstance(move, str):
            raise ValueError("moves must contain strings")
        normalized.append(_normalize_uci(move))
    return normalized


class ReviewPlayer(BaseModel):
    username: str = Field(min_length=1, description="Player username.")
    rating: int | None = Field(default=None, description="Player rating at game time, if available.")
    title: str | None = Field(default=None, description="Optional player title (GM, IM, etc).")


class GameMetadata(BaseModel):
    game_id: str = Field(min_length=1, description="Lichess game identifier.")
    url: str = Field(min_length=1, description="Canonical game URL.")
    played_at: datetime | None = Field(default=None, description="UTC timestamp when the game was played.")
    white: ReviewPlayer = Field(description="White player metadata.")
    black: ReviewPlayer = Field(description="Black player metadata.")
    result: Literal["1-0", "0-1", "1/2-1/2", "*"] = Field(
        description="PGN result token."
    )
    winner: Literal["white", "black"] | None = Field(default=None, description="Winning side, if decisive.")
    rated: bool | None = Field(default=None, description="Whether the game was rated.")
    speed: str | None = Field(default=None, description="Speed bucket (blitz, rapid, etc).")
    perf: str | None = Field(default=None, description="Lichess perf key.")
    variant: str | None = Field(default=None, description="Variant key (standard, chess960, etc).")
    initial_fen: str | None = Field(
        default=None,
        alias="initialFen",
        description="Initial FEN if game did not start from standard initial position.",
    )
    total_plies: int = Field(default=0, ge=0, description="Total number of half-moves in the game.")
    termination: str | None = Field(default=None, description="Termination reason/status, if available.")


class OpeningMetadata(BaseModel):
    eco: str = Field(min_length=1, description="ECO code of the detected opening.")
    name: str = Field(min_length=1, description="Opening family name.")
    variation: str | None = Field(default=None, description="Optional opening variation name.")
    source: str = Field(default="lichess-pgn", description="Source used to infer opening metadata.")


class EngineContext(BaseModel):
    name: str = Field(default="stockfish", description="Engine name used for the analysis run.")
    depth: int = Field(default=14, ge=1, description="Requested search depth.")
    multipv: int = Field(default=1, ge=1, le=5, description="Requested number of principal variations.")
    movetime_ms: int | None = Field(default=None, ge=25, description="Optional fixed think time per position in milliseconds.")


class EngineLine(BaseModel):
    rank: int = Field(default=1, ge=1, description="PV rank where 1 is best.")
    cp: int | None = Field(default=None, description="Centipawn evaluation from White perspective.")
    mate: int | None = Field(default=None, description="Mate score in plies, if applicable.")
    moves: list[str] = Field(default_factory=list, description="PV moves in UCI notation.")

    @field_validator("moves", mode="before")
    @classmethod
    def normalize_moves(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_uci_list(value)


class MoveReview(BaseModel):
    ply: int = Field(ge=1, description="1-based half-move index.")
    turn: Literal["white", "black"] = Field(description="Side that played this move.")
    san: str = Field(min_length=1, description="Played move in SAN notation.")
    uci: str = Field(min_length=4, max_length=5, description="Played move in UCI notation.")
    fen_before: str | None = Field(default=None, description="FEN before the move was played.")
    fen_after: str | None = Field(default=None, description="FEN after the move was played.")
    eval_before_cp: int | None = Field(default=None, description="Engine centipawn eval before the move.")
    eval_after_cp: int | None = Field(default=None, description="Engine centipawn eval after the move.")
    eval_swing_cp: int | None = Field(default=None, description="Delta between eval_after_cp and eval_before_cp.")
    bestmove_uci: str | None = Field(default=None, description="Engine best move in UCI for the pre-move position.")
    best_line: EngineLine | None = Field(default=None, description="Primary engine line for the pre-move position.")
    alternatives: list[EngineLine] = Field(default_factory=list, description="Alternative PV lines (MultiPV > 1).")
    tags: list[str] = Field(default_factory=list, description="Arbitrary labels for downstream review agents.")

    @field_validator("uci", mode="before")
    @classmethod
    def normalize_uci(cls, value: object) -> object:
        if isinstance(value, str):
            return _normalize_uci(value)
        return value

    @field_validator("bestmove_uci", mode="before")
    @classmethod
    def normalize_bestmove(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            return _normalize_uci(value)
        return value


class ReviewPointOfInterest(BaseModel):
    ply: int = Field(ge=1, description="Ply where the point of interest occurs.")
    side: Literal["white", "black"] = Field(description="Side associated with the point of interest.")
    kind: Literal["blunder", "mistake", "inaccuracy", "swing", "critical", "tactic"] = Field(
        description="Classification label for the critical moment."
    )
    title: str = Field(min_length=1, description="Short one-line headline for the point of interest.")
    detail: str | None = Field(default=None, description="Longer explanation suitable for review UI or agents.")
    swing_cp: int | None = Field(default=None, description="Evaluation swing tied to this moment, if computed.")
    recommended_line: EngineLine | None = Field(default=None, description="Engine-recommended continuation.")
    played_line: list[str] = Field(default_factory=list, description="Played continuation in UCI.")

    @field_validator("played_line", mode="before")
    @classmethod
    def normalize_played_line(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return _normalize_uci_list(value)


class ReviewSummary(BaseModel):
    final_eval_white_cp: int | None = Field(default=None, description="Final position evaluation in centipawns from White perspective.")
    decisive_ply: int | None = Field(default=None, ge=1, description="Ply where the game became strategically/tactically decisive.")
    white_advantage_peak_cp: int | None = Field(default=None, description="Maximum white advantage reached during analysis.")
    black_advantage_peak_cp: int | None = Field(default=None, description="Maximum black advantage reached during analysis.")
    notes: list[str] = Field(default_factory=list, description="Free-form summary bullets for final review output.")


class BedrockContextLine(BaseModel):
    label: str = Field(min_length=1, description="Short label for one context line.")
    value: str = Field(min_length=1, description="Compact context value to include in the prompt.")


class BedrockReviewPrompt(BaseModel):
    model_id: str = Field(
        default="arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
        min_length=1,
        description="Bedrock model ID used for game review generation.",
    )
    system_prompt: str = Field(
        min_length=1,
        description="Short system instruction for the chess review assistant.",
    )
    user_message: str = Field(
        min_length=1,
        description="Short user instruction describing desired review output.",
    )
    context_lines: list[BedrockContextLine] = Field(
        default_factory=list,
        description="Structured context bullets derived from GameReview data.",
    )
    max_output_tokens: int = Field(
        default=700,
        ge=64,
        le=4096,
        description="Maximum token budget for model output.",
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for response generation.",
    )

    def rendered_user_message(self) -> str:
        context = "\n".join(f"- {line.label}: {line.value}" for line in self.context_lines)
        if not context:
            return self.user_message
        return f"{self.user_message}\n\nContext:\n{context}"


class BedrockUsageStats(BaseModel):
    input_tokens: int | None = Field(default=None, ge=0, description="Bedrock input token count, if returned.")
    output_tokens: int | None = Field(default=None, ge=0, description="Bedrock output token count, if returned.")
    total_tokens: int | None = Field(default=None, ge=0, description="Bedrock total token count, if returned.")


class BedrockCompletion(BaseModel):
    model_id: str = Field(min_length=1, description="Bedrock model ID that produced this response.")
    text: str = Field(min_length=1, description="Assistant response text returned by Bedrock.")
    stop_reason: str | None = Field(default=None, description="Bedrock stop reason, if available.")
    usage: BedrockUsageStats | None = Field(
        default=None,
        description="Token usage details returned by Bedrock, if available.",
    )
    latency_ms: int | None = Field(default=None, ge=0, description="End-to-end model latency in milliseconds.")


class BedrockReviewResponse(BaseModel):
    ok: bool = Field(default=True, description="Whether Bedrock review generation succeeded.")
    game_id: str = Field(min_length=1, description="Lichess game identifier.")
    cache: Literal["hit", "miss"] = Field(description="Whether the underlying structured review came from cache.")
    prompt: BedrockReviewPrompt = Field(description="Prompt payload sent to Bedrock.")
    completion: BedrockCompletion = Field(description="Model response returned by Bedrock.")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp when this response was generated.")


class GameReview(BaseModel):
    game: GameMetadata = Field(description="Core immutable metadata for the reviewed game.")
    opening: OpeningMetadata | None = Field(default=None, description="Opening identification metadata.")
    engine: EngineContext | None = Field(default=None, description="Engine configuration used to generate review data.")
    moves: list[MoveReview] = Field(default_factory=list, description="Move-by-move review records.")
    points_of_interest: list[ReviewPointOfInterest] = Field(
        default_factory=list,
        description="Ranked critical moments used to drive human-readable review narratives.",
    )
    summary: ReviewSummary | None = Field(default=None, description="Game-level aggregate conclusions.")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp when this review payload was generated.")
    raw_pgn: str | None = Field(default=None, description="Optional raw PGN text used as source input.")

    @model_validator(mode="after")
    def validate_consistency(self) -> GameReview:
        for index, move in enumerate(self.moves, start=1):
            if move.ply != index:
                raise ValueError("moves must be ordered by ply starting at 1")
            expected_turn = "white" if index % 2 == 1 else "black"
            if move.turn != expected_turn:
                raise ValueError("move turn does not match ply parity")

        if self.game.total_plies and self.game.total_plies != len(self.moves):
            raise ValueError("game.total_plies must match moves length when provided")

        max_ply = len(self.moves)
        for poi in self.points_of_interest:
            if max_ply and poi.ply > max_ply:
                raise ValueError("point_of_interest ply is out of range")
        if self.summary and self.summary.decisive_ply and max_ply and self.summary.decisive_ply > max_ply:
            raise ValueError("summary.decisive_ply is out of range")
        return self


def _rating_fragment(player: ReviewPlayer) -> str:
    if player.rating is None:
        return player.username
    return f"{player.username} ({player.rating})"


def build_bedrock_review_prompt(
    review: GameReview,
    *,
    model_id: str = "arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
    max_context_lines: int = 10,
) -> BedrockReviewPrompt:
    lines: list[BedrockContextLine] = []

    lines.append(
        BedrockContextLine(
            label="Game",
            value=(
                f"{_rating_fragment(review.game.white)} vs {_rating_fragment(review.game.black)}, "
                f"result {review.game.result}, {review.game.total_plies} plies"
            ),
        )
    )

    if review.opening:
        opening_value = review.opening.name
        if review.opening.variation:
            opening_value = f"{opening_value} - {review.opening.variation}"
        lines.append(BedrockContextLine(label="Opening", value=f"{review.opening.eco} {opening_value}"))

    if review.summary and review.summary.decisive_ply:
        lines.append(
            BedrockContextLine(
                label="Decisive Moment",
                value=f"Ply {review.summary.decisive_ply}",
            )
        )

    if review.summary and review.summary.final_eval_white_cp is not None:
        lines.append(
            BedrockContextLine(
                label="Final Eval",
                value=f"{review.summary.final_eval_white_cp:+} cp (white perspective)",
            )
        )

    for poi in review.points_of_interest[:4]:
        detail = f"ply {poi.ply}, {poi.side} {poi.kind.lower()}: {poi.title}"
        if poi.swing_cp is not None:
            detail = f"{detail} ({poi.swing_cp:+}cp)"
        lines.append(BedrockContextLine(label="Critical", value=detail))

    if review.moves:
        tail = review.moves[-6:]
        lines.append(
            BedrockContextLine(
                label="Recent Moves",
                value=" ".join(move.san for move in tail),
            )
        )

    if review.raw_pgn:
        compact_pgn = " ".join(review.raw_pgn.split())
        lines.append(BedrockContextLine(label="PGN", value=compact_pgn[:300]))

    if max_context_lines > 0:
        lines = lines[:max_context_lines]
    else:
        lines = []

    return BedrockReviewPrompt(
        model_id=model_id,
        system_prompt=(
            "You are a practical chess coach. Give accurate, concise feedback and prioritize actionable improvements."
        ),
        user_message=(
            "Review this game in 3 short sections: What decided the game, biggest mistakes, and one training drill."
        ),
        context_lines=lines,
    )


def sample_game_review() -> GameReview:
    return GameReview(
        game=GameMetadata(
            game_id="PqM3vCDs",
            url="https://lichess.org/PqM3vCDs",
            played_at=datetime(2026, 2, 9, 20, 0, 0, tzinfo=timezone.utc),
            white=ReviewPlayer(username="B00gieman", rating=1780),
            black=ReviewPlayer(username="JacksonFau1kner", rating=1812),
            result="0-1",
            winner="black",
            rated=True,
            speed="blitz",
            perf="blitz",
            variant="standard",
            total_plies=4,
            termination="mate",
        ),
        opening=OpeningMetadata(
            eco="B01",
            name="Scandinavian Defense",
            variation="Mieses-Kotroc Variation",
        ),
        engine=EngineContext(name="stockfish", depth=18, multipv=3),
        moves=[
            MoveReview(
                ply=1,
                turn="white",
                san="e4",
                uci="e2e4",
                eval_before_cp=20,
                eval_after_cp=30,
                eval_swing_cp=10,
                bestmove_uci="e2e4",
                best_line=EngineLine(rank=1, cp=30, moves=["e2e4", "d7d5", "e4d5"]),
            ),
            MoveReview(
                ply=2,
                turn="black",
                san="d5",
                uci="d7d5",
                eval_before_cp=30,
                eval_after_cp=10,
                eval_swing_cp=-20,
                bestmove_uci="d7d5",
                best_line=EngineLine(rank=1, cp=10, moves=["d7d5", "e4d5", "d8d5"]),
            ),
            MoveReview(
                ply=3,
                turn="white",
                san="exd5",
                uci="e4d5",
                eval_before_cp=10,
                eval_after_cp=35,
                eval_swing_cp=25,
                bestmove_uci="e4d5",
            ),
            MoveReview(
                ply=4,
                turn="black",
                san="Qxd5",
                uci="d8d5",
                eval_before_cp=35,
                eval_after_cp=5,
                eval_swing_cp=-30,
                bestmove_uci="d8d5",
            ),
        ],
        points_of_interest=[
            ReviewPointOfInterest(
                ply=4,
                side="black",
                kind="critical",
                title="Recaptures central pawn with queen",
                detail="Black restores material balance and keeps active piece play.",
                swing_cp=-30,
                recommended_line=EngineLine(rank=1, cp=5, moves=["d8d5", "b1c3", "d5a5"]),
            )
        ],
        summary=ReviewSummary(
            final_eval_white_cp=5,
            decisive_ply=4,
            white_advantage_peak_cp=35,
            black_advantage_peak_cp=-30,
            notes=["Model is intended for move-by-move review and eval swing tagging."],
        ),
        raw_pgn='1. e4 d5 2. exd5 Qxd5 *',
    )


_MODEL_ORDER: tuple[type[BaseModel], ...] = (
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
    BedrockUsageStats,
    BedrockCompletion,
    BedrockReviewResponse,
    GameReview,
)


def _annotation_label(annotation: Any) -> str:
    text = str(annotation)
    return text.replace("typing.", "")


def _model_table(model_type: type[BaseModel]) -> str:
    rows: list[str] = []
    for name, field in model_type.model_fields.items():
        required = "yes" if field.is_required() else "no"
        default = "—" if field.default is None and not field.is_required() else repr(field.default)
        description = field.description or ""
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(name)}</code></td>"
            f"<td><code>{html.escape(_annotation_label(field.annotation))}</code></td>"
            f"<td>{required}</td>"
            f"<td>{html.escape(default)}</td>"
            f"<td>{html.escape(description)}</td>"
            "</tr>"
        )
    body = "".join(rows)
    return (
        f"<section><h2>{html.escape(model_type.__name__)}</h2>"
        "<table><thead><tr>"
        "<th>field</th><th>type</th><th>required</th><th>default</th><th>description</th>"
        f"</tr></thead><tbody>{body}</tbody></table></section>"
    )


def render_game_review_models_html() -> str:
    sample = sample_game_review().model_dump_json(indent=2, by_alias=True)
    sections = "".join(_model_table(model) for model in _MODEL_ORDER)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Game Review Model Map</title>
  <style>
    body {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 24px; line-height: 1.45; }}
    h1, h2 {{ margin: 0 0 8px; }}
    p {{ margin: 0 0 16px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0 24px; font-size: 13px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f7f7f7; }}
    .flow {{ padding: 10px; border: 1px solid #ddd; background: #fafafa; margin-bottom: 20px; }}
    pre {{ border: 1px solid #ddd; background: #0f172a; color: #e5e7eb; padding: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>Game Review Data Map</h1>
  <p>Use this page to inspect the full game-review model contract before implementing the review pipeline.</p>
  <div class="flow"><code>GameReview -> {{ game, opening, engine, moves[], points_of_interest[], summary, generated_at, raw_pgn }}</code></div>
  {sections}
  <h2>Sample Payload</h2>
  <pre>{html.escape(sample)}</pre>
</body>
</html>"""
