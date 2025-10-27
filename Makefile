.PHONY: help run chat check deps

help:
	@echo "Available targets:"
	@echo "  make run    - Start the FastAPI server with uvicorn."
	@echo "  make chat   - Launch the interactive CLI client (requires server running)."
	@echo "  make check  - Run a lightweight compile check across the project."
	@echo "  make deps   - Sync dependencies using uv."

run:
	uv run uvicorn main:app --reload --port 8000

chat:
	uv run python chat_cli.py

check:
	uv run python -m compileall main.py lib

deps:
	uv sync
