# Full-Stack Chess Migration Plan

## Context
This plan assumes:
- Source MVP is `../cool_chess` (backend + frontend).
- Target is `./full-stack-chess-app` (FastAPI full-stack template).
- We keep the template structure and workflows as the baseline.
- We migrate business logic and preserve strong Pydantic contracts.

If your source MVP is not `../cool_chess`, replace the source paths in this plan before execution.

## Goals
- Keep template architecture (`backend/app/api`, `backend/app/core`, `frontend/src/routes`, generated client, Docker/Alembic/Playwright flow).
- Port chess business logic end-to-end (Lichess proxy, SSE, openings lookup, game review, Stockfish streaming).
- Preserve and strengthen model-driven validation using Pydantic.
- Migrate all current backend chess tests and optimize test performance/stability.
- Replace template CRUD UX/tests with chess UX/tests while keeping auth/account flows.

## Non-goals (initial migration)
- Building a brand-new design system.
- Supporting every historical MVP route shape forever.
- Distributed engine orchestration on day 1.

## Source Inventory (MVP)
- Backend modules: `cool_chess/backend/app/*` with domain-heavy code in `analysis/`, `models.py`, `main.py`, `openings.py`, `streaming.py`, `persistence.py`.
- Backend tests: `cool_chess/backend/tests/*.py` (10 modules including one manual stream probe).
- Frontend: monolithic app in `cool_chess/frontend/src/App.tsx` plus feature components/hooks.

## Template Constraints To Preserve
- API mounted at `settings.API_V1_STR` (`/api/v1`) via `backend/app/api/main.py`.
- Central settings in `backend/app/core/config.py` using `pydantic-settings`.
- DB + migrations via SQLModel + Alembic (`backend/app/models.py`, `backend/app/alembic`).
- Frontend routing via TanStack file routes in `frontend/src/routes`.
- Typed API client generated from OpenAPI in `frontend/src/client`.

## Migration Strategy (Phased)

### Phase 0 - Baseline and contracts
- Freeze MVP API/model/test inventory.
- Define target endpoint map under `/api/v1/chess/*`.
- Decide auth model for SSE (recommended: `fetch-event-source` with bearer token; avoid plain `EventSource` header limitations).
- Produce model parity checklist for every migrated request/response/event payload.

### Phase 1 - Backend domain extraction
- Create `backend/app/chess/` package for chess logic while leaving template auth/user modules intact.
- Move and refactor MVP services into template-compatible modules.
- Keep Pydantic schemas as first-class contracts in dedicated chess schema modules.

### Phase 2 - Persistence migration
- Replace Mongo-backed snapshot/review persistence with PostgreSQL/SQLModel tables (JSON columns where needed).
- Add Alembic revisions for new chess tables and indexes.
- Keep cache semantics (`review hit/miss`) and equivalent API behavior.

### Phase 3 - API route migration
- Add chess routers under `backend/app/api/routes`.
- Register routers in `backend/app/api/main.py`.
- Optional temporary compatibility aliases for old `/api/*` endpoints during frontend cutover.

### Phase 4 - Frontend migration
- Split MVP monolith into route-based features under template router/layout.
- Move REST calls to generated client where possible; keep typed SSE client wrapper for streams.
- Preserve auth flow from template (`useAuth`, token handling, protected layout).

### Phase 5 - Test migration and optimization
- Port all MVP backend tests to pytest style under `backend/tests/chess/`.
- Keep and adapt useful template tests; retire item-specific tests once chess routes replace item CRUD.
- Add deterministic fixtures for SSE, Stockfish, and Lichess stubs.

### Phase 6 - Hardening and rollout
- Add observability, rate limiting, retry boundaries, and timeout guards.
- Performance tune engine execution, stream backpressure, and DB queries.
- Run full CI matrix and stage rollout with feature flags where needed.

## Backend Test Migration Matrix (Required Coverage)

| Source test (MVP) | Target test (template) | Status target |
|---|---|---|
| `cool_chess/backend/tests/test_storage_pipeline.py` | `full-stack-chess-app/backend/tests/chess/test_storage_pipeline.py` | migrate + optimize |
| `cool_chess/backend/tests/test_streaming_and_lichess.py` | `full-stack-chess-app/backend/tests/chess/test_streaming_and_lichess.py` | migrate + optimize |
| `cool_chess/backend/tests/test_stream_and_lichess.py` | `full-stack-chess-app/backend/tests/chess/test_stream_and_lichess.py` | keep shim or remove after CLI cleanup |
| `cool_chess/backend/tests/test_analysis_stream_api.py` | `full-stack-chess-app/backend/tests/chess/test_analysis_stream_api.py` | migrate + optimize |
| `cool_chess/backend/tests/test_game_review_api.py` | `full-stack-chess-app/backend/tests/chess/test_game_review_api.py` | migrate + optimize |
| `cool_chess/backend/tests/test_game_review_schemas.py` | `full-stack-chess-app/backend/tests/chess/test_game_review_schemas.py` | migrate + optimize |
| `cool_chess/backend/tests/test_openings.py` | `full-stack-chess-app/backend/tests/chess/test_openings.py` | migrate + optimize |
| `cool_chess/backend/tests/test_stockfish_stream_schemas.py` | `full-stack-chess-app/backend/tests/chess/test_stockfish_stream_schemas.py` | migrate + optimize |
| `cool_chess/backend/tests/test_stockfish_stream_service.py` | `full-stack-chess-app/backend/tests/chess/test_stockfish_stream_service.py` | migrate + optimize |
| `cool_chess/backend/tests/test_lichess_stream.py` (manual) | `full-stack-chess-app/backend/tests/manual/test_lichess_stream.py` | keep manual probe outside CI |

## Template Test Adaptation Plan
- Keep template auth/user tests (`test_login.py`, `test_users.py`, `crud/test_user.py`) as regression coverage for identity and permissions.
- Replace or rewrite item-route tests (`test_items.py`) into chess-route equivalents.
- Keep script health tests (`tests/scripts/*`) and extend for chess prestart checks.
- Replace frontend Playwright item/admin flows with chess flows while preserving login/signup/reset-password checks.

## Definition of Done
- Chess backend is fully available under template API structure.
- Pydantic schemas cover all migrated payloads/events with validation parity or stricter.
- All migrated backend chess tests pass in CI and are faster/stabler than MVP baseline.
- Frontend chess experience is route-based within template layout and works with template auth.
- `scripts/test.sh` and `scripts/test-local.sh` execute complete backend + frontend suites without manual patching.
