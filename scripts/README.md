# Scripts Guide

This folder contains root-level helper scripts used during local development and CI-like checks.

## Scripts

- `generate-client.sh`: regenerate frontend API client from backend OpenAPI.
- `test.sh`: project test runner wrapper.
- `test-local.sh`: local test helper with environment-specific behavior.

## Notes

- Prefer these wrappers over ad-hoc commands when available.
- If script behavior changes, update this file with the expected inputs/outputs.
