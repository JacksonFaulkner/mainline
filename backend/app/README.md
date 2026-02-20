# Backend App Package

This is the backend application root package used by FastAPI.

## What Lives Here

- `main.py`: FastAPI app entrypoint and startup wiring.
- `api/`: versioned API router composition and route modules.
- `core/`: settings, database setup, and security primitives.
- `models.py`: SQLModel ORM models shared across domains.
- `crud.py`: core CRUD helpers for common entities.
- `chess/`: chess-specific schemas and business services.
- `alembic/`: migration environment and revision files.
- `data/`: bundled reference datasets (for example, openings).
- `email-templates/`: email template source/build artifacts.

## Support Files

- `backend_pre_start.py`, `tests_pre_start.py`: pre-start checks and startup verification helpers.
- `initial_data.py`: bootstrap logic for seed/admin initialization.
- `utils.py`: shared utility helpers used across backend modules.

## Design Intent

- Keep generic platform concerns in `api/` and `core/`.
- Keep chess domain complexity isolated under `chess/`.
- Keep DB schema and migrations synchronized (`models.py` + `alembic/`).

