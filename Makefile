.PHONY: init install lint format

init:
	uv python install
	uv venv

install:
	uv sync --locked

lint:
	uv run ruff check
	uv run ruff format --check
	uv run pyright

format:
	uv run ruff check --fix
	uv run ruff format
