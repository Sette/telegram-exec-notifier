.PHONY: help install lint lint-check format test run

help:
	@echo "Targets: install, lint, lint-check, format, test, run"

install:
	@echo "--> Installing dependencies"
	uv sync --group dev

format:
	@echo "--> Formatting"
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

lint-check:
	@echo "--> Running linter check"
	uv run ruff format --check src/ tests/
	uv run ruff check src/ tests/
	uv run pylint src/

lint:
	@echo "--> Running linter"
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/
	uv run pylint src/

test:
	@echo "--> Running tests"
	uv run pytest -v --cov=telegram_exec_notifier --cov-report=term-missing

run:
	uv run telegram-exec-notifier
