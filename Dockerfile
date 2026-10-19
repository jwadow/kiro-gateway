# Kiro Gateway - Docker Image
# Optimized single-stage build on Alpine for a minimal, low-CVE footprint.

FROM python:3.13-alpine

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Fail the build if any dependency lacks a musl (musllinux) wheel instead of
    # silently attempting a source build. All current deps ship musl wheels, so
    # no compiler toolchain is needed in the image.
    PIP_ONLY_BINARY=:all:

# Apply available base package upgrades
RUN apk update && apk upgrade --no-cache

# Create non-root user for security (busybox adduser/addgroup)
RUN addgroup -S kiro && adduser -S -G kiro kiro

# Set working directory and give ownership to kiro user
WORKDIR /app
RUN chown kiro:kiro /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
# Install runtime dependencies, then remove pip and its vendored packages.
# pip is only needed at build time; leaving it in the final image exposes its
# vendored copies of msgpack/setuptools to CVE scanners (e.g. Trivy) even though
# they are never imported by the gateway at runtime.
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.13/site-packages/pip* \
              /usr/local/bin/pip*

# Copy application code
COPY --chown=kiro:kiro . .

# Remove runtime files that should not be in image
# (in case they were copied from build context or cache)
RUN rm -f credentials.json state.json

# Create directory for debug logs with proper permissions
RUN mkdir -p debug_logs && chown -R kiro:kiro debug_logs

# Switch to non-root user
USER kiro

# Expose port
EXPOSE 8000

# Health check
# Using httpx (our main HTTP library) instead of requests
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Run the application
CMD ["python", "main.py"]
