.DEFAULT_GOAL := help

help:
	@echo "make run-local        — start the MCP server (stdio, local)"
	@echo "make run-remote       — start the MCP server (HTTP, remote)"
	@echo "make test             — run unit tests"
	@echo "make test-integration — run integration tests (temp db)"
	@echo "make test-smoke       — run smoke tests (live db)"
	@echo "make test-all         — run all tests"
	@echo "make test-coverage    — unit + integration with coverage report"
	@echo "make purge-deleted    — hard-delete soft-deleted notes older than 90 days"
	@echo "make purge-deleted-30 — hard-delete soft-deleted notes older than 30 days"
	@echo "make health           — quick health check via Python"
	@echo "make clean            — remove __pycache__ and .pyc files"

run-local:
	PKB_ENV=local python3 main.py

# NOTE[remote]: use this target when deploying
run-remote:
	PKB_ENV=remote python3 main.py

test:
	python3 -m pytest tests/unit/ -v --tb=short

test-integration:
	python3 -m pytest tests/integration/ -v --tb=short

test-smoke:
	python3 -m pytest tests/smoke/ -v --tb=short -m smoke

test-all:
	python3 -m pytest tests/ -v --tb=short

test-coverage:
	python3 -m pytest tests/unit/ tests/integration/ \
	  --cov=src --cov-report=term-missing --cov-report=html \
	  --tb=short

purge-deleted:
	@echo "Purging soft-deleted notes older than 90 days..."
	@python3 -c "\
from src.store.fts import FTSStore; \
store = FTSStore(); \
count = store.purge(older_than_days=90); \
print(f'Purged {count} permanently deleted notes.')"

purge-deleted-30:
	@echo "Purging soft-deleted notes older than 30 days..."
	@python3 -c "\
from src.store.fts import FTSStore; \
store = FTSStore(); \
count = store.purge(older_than_days=30); \
print(f'Purged {count} permanently deleted notes.')"

health:
	python3 -c "from src.store import storage; print('SQLite OK:', storage.fts.db_path); print('ChromaDB OK:', storage.vector.collection.name)"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete
