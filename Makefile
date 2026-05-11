.PHONY: help sync run test token

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  sync   - Sync dependencies"
	@echo "  run    - Run the server"
	@echo "  test   - Run tests"
	@echo "  token  - Sync token from AWS SSO"

sync:
	uv sync

run:
	uv run python main.py

test:
	uv run pytest

token:
	uv run python sync_token.py
