# Multi-stage Docker build for optimal image size and security
# Stage 1: Builder
FROM python:3.11-slim as builder

# Set build arguments
ARG PYTHON_VERSION=3.11

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app /app/logs /app/data && \
    chown -R appuser:appuser /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application files
COPY --chown=appuser:appuser server.py .
COPY --chown=appuser:appuser healthcheck.py .
COPY --chown=appuser:appuser .env.example .

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    LOG_LEVEL=INFO \
    PORT=8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python healthcheck.py || exit 1

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "server.py"]

# Labels for metadata
LABEL maintainer="Patrick Carmichael <patrick@example.com>" \
      version="1.0.0" \
      description="Production-ready MCP server for changedetection.io" \
      org.opencontainers.image.source="https://github.com/patrickcarmichael/changedetection-mcp-server"
