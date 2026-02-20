# Git Commit Style

Use Conventional Commits with this format:

`type(scope): short summary`

## Rules

- Keep summary in imperative mood (e.g., "add", "fix", "update").
- Keep summary concise and specific.
- Use lowercase `type` and `scope`.
- Prefer one logical change per commit.

## Allowed Types

- `feat`: new functionality
- `fix`: bug fix
- `docs`: documentation only changes
- `test`: tests added/updated
- `refactor`: internal code change without behavior change
- `perf`: performance improvement
- `chore`: tooling/config/maintenance changes

## Scope Guidance

- Use the subsystem or folder name, e.g.:
  - `backend`
  - `api`
  - `chess-backend`
  - `frontend`
  - `frontend-api`
  - `frontend-shell`
  - `frontend-chess`
  - `repo`
  - `infra`
  - `workspace`
  - `license`

## Examples

- `feat(frontend-chess): implement analysis and play routes`
- `feat(chess-backend): add commentary analysis streaming service`
- `test(frontend): add Playwright coverage for auth and history`
- `docs(project): document setup and deployment flow`
- `chore(repo): update gitignore and pre-commit hooks`

## More Examples

- `fix(api): handle missing PGN payload in chess review endpoint`
- `fix(frontend-shell): prevent redirect loop after token expiry`
- `refactor(chess-backend): split review orchestration from persistence logic`
- `refactor(frontend-foundation): extract shared table state hooks`
- `perf(frontend-chess): memoize eval chart transforms for large games`
- `perf(api): reduce repeated openings lookup queries`
- `test(chess): add regression test for commentary stream disconnects`
- `test(backend): cover startup checks for missing environment variables`
- `docs(engineering): add backend migration decision record`
- `chore(infra): align compose override service names with local dev workflow`
