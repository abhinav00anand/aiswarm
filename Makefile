.PHONY: install test test-unit test-integration lint format typecheck clean run-api run-worker docker-up docker-down index

PYTHON := python3
PIP    := pip3
PYTEST := python3 -m pytest

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt
	$(PIP) install ruff mypy black pre-commit

test: test-unit

test-unit:
	$(PYTEST) tests/unit/ -v --tb=short -q

test-integration:
	$(PYTEST) tests/integration/ -v --tb=short -m integration

test-all:
	$(PYTEST) tests/ -v --tb=short

lint:
	python3 -m ruff check blynx/ apps/ tests/ --fix

format:
	python3 -m ruff format blynx/ apps/ tests/

typecheck:
	python3 -m mypy blynx/ --ignore-missing-imports

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .mypy_cache .ruff_cache .pytest_cache

run-api:
	$(PYTHON) -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

run-worker:
	$(PYTHON) -m blynx.worker.local_worker

index:
	blynx index --root .

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

help:
	@echo "Blynx Makefile targets:"
	@echo "  install          Install all dependencies"
	@echo "  test             Run unit tests"
	@echo "  test-integration Run integration tests (requires API keys)"
	@echo "  lint             Lint with ruff"
	@echo "  format           Format with ruff"
	@echo "  typecheck        Type-check with mypy"
	@echo "  run-api          Start the FastAPI server"
	@echo "  run-worker       Start a local worker"
	@echo "  docker-up        Start all services with Docker Compose"
	@echo "  docker-down      Stop all services"
	@echo "  index            Index the repository for RAG"
