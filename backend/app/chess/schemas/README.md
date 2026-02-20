# Chess Schemas

This folder defines chess-specific data models exchanged between API routes, services, and streaming layers.

## Files

- `api.py`: request/response models for chess API endpoints.
- `review.py`: review and analysis payload models used by review workflows.

## Conventions

- Keep transport/data-contract models here.
- Avoid business logic in schema classes.
- When endpoint payloads change, update these models first and then align route/service code.

