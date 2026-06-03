# Kiro Gateway - Docker Image
# Optimized single-stage build

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security (UID 1000 to match typical host user for volume permissions)
RUN groupadd -g 1000 kiro && useradd -u 1000 -g 1000 kiro

# Set working directory and give ownership to kiro user
WORKDIR /app
RUN chown kiro:kiro /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=kiro:kiro . .

# Remove runtime files that should not be in image
# (in case they were copied from build context or cache)
RUN rm -f credentials.json state.json

# Create directory for debug logs with proper permissions
RUN mkdir -p debug_logs && chown -R kiro:kiro debug_logs

# Create writable directory for the gateway's own copy of the kiro-cli database
RUN mkdir -p /home/kiro/.local/share/kiro-cli && chown -R kiro:kiro /home/kiro

# Switch to non-root user
USER kiro

# Expose port
EXPOSE 8000

# Health check
# Using httpx (our main HTTP library) instead of requests
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Entrypoint copies seed database then runs CMD
ENTRYPOINT ["./entrypoint.sh"]

# Run the application
CMD ["python", "main.py"]
