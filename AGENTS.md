# AGENTS.md - Guide for AI Agents Working in Kiro Gateway

This document provides essential information for AI agents (Claude, GPT, etc.) working in the Kiro Gateway codebase.

## Project Philosophy

**Kiro Gateway is a transparent proxy with minimal, purposeful modifications.**

### Core Principles

1. **Transparency First**
   - The gateway preserves the user's original intent and request structure
   - Modifications are made only when necessary to work around Kiro API limitations or to add opt-in enhancements
   - We fix API quirks, not user decisions

2. **Minimal Intervention**
   - Changes to requests are surgical and well-justified
   - We add capabilities (like extended thinking) but never remove user content
   - Every modification must serve a clear purpose: fixing validation issues, adding optional features, or improving compatibility

3. **User Control**
   - All optional enhancements must be configurable
   - Users can disable features to get native Kiro API behavior
   - The gateway respects user choices about conversation structure and content

4. **Clear Boundaries**
   - ✅ **We fix**: API validation quirks, format incompatibilities, authentication flows
   - ✅ **We add (optionally)**: Enhanced features that Kiro API doesn't provide natively
   - ❌ **We don't modify**: User's conversation content, context decisions, message priorities
   - ❌ **We don't decide**: What messages to keep, what to trim, what's "important"

5. **Responsibility Separation**
   - Gateway handles API-level issues
   - Client handles content-level decisions
   - Model handles capacity limitations

6. **Systems Over Patches**
   - When solving a problem, we build systems that handle entire classes of issues, not one-off fixes
   - Even if a quick if-else would work, we invest time in creating proper abstractions and dedicated modules
   - Solutions should be easily extensible without modifying core logic
   - We prefer spending a few extra minutes on architecture that scales over quick hacks that accumulate technical debt
   - Every fix is an opportunity to create infrastructure that prevents similar problems in the future

7. **Paranoid Testing Philosophy**
   - Every commit must include tests - no exceptions
   - Tests exist to break code, not to confirm it works
   - Happy path alone is worthless - we test edge cases, error scenarios, boundary conditions, and malformed inputs
   - If you can't think of ways to break your code, you haven't thought hard enough
   - Two basic tests are not testing - comprehensive coverage means testing every logical branch and failure mode
   - Tests are both documentation and a safety net - they should clearly show what the code does and prevent regressions

8. **Code Quality Standards**
   - Comprehensive docstrings for all functions (Google style with Args/Returns/Raises)
   - Type hints are mandatory - every function parameter and return value must be typed
   - Logging at key decision points using loguru (INFO for business logic, DEBUG for technical details, ERROR for failures)
   - Never use bare `except:` or `except Exception:` - catch specific exceptions and add context
   - Proactive tech debt cleanup - if you see hardcoded values or duplicated code, extract it immediately (constants, functions, modules)
   - No placeholders - every function must be complete and production-ready when committed

9. **User Experience First**
   - Error messages must be actionable and user-friendly, not technical jargon
   - When something fails, explain what went wrong and how to fix it
   - Configuration should be intuitive with sensible defaults
   - Debug logging exists to help users troubleshoot, not just for developers
   - Documentation is part of the feature - if users can't figure it out, it doesn't work
   - Every error should guide the user toward a solution, not leave them confused

### About "Improperly formed request" Errors

**Important**: Kiro API's "Improperly formed request" error is notoriously vague due to poor documentation from Amazon. This single error message can indicate many different validation issues:

- Message structure problems (wrong role order, missing required fields)
- Tool definition issues (invalid schemas, name length violations)
- Content format problems (malformed JSON, unsupported content types)
- Authentication or permission issues
- Undocumented API constraints

When debugging this error, systematic testing is required to identify the actual cause. The gateway fixes known validation quirks, but new edge cases may emerge as Kiro API evolves.

## Project Overview

**Kiro Gateway** is a Python FastAPI proxy server that provides OpenAI-compatible and Anthropic-compatible APIs for Kiro (Amazon Q Developer / AWS CodeWhisperer). It translates requests between different API formats and handles authentication, streaming, model resolution, and error handling.

- **Language**: Python 3.10+
- **Framework**: FastAPI with uvicorn
- **License**: AGPL-3.0
- **Main Entry Point**: `main.py`
- **Package**: `kiro/` directory

## Essential Commands

### Running the Server

```bash
# Default (host: 0.0.0.0, port: 8000)
python main.py

# Custom port
python main.py --port 9000

# Custom host and port
python main.py --host 127.0.0.1 --port 9000

# Using uvicorn directly
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Testing

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_auth_manager.py -v

# Run specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run with coverage
pip install pytest-cov
pytest --cov=kiro --cov-report=html
```

### Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Main dependencies:
# - fastapi
# - uvicorn[standard]
# - httpx
# - loguru
# - requests
# - python-dotenv
# - tiktoken
# - pytest
# - pytest-asyncio
# - hypothesis
```

### Docker (Containerization)

```bash
# Build Docker image
docker build -t kiro-gateway .

# Run with Docker (using environment variables)
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="your-secret-key" \
  -e REFRESH_TOKEN="your-refresh-token" \
  --name kiro-gateway \
  kiro-gateway

# Run with docker-compose (recommended)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop container
docker-compose down

# Rebuild after code changes
docker-compose up -d --build

# Run with custom .env file
docker-compose --env-file .env.production up -d

# Mount credentials file (Kiro IDE)
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway

# Mount kiro-cli database
docker run -d \
  -p 8000:8000 \
  -v ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli \
  -e KIRO_CLI_DB_FILE=/home/kiro/.local/share/kiro-cli/data.sqlite3 \
  -e PROXY_API_KEY="your-secret-key" \
  --name kiro-gateway \
  kiro-gateway
```

**Docker Features:**
- Single-stage optimized build
- Non-root user (`kiro`) for security
- Health check endpoint monitoring (`/health`)
- Volume mounts for credentials and debug logs
- Automatic restart on failure
- Support for all 4 authentication methods
- Resource limits (optional in docker-compose.yml)

**CI/CD Integration:**
- GitHub Actions workflow (`.github/workflows/docker.yml`)
- Automated testing before Docker build
- Docker image testing (health checks)
- Automatic push to GitHub Container Registry (ghcr.io) on main branch
- Coverage report generation

## Project Structure

```
kiro-gateway/
├── main.py                          # Application entry point
├── kiro/                            # Main package
│   ├── __init__.py                  # Package exports
│   ├── config.py                    # Configuration and constants
│   ├── auth.py                      # Authentication manager
│   ├── cache.py                     # Model metadata cache
│   ├── model_resolver.py            # Dynamic model resolution
│   ├── http_client.py               # HTTP client with retry logic
│   ├── routes_openai.py             # OpenAI API endpoints
│   ├── routes_anthropic.py          # Anthropic API endpoints
│   ├── converters_core.py           # Shared conversion logic
│   ├── converters_openai.py         # OpenAI format converters
│   ├── converters_anthropic.py      # Anthropic format converters
│   ├── streaming_core.py            # Shared streaming logic
│   ├── streaming_openai.py          # OpenAI streaming
│   ├── streaming_anthropic.py       # Anthropic streaming
│   ├── parsers.py                   # AWS SSE stream parsers
│   ├── thinking_parser.py           # Thinking block parser (FSM)
│   ├── models_openai.py             # OpenAI Pydantic models
│   ├── models_anthropic.py          # Anthropic Pydantic models
│   ├── network_errors.py            # Network error classification
│   ├── exceptions.py                # Exception handlers
│   ├── debug_logger.py              # Debug logging system
│   ├── debug_middleware.py          # Debug middleware
│   ├── tokenizer.py                 # Token counting (tiktoken)
│   └── utils.py                     # Helper utilities
├── tests/                           # Test suite
│   ├── conftest.py                  # Shared fixtures
│   ├── unit/                        # Unit tests
│   └── integration/                 # Integration tests
├── .env.example                     # Environment configuration template
├── requirements.txt                 # Python dependencies
└── pytest.ini                       # Pytest configuration
```

## Code Architecture

### Modular Design

The codebase follows a layered architecture:

1. **Routes Layer** (`routes_*.py`): FastAPI endpoints, authentication, request validation
2. **Converters Layer** (`converters_*.py`): Format translation (OpenAI/Anthropic → Kiro)
3. **Streaming Layer** (`streaming_*.py`): SSE stream processing (Kiro → OpenAI/Anthropic)
4. **Core Services**: Auth, HTTP client, model resolution, caching
5. **Parsers**: AWS event stream parsing, thinking block extraction
6. **Models**: Pydantic models for validation

### Key Components

#### Authentication (`auth.py`)

- **KiroAuthManager**: Manages token lifecycle
- Supports multiple auth methods:
  - JSON credentials file (Kiro IDE)
  - Environment variables (refresh token)
  - SQLite database (kiro-cli)
  - AWS SSO OIDC (Builder ID, Enterprise)
- Auto-detects auth type based on credentials
- Thread-safe token refresh with asyncio.Lock
- Automatic refresh before expiration

#### Model Resolution (`model_resolver.py`)

4-layer resolution pipeline:
1. **Normalize Name**: Convert client formats to Kiro format (dashes→dots, strip dates)
2. **Check Dynamic Cache**: Models from /ListAvailableModels API
3. **Check Hidden Models**: Manual config for undocumented models
4. **Pass-through**: Unknown models sent to Kiro (let Kiro decide)

Key principle: **We are a gateway, not a gatekeeper**. Kiro API is the final arbiter.

#### HTTP Client (`http_client.py`)

- **KiroHttpClient**: HTTP client with automatic retry logic
- Handles errors:
  - 403: Automatic token refresh and retry
  - 429: Exponential backoff
  - 5xx: Exponential backoff
  - Timeouts: Exponential backoff
- Supports per-request clients (for streaming) and shared clients (for connection pooling)
- Network error classification with user-friendly messages

#### Streaming (`streaming_*.py`)

- Parses AWS event stream format
- Converts to OpenAI or Anthropic SSE format
- Handles thinking blocks (extended thinking mode)
- First token timeout with retry logic
- Tool call parsing and deduplication

#### Converters (`converters_*.py`)

- **Core Layer** (`converters_core.py`): Shared logic for both APIs
  - UnifiedMessage format
  - Tool processing and sanitization
  - Message merging
  - Kiro payload building
- **OpenAI Adapter** (`converters_openai.py`): OpenAI → Kiro
- **Anthropic Adapter** (`converters_anthropic.py`): Anthropic → Kiro

## Code Conventions

### Naming

- **Functions/Variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`

### Type Hints

Always use type hints:

```python
def extract_text_content(content: Any) -> str:
    """Extract text from various content formats."""
    pass

async def refresh_token(self) -> str:
    """Refresh access token."""
    pass
```

### Docstrings

Use Google-style docstrings with Args/Returns sections:

```python
def normalize_model_name(name: str) -> str:
    """
    Normalize client model name to Kiro format.
    
    Transformations applied:
    1. claude-haiku-4-5 → claude-haiku-4.5 (dash to dot for minor version)
    2. claude-haiku-4-5-20251001 → claude-haiku-4.5 (strip date suffix)
    
    Args:
        name: External model name from client
    
    Returns:
        Normalized model name in Kiro format
    
    Examples:
        >>> normalize_model_name("claude-haiku-4-5-20251001")
        'claude-haiku-4.5'
    """
    pass
```

### Logging

Use loguru for all logging:

```python
from loguru import logger

logger.info("Server starting...")
logger.warning("Token expiring soon")
logger.error(f"Failed to refresh token: {e}")
logger.debug(f"Request payload: {payload}")
```

Log levels:
- `DEBUG`: Detailed diagnostic information
- `INFO`: General informational messages
- `WARNING`: Warning messages (non-critical issues)
- `ERROR`: Error messages (failures)

### Error Handling

```python
from fastapi import HTTPException

# For API errors
raise HTTPException(status_code=401, detail="Invalid API Key")

# For internal errors with logging
try:
    result = await some_operation()
except Exception as e:
    logger.error(f"Operation failed: {e}")
    raise HTTPException(status_code=500, detail="Internal server error")
```

### Async/Await

All I/O operations are async:

```python
async def fetch_models(self) -> List[str]:
    """Fetch available models from Kiro API."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

## Testing Philosophy

### Complete Network Isolation

**Critical**: All tests MUST be completely isolated from the network.

- Global fixture `block_all_network_calls` in `tests/conftest.py` blocks all httpx requests
- Any attempt to make real network calls will fail the test
- All external services are mocked

### Test Structure

Tests follow the **Arrange-Act-Assert** pattern:

```python
@pytest.mark.asyncio
async def test_token_refresh_success(mock_env_vars, mock_kiro_token_response):
    """
    Test successful token refresh.
    
    What it does: Verifies that KiroAuthManager correctly refreshes tokens
    Purpose: Ensure token lifecycle management works correctly
    """
    # Arrange
    auth_manager = KiroAuthManager()
    mock_response = mock_kiro_token_response(expires_in=3600)
    
    # Act
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.json.return_value = mock_response
        token = await auth_manager.get_valid_token()
    
    # Assert
    assert token == mock_response["accessToken"]
    assert auth_manager._access_token == token
```

### Test Organization

- **Unit tests** (`tests/unit/`): Test individual functions/classes in isolation
- **Integration tests** (`tests/integration/`): Test component interactions
- Test classes: `Test*Success`, `Test*Errors`, `Test*EdgeCases`
- Test names: `test_<what_it_does>_<expected_result>`

### Running Tests

Always run tests after making changes:

```bash
# Quick check
pytest tests/unit/test_<module>.py -v

# Full suite
pytest -v

# With coverage
pytest --cov=kiro --cov-report=html
```

## Configuration

### Environment Variables

Configuration is loaded from `.env` file (see `.env.example`):

```bash
# Required
PROXY_API_KEY="my-super-secret-password-123"

# Authentication (choose one method)
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"  # JSON file
REFRESH_TOKEN="your_refresh_token"                        # Direct token
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3" # SQLite DB

# Optional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
SERVER_HOST="0.0.0.0"
SERVER_PORT="8000"
VPN_PROXY_URL="http://127.0.0.1:7890"  # For restricted networks

# Debug logging (off by default)
DEBUG_MODE="off"  # or "errors" or "all"
```

### Configuration Priority

1. CLI arguments: `python main.py --port 9000`
2. Environment variables: `SERVER_PORT=9000`
3. Default values: `8000`

## Important Patterns and Gotchas

### 1. Per-Request HTTP Clients for Streaming

**Critical**: Always use per-request clients for streaming to prevent CLOSE_WAIT leaks.

```python
# ✅ Correct: Per-request client for streaming
async with httpx.AsyncClient(timeout=timeout) as client:
    async with client.stream("POST", url, json=payload) as response:
        async for line in response.aiter_lines():
            yield line

# ❌ Wrong: Reusing shared client for streaming causes CLOSE_WAIT
```

### 2. Model Name Normalization

Model names are normalized before resolution:

```python
# Client sends: "claude-haiku-4-5-20251001"
# Normalized to: "claude-haiku-4.5"
# Sent to Kiro: "claude-haiku-4.5"
```

### 3. Tool Call Parsing

Kiro API may return tool calls in bracket format `[{...}]` instead of proper JSON. The parser handles this:

```python
# Kiro returns: "[{\"name\":\"get_weather\",\"arguments\":{...}}]"
# Parser extracts: [{"name": "get_weather", "arguments": {...}}]
```

### 4. Thinking Block Extraction

Extended thinking mode uses a finite state machine (FSM) to extract thinking blocks:

```python
# Input: "Let me think...<thinking>reasoning here</thinking>The answer is..."
# Extracted thinking: "reasoning here"
# Extracted content: "Let me think...The answer is..."
```

### 5. Network Error Classification

Network errors are classified into user-friendly categories:

```python
# httpx.ConnectTimeout → "Connection timeout"
# httpx.ReadTimeout → "Server response timeout"
# DNS errors → "DNS resolution failed"
```

### 6. Authentication Auto-Detection

Auth type is auto-detected based on credentials:

```python
# Has clientId/clientSecret → AWS SSO OIDC
# No clientId/clientSecret → Kiro Desktop Auth
```

### 7. Debug Logging Modes

Debug logging has three modes:

- `off`: Disabled (default, production)
- `errors`: Save logs only for failed requests (4xx, 5xx) - **recommended for troubleshooting**
- `all`: Save logs for every request (development)

Logs are saved to `debug_logs/` directory.

### 8. VPN/Proxy Support

For users in restricted networks (China, corporate):

```bash
VPN_PROXY_URL="http://127.0.0.1:7890"      # HTTP proxy
VPN_PROXY_URL="socks5://127.0.0.1:1080"    # SOCKS5 proxy
VPN_PROXY_URL="http://user:pass@proxy:8080" # With auth
```

## Common Tasks

### Adding a New Endpoint

1. Define Pydantic models in `models_*.py`
2. Add route in `routes_*.py`
3. Add converter in `converters_*.py`
4. Add streaming logic in `streaming_*.py`
5. Write tests in `tests/unit/test_routes_*.py`

### Adding a New Model

Models are dynamically fetched from Kiro API. To add a hidden model:

```python
# In config.py
HIDDEN_MODELS = [
    "claude-new-model-1.0",
]
```

### Debugging Issues

1. Enable debug logging: `DEBUG_MODE="errors"` in `.env`
2. Check `debug_logs/` directory for request/response logs
3. Run tests: `pytest tests/unit/test_<module>.py -v`
4. Check application logs (loguru output)

### Making Changes

1. **Read before editing**: Always view files before modifying
2. **Follow existing patterns**: Check similar code for style
3. **Add tests**: Write tests for new functionality
4. **Run tests**: `pytest -v` before committing
5. **Check types**: Use type hints throughout
6. **Document**: Add docstrings with Args/Returns

## API Endpoints

### OpenAI-Compatible API

- `GET /`: Health check
- `GET /health`: Detailed health check
- `GET /v1/models`: List available models
- `POST /v1/chat/completions`: Chat completions (streaming and non-streaming)

### Anthropic-Compatible API

- `POST /v1/messages`: Messages API (streaming and non-streaming)

### Authentication

All endpoints require authentication:

```bash
# OpenAI format
Authorization: Bearer {PROXY_API_KEY}

# Anthropic format
x-api-key: {PROXY_API_KEY}
```

## Dependencies and Imports

### Core Dependencies

```python
# FastAPI
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

# HTTP client
import httpx

# Logging
from loguru import logger

# Environment
from dotenv import load_dotenv
import os

# Type hints
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

# Async
import asyncio

# Pydantic
from pydantic import BaseModel, Field, validator
```

### Internal Imports

```python
# Configuration
from kiro.config import PROXY_API_KEY, REGION, APP_VERSION

# Auth
from kiro.auth import KiroAuthManager, AuthType

# Models
from kiro.models_openai import ChatCompletionRequest, ChatMessage
from kiro.models_anthropic import AnthropicMessagesRequest

# Converters
from kiro.converters_openai import build_kiro_payload
from kiro.converters_anthropic import build_kiro_payload_anthropic

# Streaming
from kiro.streaming_openai import stream_kiro_to_openai
from kiro.streaming_anthropic import stream_kiro_to_anthropic

# HTTP client
from kiro.http_client import KiroHttpClient

# Model resolution
from kiro.model_resolver import ModelResolver, normalize_model_name
```

## Git Workflow

### Recent Changes

Check recent commits for context:

```bash
git log --oneline -20
```

Recent features:
- Network error classification with user-friendly messages
- Per-request clients for streaming (CLOSE_WAIT leak fix)
- Cursor flat format support
- Inverted model names support
- HTTP/SOCKS5 proxy support
- Enterprise Kiro IDE support
- AWS SSO OIDC authentication

### Making Commits

Follow existing commit message style:

```bash
# Format: <type>(<scope>): <description> (#issue)
# Types: feat, fix, docs, test, refactor, chore

git commit -m "feat(auth): add support for new auth method"
git commit -m "fix(streaming): handle empty chunks correctly"
git commit -m "docs: update configuration examples"
```

## Security Considerations

1. **Never log credentials**: Tokens, API keys, passwords
2. **Sanitize errors**: Don't expose internal details to clients
3. **Validate input**: Use Pydantic models for all requests
4. **Use HTTPS**: In production, always use HTTPS
5. **Rate limiting**: Consider adding rate limiting for production

## Performance Considerations

1. **Connection pooling**: Use shared httpx.AsyncClient for non-streaming requests
2. **Per-request clients**: Use per-request clients for streaming to prevent leaks
3. **Async everywhere**: All I/O operations are async
4. **Caching**: Model metadata is cached to reduce API calls
5. **Streaming**: Use streaming for large responses to reduce memory usage

## Troubleshooting

### Tests Failing

```bash
# Check if dependencies are installed
pip install -r requirements.txt

# Run specific test with verbose output
pytest tests/unit/test_<module>.py::test_<name> -v -s

# Check for network isolation violations
# All tests should pass without internet connection
```

### Server Not Starting

```bash
# Check if port is already in use
lsof -i :8000  # Linux/macOS
netstat -ano | findstr :8000  # Windows

# Use different port
python main.py --port 9000

# Check environment variables
cat .env
```

### Authentication Errors

```bash
# Check credentials file exists
ls -la ~/.aws/sso/cache/

# Check environment variables
echo $REFRESH_TOKEN
echo $KIRO_CREDS_FILE

# Enable debug logging
DEBUG_MODE="errors" python main.py
```

## Resources

- **README.md**: User-facing documentation
- **tests/README.md**: Testing documentation
- **.env.example**: Configuration template
- **GitHub Issues**: https://github.com/jwadow/kiro-gateway/issues

## Summary

Kiro Gateway is a well-architected Python FastAPI application with:

- ✅ Modular design with clear separation of concerns
- ✅ Comprehensive test suite with complete network isolation
- ✅ Type hints and docstrings throughout
- ✅ Async/await for all I/O operations
- ✅ Automatic retry logic and error handling
- ✅ Dynamic model resolution
- ✅ Multiple authentication methods
- ✅ Streaming support for both OpenAI and Anthropic APIs
- ✅ Debug logging system
- ✅ VPN/Proxy support for restricted networks

When working in this codebase:
1. **Read before editing** - Always view files first
2. **Follow patterns** - Check similar code for style
3. **Test everything** - Run `pytest -v` after changes
4. **Use type hints** - Always add type annotations
5. **Document changes** - Add docstrings with Args/Returns
6. **Isolate tests** - Never make real network calls in tests
