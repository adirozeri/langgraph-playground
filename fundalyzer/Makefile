.PHONY: install dev build start lint test

# Install Python + Node dependencies
install:
	pip install -e ".[dev,api]"
	cd webapp && npm install

# Development: API on :8000, Vite dev server on :5173 (proxied)
dev:
	@echo "Starting Fundalyzer dev servers…"
	@trap 'kill 0' INT; \
	uvicorn fundalyzer.api.main:app --reload --port 8000 & \
	cd webapp && npm run dev & \
	wait

# Build the React app into webapp/dist/
build:
	cd webapp && npm run build

# Production: FastAPI serves the built bundle
start: build
	uvicorn fundalyzer.api.main:app --port 8000 --host 0.0.0.0

lint:
	ruff check .
	ruff format --check .

test:
	pytest -v
