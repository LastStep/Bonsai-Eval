.PHONY: install test test-api lint format eval telemetry clean help

help:
	@echo "Bonsai-Eval — make targets"
	@echo ""
	@echo "  install     uv sync (install/refresh deps from uv.lock)"
	@echo "  test        pytest (non-API only — no key required)"
	@echo "  test-api    pytest (API tests — requires ANTHROPIC_API_KEY)"
	@echo "  lint        ruff check + mypy"
	@echo "  format      ruff format ."
	@echo "  eval        inspect eval (placeholder — needs ANTHROPIC_API_KEY)"
	@echo "  telemetry   run telemetry pipeline end-to-end"
	@echo "  clean       remove build/cache artifacts"

install:
	uv sync --all-extras

test:
	uv run pytest -m "not requires_api"

test-api:
	uv run pytest -m requires_api

lint:
	uv run ruff check .
	uv run mypy bonsai_eval

format:
	uv run ruff format .

# `eval` will fail without ANTHROPIC_API_KEY — that's documented.
eval:
	uv run inspect eval bonsai_eval/tasks/ --model anthropic/claude-haiku-4-5

telemetry:
	uv run python -m bonsai_eval.telemetry.run_all

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
