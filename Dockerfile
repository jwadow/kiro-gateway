# Kiro Gateway - Docker Image

FROM python:3.10-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN groupadd -r kiro && useradd -r -g kiro kiro

WORKDIR /app
RUN chown kiro:kiro /app

# Install dependencies (cached layer)
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY --chown=kiro:kiro . .

# Remove runtime files that should not be in image
RUN rm -f credentials.json state.json

# Create directory for debug logs
RUN mkdir -p debug_logs && chown -R kiro:kiro debug_logs

USER kiro

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

CMD ["python", "main.py"]
