# Chess Services

This folder contains chess domain service modules used by API handlers and streaming endpoints.

## Modules

- `analysis_stream.py`: analysis stream orchestration and event flow.
- `commentary_analysis_stream.py`: commentary generation over analysis streams.
- `streaming.py`: shared stream lifecycle/helpers.
- `review_service.py`: game review assembly and evaluation workflow.
- `persistence.py`: persistence boundary for snapshots/reviews/history.
- `lichess.py`: Lichess integration and remote game fetch helpers.
- `openings.py`: opening lookup and matching utilities.
- `bedrock.py`: Bedrock model integration helpers.

## Conventions

- Keep route handlers thin; put business logic here.
- Keep external API calls isolated in integration-focused modules (`lichess.py`, `bedrock.py`).
- Keep pure domain transformations testable without framework coupling.

