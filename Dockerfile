# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and source code first
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install the package and dependencies
RUN pip install --no-cache-dir -e .

# Create directory for sqlite database and logs
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Start FastAPI server with ADK Web UI
CMD ["python3", "-m", "google.adk.cli.cli", "web", "--host", "0.0.0.0", "--port", "8000", "--session_service_uri", "sqlite:////app/data/agent_sessions.db", "src/code_review_agent"]
