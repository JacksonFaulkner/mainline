# Frontend Migration Plan

## Objective
Move chess frontend behavior from `cool_chess/frontend` into template frontend (`full-stack-chess-app/frontend`) while preserving:
- Template routing/auth/client conventions.
- Typed API integration.
- Production-ready route/component boundaries.

## Current State Summary
- MVP UI is largely in one file: `cool_chess/frontend/src/App.tsx`.
- MVP uses `fetch` + `EventSource` directly in `src/lib/api.ts`.
- Template frontend is route-based with TanStack Router + React Query + generated OpenAPI client.

## Target Frontend Structure (Template-Compatible)

```text
frontend/src/
  routes/
    _layout.tsx
    _layout/index.tsx
    _layout/play.tsx
    _layout/analysis.tsx
    _layout/history.tsx
    _layout/matchmaking.tsx
    _layout/system.tsx
    login.tsx
    signup.tsx
  features/chess/
    api/
      rest.ts
      sse.ts
    state/
      use-chess-session.ts
    play/
    analysis/
    history/
    matchmaking/
    system/
  components/chess/
```

Key rule:
- Keep template `routes/` + protected layout conventions.
- Move domain behavior into `features/chess/*`.

## Route Migration Plan

| MVP area | Target route | Notes |
|---|---|---|
| Play board + live game stream | `/_layout/play` | main game interaction screen |
| Analysis stream + review panel | `/_layout/analysis` | includes stockfish stream and review fetch |
| Recent games | `/_layout/history` | consumes `/chess/me/games/recent` |
| Seek/challenge workflows | `/_layout/matchmaking` | challenge accept/decline + seek |
| Runtime diagnostics | `/_layout/system` | stream status, API base, environment checks |

Dashboard (`/_layout/index`) should become a compact chess home/overview instead of generic item/admin summary.

## API Integration Plan

### REST
- Use generated OpenAPI client for standard endpoints:
  - account, recent games, seek, move, openings lookup, review fetch, snapshots, challenge actions.
- Add thin wrappers in `features/chess/api/rest.ts` to normalize response errors into domain-friendly messages.

### SSE
`EventSource` cannot send Authorization headers reliably in bearer-token flows.

Recommended approach:
- Use `@microsoft/fetch-event-source` for authenticated SSE streams.
- Send bearer token like other API calls.
- Parse server events (`depth_update`, `analysis_complete`, `proxy_error`) in one reusable stream utility.

Fallback (only if needed):
- temporary token query param for stream routes, then remove.

## Component Migration Plan

### Extract from MVP `App.tsx`
- Move gameplay logic to `features/chess/play`.
- Move timeline + replay logic to `features/chess/history`.
- Move analysis overlays/charts/hooks to `features/chess/analysis`.
- Keep generic primitives in `components/ui` and chess-specific visuals in `components/chess`.

### State management
- Keep route-local state where possible.
- Centralize only shared session state (active game id, orientation, stream state, selected ply) in a small domain hook/store.
- Use React Query for server state, not custom global caches where avoidable.

## Frontend Test Migration Plan

## Keep from template
- Login/logout and auth gate coverage (`login.spec.ts` core scenarios).
- Signup/reset-password/user-settings coverage if still supported in chess app scope.

## Replace/adapt
- `items.spec.ts` -> `play.spec.ts`
  - make move
  - stream game updates
  - persist snapshot behavior
- `admin.spec.ts` -> `matchmaking.spec.ts`
  - create seek
  - incoming challenge event handling
  - accept/decline flows
- Add `analysis.spec.ts`
  - starts analysis stream
  - receives depth updates
  - handles completion/error events
- Add `history.spec.ts`
  - recent games list
  - review cache hit/miss UI states

## Test stability requirements
- Use deterministic seeded users and game fixtures where possible.
- Stub long-running stream backends in CI-oriented E2E tests.
- Separate smoke E2E from full stream lifecycle E2E.

## Implementation Sequence (Frontend)
1. Add chess routes and nav entries in sidebar.
2. Move MVP API calls into template domain API wrappers.
3. Introduce authenticated SSE utility.
4. Port play/matchmaking/history/analysis features incrementally.
5. Delete old item/admin UI once equivalent chess screens are complete.
6. Rewrite Playwright suite to chess-focused scenarios.

## Progress Snapshot (Current)
- Completed: `/_layout/items` and `/_layout/admin` routes removed from the frontend route tree.
- Completed: Sidebar navigation now points to chess routes only (`/play`, `/analysis`, `/history`, `/matchmaking`, `/system`).
- Completed: History screen migrated to shared template `DataTable` pattern via chess-specific columns.
- Completed: Playwright files renamed from template naming to chess naming (`play.spec.ts`, `analysis.spec.ts`, plus `history.spec.ts`, `matchmaking.spec.ts`, `system.spec.ts`).
- Completed: Playwright tooling shifted to npm-compatible commands (no Bun requirement).
- Pending: Full Playwright green run in this workspace still depends on a running backend + database stack for auth setup.

## Acceptance Criteria
- No monolithic `App.tsx` equivalent remains.
- All chess features are route-based and work under template auth.
- SSE endpoints work with authenticated users in browser and CI.
- Frontend tests cover login + core chess workflows end-to-end.
