# Optimization Backlog (Migration + Post-Migration)

This file is intentionally suggestion-heavy so you can choose optimization depth by phase.

## How to Use This Backlog
- Apply `P0` items during migration (safety and correctness).
- Apply `P1` items before broad user rollout.
- Apply `P2` items as continuous improvement work.

## P0 - High-Impact, Low-Risk (Do Early)
- P0: Convert migrated backend tests from `unittest` style to pytest fixtures/parametrization for speed and readability.
- P0: Mark manual network tests (`test_lichess_stream.py`) as non-CI.
- P0: Add strict Pydantic validation at every API boundary (request parse + outbound response shaping).
- P0: Add timeout guards for all Lichess and Stockfish calls.
- P0: Add consistent exception mapping with stable error codes.
- P0: Add request-id correlation to logs for all chess routes and SSE streams.
- P0: Add OpenAPI examples for all new chess endpoints.
- P0: Run mypy/ruff/pytest in CI for backend on every PR.
- P0: Split giant frontend features into route-level chunks to reduce initial JS payload.
- P0: Replace plain `EventSource` with authenticated streaming transport.
- P0: Ensure Playwright prerequisites are explicit in CI and local docs (browser install + backend/db availability).
- P0: Avoid Playwright port collisions by pinning dedicated test host/port and disabling server reuse for CI runs.

## P1 - Production Hardening
- P1: Add connection pooling and retry policy for downstream Lichess HTTP operations.
- P1: Add lightweight circuit breaker around Lichess failures to prevent cascading errors.
- P1: Bound Stockfish concurrency with a queue/semaphore to prevent CPU starvation.
- P1: Cache opening lookups for repeated move prefixes.
- P1: Cache game reviews by `(game_id, refresh flag)` with TTL and explicit invalidation.
- P1: Add DB indexes for common filters (`game_id`, `saved_at`, `updated_at`).
- P1: Add response compression for large review payloads.
- P1: Add pagination/cursor controls for history endpoints as data grows.
- P1: Add health checks that include dependency readiness (DB, engine binary, optional Lichess check).
- P1: Add structured logs for SSE lifecycle (open/update/error/close).
- P1: Capture stream disconnect reasons and rates for operational dashboards.
- P1: Add robust reconnection backoff policy on frontend stream clients.
- P1: Add optimistic UI for move submission with rollback on server rejection.
- P1: Persist frontend analysis preferences (multipv/depth) in local storage per user.
- P1: Guard expensive chart re-renders with memoization and selector narrowing.
- P1: Add a dedicated `chess` React Query namespace and tuned stale times.
- P1: Preload critical routes after login for faster first interaction.
- P1: Add smoke tests that validate OpenAPI client generation in CI.
- P1: Run Playwright tests in parallel shards with deterministic fixtures.
- P1: Add flaky-test detection and quarantine pipeline.
- P1: Add a Playwright "mock-auth + mocked API" smoke profile so UI route checks can run even when backend is offline.
- P1: Keep a separate "real backend" Playwright profile for true end-to-end login/session coverage.

## P2 - Advanced Scaling and DX
- P2: Move long-running engine analysis to background workers and stream progress from job state.
- P2: Store analysis snapshots to avoid recomputation of common positions.
- P2: Add per-user engine quota/rate limits.
- P2: Add Redis for transient stream state and cache invalidation fanout.
- P2: Add ETag or conditional GET for review payload endpoints.
- P2: Add server-side sampling for verbose stream logs.
- P2: Add SLO dashboards (latency, stream stability, error budget burn).
- P2: Add contract tests that diff OpenAPI schema against expected fixtures.
- P2: Add chaos tests for downstream failures (Lichess down, engine unavailable, DB slow).
- P2: Add canary deployment checks for stream endpoints.

## Backend-Specific Suggestions

## API and validation
- Keep one canonical schema source for each payload type; avoid duplicate ad-hoc dict contracts.
- Use discriminated unions for all event streams and enforce `type` in tests.
- Add custom validators for FEN normalization and UCI move format once, reuse everywhere.
- Enforce max payload sizes for review/raw PGN fields.
- Reject unsupported variants explicitly with stable error messages.

## Service boundaries
- Introduce `chess/services/*` interfaces for Lichess, engine, persistence to simplify mocking.
- Keep route handlers thin: parse input, call service, map error, return model.
- Remove hidden global state from services where possible.
- Inject dependencies in tests to avoid patching deep module paths.

## Persistence
- Store large nested review payloads in JSONB but index selective scalar columns.
- Add unique constraints that match business invariants.
- Use server-generated timestamps (`now()`/UTC) consistently.
- Add archival strategy for old snapshots to control table growth.
- Add migration tests for every Alembic revision touching chess tables.

## Streaming and engine
- Add heartbeat events every N seconds to keep intermediaries from closing idle streams.
- Add per-stream idle timeout and graceful completion reasons.
- Emit explicit terminal event on cancellation.
- Cap analysis depth and multipv server-side regardless of client request.
- Preflight stockfish availability and expose readiness endpoint.
- Protect engine subprocess launches with backoff and startup timeout.

## Frontend-Specific Suggestions

## Rendering and state
- Split chess pages by route-level code splitting.
- Memoize expensive board overlays and chart transforms.
- Virtualize long move/review lists.
- Move heavy eval computations to web workers if UI jank appears.
- Normalize server payloads once in data layer, not in every component.
- Keep a small state machine for stream lifecycle (`idle/connecting/live/error/closed`).

## UX resilience
- Show explicit reconnect state for stream disruptions.
- Add recoverable error toasts with retry actions.
- Debounce high-frequency slider/setting changes before API calls.
- Keep manual refresh controls for stale analysis views.
- Add skeleton states for every chess route.

## Accessibility
- Keyboard navigation for move timeline and board controls.
- ARIA live region for critical stream status changes.
- Colorblind-safe palette for move arrows and eval bars.
- Screen-reader labels for graph data points and summary panels.

## Test Optimization Suggestions (Detailed)
- Use pytest markers: `unit`, `integration`, `manual`, `slow`, `stream`.
- Make `TestClient` a module fixture, not per-test where safe.
- Replace repeated timestamp assertions with tolerance helper utilities.
- Parametrize invalid-input tests for FEN/UCI/depth bounds.
- Use fake clock helpers for throttle and timeout behavior.
- Ensure stream tests assert event order and terminal event presence.
- Use hypothesis/property tests for move normalization edge cases.
- Add mutation tests for critical validators.
- Snapshot-test complex review payload shapes after normalization.
- Add frontend component tests for stream parser and reducer logic.
- Keep Playwright tests focused on core user journeys; move edge cases to lower-level tests.
- Cache Playwright browser binaries and npm/uv dependencies in CI.
- Use selective test runs by changed paths for faster PR feedback.
- Keep nightly full-suite run with extended stream/stress coverage.

## Security and Compliance Suggestions
- Avoid exposing raw downstream exception text directly to clients in production mode.
- Add per-route rate limiting for stream-heavy endpoints.
- Enforce stricter CORS by environment.
- Rotate and validate secret config at startup.
- Add audit logs for challenge actions and move submissions.
- Scan dependencies in CI (Python + Node) with fail thresholds.

## Observability Suggestions
- Standardize log fields: `request_id`, `user_id`, `game_id`, `stream_id`, `endpoint`.
- Export metrics: request latency, error counts, stream durations, disconnect reasons.
- Add tracing for route -> service -> downstream calls.
- Alert on high stream error ratio and engine unavailability.
- Alert on DB query p95 regressions and migration failures.

## Suggested Milestone Bundles
- Bundle A (migration-safe): all P0 + backend test optimization basics.
- Bundle B (pre-launch): core P1 reliability + SSE/auth hardening + full chess E2E suite.
- Bundle C (scale-up): selected P2 worker/cache/observability investments.
