# Frontend Chess Components

This folder contains chess-focused UI components used by route pages.

## Typical Components Here

- Board and position rendering.
- Analysis visuals (for example, eval chart or move overlays).
- History and review action widgets.
- Shared chess workspace composition/layout pieces.

## Boundary

- Keep these components mostly presentational.
- Put API calls, stream handling, and domain-state logic in `frontend/src/features/chess/`.

