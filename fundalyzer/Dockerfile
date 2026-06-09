# Stage 1: Build React frontend
FROM node:20-slim AS frontend
WORKDIR /webapp
COPY webapp/package*.json ./
RUN npm install
COPY webapp/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy built frontend
COPY --from=frontend /webapp/dist ./webapp/dist

# Install Python package
COPY pyproject.toml ./
COPY fundalyzer/ ./fundalyzer/
RUN pip install --no-cache-dir -e ".[api]"

# Railway injects $PORT; default to 8000 locally
ENV PORT=8000
EXPOSE 8000

CMD uvicorn fundalyzer.api.main:app --host 0.0.0.0 --port $PORT
