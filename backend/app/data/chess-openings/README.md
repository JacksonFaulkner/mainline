# Opening DB Drop-In Folder

Place Lichess opening TSV files (`a.tsv`, `b.tsv`, `c.tsv`, `d.tsv`, `e.tsv`) in this folder.
This repo also ships a tiny `starter.tsv` fallback so opening lookup still works out-of-the-box.

The backend opening lookup endpoint reads `*.tsv` here by default:

- `POST /api/v1/chess/openings/lookup`

You can override this path with:

- `OPENINGS_DB_DIR=/custom/path/to/openings`

If `OPENINGS_DB_DIR` points to an empty/missing directory, the backend falls back to
`backend/app/data/chess-openings/starter.tsv`.

## Quick Download

From the repo root, you can fetch the current Lichess opening files into this folder:

```bash
mkdir -p backend/app/data/chess-openings
for f in a b c d e; do
  curl -fsSL "https://raw.githubusercontent.com/lichess-org/chess-openings/master/${f}.tsv" \
    -o "backend/app/data/chess-openings/${f}.tsv"
done
```
