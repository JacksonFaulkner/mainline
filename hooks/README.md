# Hooks Guide

This folder contains template-generation hooks.

## What It Does

- `post_gen_project.py`: normalizes line endings for all `*.sh` files to LF after project generation.

## Why It Exists

- Prevents mixed line ending issues across macOS/Linux/CI environments.
- Keeps shell scripts executable and consistent after Copier-based generation.

