#!/bin/sh
set -eu
uv run --quiet ruff check --fix --quiet "$@"
uv run --quiet ruff format --quiet "$@"
