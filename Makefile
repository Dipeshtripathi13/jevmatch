.PHONY: install dev api web test lint format clean

install:
	uv sync --extra dev
	cd web && npm install

dev:
	@trap 'kill 0' INT TERM EXIT; \
	uv run uvicorn api.main:app --reload --port 8000 & \
	cd web && npm run dev & \
	wait

api:
	uv run uvicorn api.main:app --reload --port 8000

web:
	cd web && npm run dev

test:
	uv run pytest
	cd web && npm run build

lint:
	uv run ruff check .
	cd web && npm run lint

format:
	uv run ruff format .
	cd web && npm run format

clean:
	rm -rf .pytest_cache .ruff_cache web/dist
