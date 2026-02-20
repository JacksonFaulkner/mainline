# Backend Chess Domain

This package isolates chess-specific backend logic from the generic auth/user/backend template modules.

## Structure

- `schemas/`: API and review payload models used by chess endpoints and streaming flows.
- `services/`: business logic for analysis, commentary, openings, persistence, and external integrations.

## Integration Points

- Main route wiring is in `backend/app/api/routes/chess.py`.
- Persistence touches SQLModel entities defined in `backend/app/models.py`.
- Services are consumed by API handlers and streaming endpoints.

## Design Intent

- Keep chess complexity in this package.
- Avoid leaking chess-specific concerns into template-level core modules.

