# Backend Migration Plan

## Objective
Migrate chess backend business logic from `cool_chess/backend` into the FastAPI template backend while preserving:
- Template architecture and lifecycle.
- Pydantic-heavy validation and typed event contracts.
- Complete current chess backend test coverage.

## Target Backend Shape (Template-Compatible)

```text
backend/
  app/
    api/
      main.py
      routes/
        login.py
        users.py
        chess_account.py
        chess_play.py
        chess_stream.py
        chess_analysis.py
        chess_openings.py
        chess_storage.py
        chess_challenges.py
    chess/
      __init__.py
      schemas/
        common.py
        stream.py
        review.py
      services/
        lichess_client.py
        streaming.py
        openings.py
        analysis_stream.py
        review_service.py
      persistence/
        snapshots.py
        reviews.py
      constants.py
    core/
      config.py
      db.py
    models.py
```

Notes:
- Keep template entrypoints (`app/main.py`, `app/api/main.py`) unchanged in structure.
- Keep template auth/user tables and services.
- Add chess domain package under `app/chess/` to avoid overloading template root files.

## Endpoint Migration Map

| MVP endpoint | Target endpoint (canonical) | Router file |
|---|---|---|
| `GET /health` | `GET /api/v1/chess/health` | `chess_account.py` |
| `GET /api/me` | `GET /api/v1/chess/me` | `chess_account.py` |
| `GET /api/me/games/recent` | `GET /api/v1/chess/me/games/recent` | `chess_account.py` |
| `POST /api/seek` | `POST /api/v1/chess/seek` | `chess_play.py` |
| `GET /api/events` | `GET /api/v1/chess/events` | `chess_stream.py` |
| `GET /api/games/{id}/stream` | `GET /api/v1/chess/games/{id}/stream` | `chess_stream.py` |
| `POST /api/games/{id}/move` | `POST /api/v1/chess/games/{id}/move` | `chess_play.py` |
| `POST /api/games/{id}/positions` | `POST /api/v1/chess/games/{id}/positions` | `chess_storage.py` |
| `GET /api/games/{id}/review` | `GET /api/v1/chess/games/{id}/review` | `chess_analysis.py` |
| `GET /api/analysis/stream` | `GET /api/v1/chess/analysis/stream` | `chess_analysis.py` |
| `POST /api/openings/lookup` | `POST /api/v1/chess/openings/lookup` | `chess_openings.py` |
| `POST /api/challenges/{id}/accept` | `POST /api/v1/chess/challenges/{id}/accept` | `chess_challenges.py` |
| `POST /api/challenges/{id}/decline` | `POST /api/v1/chess/challenges/{id}/decline` | `chess_challenges.py` |

Compatibility option:
- Keep temporary aliases for old `/api/*` routes for one release to ease frontend cutover.

## Pydantic Model Migration Plan

### Keep model-heavy contracts
Migrate these models from `cool_chess/backend/app/models.py` and `analysis/models.py` with minimal semantic changes:
- Core API payloads: `SeekRequest`, `MoveRequest`, `PositionSnapshotRequest`, `RecentGameSummary`, etc.
- Stream models: `StockfishDepthUpdateEvent`, `StockfishAnalysisCompleteEvent`, `StockfishAnalysisErrorEvent`, discriminator union.
- Review models: `GameReview` and nested review/opening/engine objects.

### Placement
- SQLModel DB entities remain in `backend/app/models.py` (template convention).
- Chess request/response/event Pydantic schemas live in `backend/app/chess/schemas/*`.
- Avoid mixing large chess payload models into template user/item SQLModel blocks.

## Persistence Migration (Mongo -> PostgreSQL)

### New SQLModel tables
- `ChessSnapshot`
  - columns: `id`, `game_id`, `move_count`, `fen`, `moves_json`, `status`, `saved_at`, `created_at`.
  - unique index: `(game_id, move_count)`.
  - query index: `(game_id, saved_at desc)`.
- `ChessGameReview`
  - columns: `id`, `game_id`, `review_json`, `updated_at`, `created_at`.
  - unique index: `(game_id)`.

### Behavior parity requirements
- `save_position_snapshot` upsert semantics must match MVP.
- Review endpoint must keep cache semantics and `X-Review-Cache` response header.
- 503 fallback for persistence outage can be retained initially, then tightened per environment.

### Alembic
- Create one migration for chess tables + indexes.
- Add data validators for JSON payload shape at application layer (Pydantic) before write.

## Auth and Lichess Client Strategy

Current MVP uses one global `LICHESS_TOKEN`.

Production-ready plan:
- Phase 1: keep service token flow for parity and speed.
- Phase 2: add per-user token/session support so each app user can act with their own Lichess identity.
- Encapsulate this in `app/chess/services/lichess_client.py` so route code does not change when auth evolves.

## Config Migration

Map MVP settings into template `core/config.py`:
- `LICHESS_TOKEN`
- `OPENINGS_DB_DIR`
- `STOCKFISH_PATH`
- `STOCKFISH_DEPTH`
- `STOCKFISH_MOVETIME_MS`
- `STOCKFISH_MULTIPV`
- `ANALYSIS_CACHE_TTL_SEC`
- chess-specific CORS or stream throttling values if needed

Use `pydantic-settings` typed fields and validators; avoid ad-hoc dataclass settings.

## Execution Order (Backend)
1. Add chess schema modules and copy model tests first.
2. Add chess service modules (lichess, openings, streaming, review, analysis stream).
3. Add SQLModel chess tables + Alembic migration.
4. Implement chess persistence adapters and route handlers.
5. Register routers in `app/api/main.py`.
6. Port tests module-by-module and run under pytest.
7. Remove dead template item routes/tests once chess replacements are complete.

## Backend Test Porting Plan

### Test framework direction
- Convert `unittest` style modules to pytest style.
- Keep assertions and scenarios identical first; then optimize.

### Target structure

```text
backend/tests/
  chess/
    test_storage_pipeline.py
    test_streaming_and_lichess.py
    test_analysis_stream_api.py
    test_game_review_api.py
    test_game_review_schemas.py
    test_openings.py
    test_stockfish_stream_schemas.py
    test_stockfish_stream_service.py
  manual/
    test_lichess_stream.py
```

### Optimization requirements during port
- Replace repetitive `setUp` `TestClient` creation with scoped pytest fixtures.
- Parameterize repeated invalid-input scenarios.
- Use deterministic clocks for SSE throttling tests (`time.sleep` and timestamps).
- Mark manual network probe tests with `@pytest.mark.manual` and exclude from CI.
- Add coverage gates for chess package modules.

## Risk Register
- SSE auth mismatch with template token model.
- Engine subprocess instability under concurrent load.
- JSONB payload growth for review cache.
- Path mismatch (`/api` vs `/api/v1`) during frontend transition.

Mitigations:
- Ship route aliases temporarily.
- Limit engine concurrency with queueing.
- Set payload size limits and prune oversized review fields.
- Add strict integration tests for canonical and compatibility routes.
