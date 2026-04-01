.DEFAULT_GOAL := help

help:
	@echo "make run-local   — start the MCP server (stdio, local)"
	@echo "make run-remote  — start the MCP server (HTTP, remote)"
	@echo "make test        — run all tests"
	@echo "make health      — quick health check via Python"
	@echo "make clean       — remove __pycache__ and .pyc files"

run-local:
	PKB_ENV=local python3 main.py

# NOTE[remote]: use this target when deploying
run-remote:
	PKB_ENV=remote python3 main.py

test:
	python3 -m pytest tests/ -v

health:
	python3 -c "from src.store import storage; print('SQLite OK:', storage.fts.db_path); print('ChromaDB OK:', storage.vector.collection.name)"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -name "*.pyc" -delete
