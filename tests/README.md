# Tests for Kiro Gateway

A comprehensive set of unit and integration tests for Kiro Gateway, providing full coverage of all system components.

## Testing Philosophy: Complete Network Isolation

**The key principle of this test suite is 100% isolation from real network requests.**

This is achieved through a global, automatically applied fixture `block_all_network_calls` in `tests/conftest.py`. It intercepts and blocks any attempts by `httpx.AsyncClient` to establish connections at the application level.

**Benefits:**
1.  **Reliability**: Tests don't depend on external API availability or network state.
2.  **Speed**: Absence of real network delays makes test execution instant.
3.  **Security**: Guarantees that test runs never use real credentials.

Any attempt to make an unauthorized network call will result in immediate test failure with an error, ensuring strict isolation control.

## Running Tests

### Installing Dependencies

```bash
# Main project dependencies
pip install -r requirements.txt

# Additional testing dependencies
pip install pytest pytest-asyncio hypothesis
```

### Running All Tests

```bash
# Run the entire test suite
pytest

# Run with verbose output
pytest -v

# Run with verbose output and coverage
pytest -v -s --tb=short

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run a specific file
pytest tests/unit/test_auth_manager.py -v

# Run a specific test
pytest tests/unit/test_auth_manager.py::TestKiroAuthManagerInitialization::test_initialization_stores_credentials -v
```

### pytest Options

```bash
# Stop on first failure
pytest -x

# Show local variables on errors
pytest -l

# Run in parallel mode (requires pytest-xdist)
pip install pytest-xdist
pytest -n auto
```

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures and utilities
├── unit/                            # Unit tests for individual components
│   ├── test_auth_manager.py        # KiroAuthManager tests
│   ├── test_cache.py               # ModelInfoCache tests (is_valid_model, add_hidden_model)
│   ├── test_config.py              # Configuration tests (SERVER_HOST, SERVER_PORT, LOG_LEVEL, etc.)
│   ├── test_converters_anthropic.py # Anthropic Messages API → Kiro converter tests
│   ├── test_converters_core.py     # Shared conversion logic tests (UnifiedMessage, merging, truncation recovery system prompt)
│   ├── test_converters_openai.py   # OpenAI Chat API → Kiro converter tests
│   ├── test_debug_logger.py        # DebugLogger tests (off/errors/all modes)
│   ├── test_debug_middleware.py    # DebugLoggerMiddleware tests (endpoint filtering, mode handling)
│   ├── test_exceptions.py          # Exception handlers tests (validation_exception_handler, sanitize_validation_errors)
│   ├── test_http_client.py         # KiroHttpClient tests
│   ├── test_kiro_errors.py         # Kiro API error enhancement tests (CONTENT_LENGTH_EXCEEDS_THRESHOLD, unknown errors)
│   ├── test_main_cli.py            # CLI argument parsing tests (--host, --port)
│   ├── test_mcp_tools.py           # MCP Tools tests (WebSearch: ID generation, MCP API calls, SSE emulation, query extraction)
│   ├── test_model_resolver.py      # Dynamic Model Resolution System tests
│   ├── test_models_anthropic.py    # Anthropic Pydantic models tests (all content blocks, tools, streaming, server-side tools)
│   ├── test_models_openai.py       # OpenAI Pydantic models tests (messages, tools, responses, streaming)
│   ├── test_network_errors.py      # Network error handling tests
│   ├── test_parsers.py             # AwsEventStreamParser tests (JSON truncation diagnostics, truncation recovery integration)
│   ├── test_routes_anthropic.py    # Anthropic API endpoint tests (/v1/messages, truncation recovery, WebSearch auto-injection and native detection)
│   ├── test_routes_openai.py       # OpenAI API endpoint tests (/v1/chat/completions, truncation recovery, WebSearch auto-injection)
│   ├── test_streaming_anthropic.py # Anthropic streaming response tests (truncation detection, stop_reason priority, initial_response reuse)
│   ├── test_streaming_core.py      # Shared streaming logic tests (first-token retry, initial_response parameter)
│   ├── test_streaming_openai.py    # OpenAI streaming response tests (truncation detection, finish_reason priority, initial_response reuse)
│   ├── test_thinking_parser.py     # ThinkingParser tests (FSM for thinking blocks)
│   ├── test_tokenizer.py           # Tokenizer tests (tiktoken)
│   ├── test_truncation_recovery.py # Truncation Recovery System tests (synthetic message generation)
│   ├── test_truncation_state.py    # Truncation state cache tests (save/retrieve, one-time retrieval, thread safety)
│   └── test_vpn_proxy.py           # VPN/Proxy configuration tests (environment variables, URL normalization, NO_PROXY)
├── integration/                     # Integration tests for full flow
│   └── test_full_flow.py           # End-to-end tests
└── README.md                        # This file
```

## Testing Philosophy

### Principles

1. **Isolation**: Each test is completely isolated from external services through mocks
2. **Detail**: Abundant print() for understanding test flow during debugging
3. **Coverage**: Tests cover not only happy path, but also edge cases and errors
4. **Security**: All tests use mock credentials, never real ones

### Test Structure (Arrange-Act-Assert)

Each test follows the pattern:
1. **Arrange** (Setup): Prepare mocks and data
2. **Act** (Action): Execute the tested action
3. **Assert** (Verify): Verify result with explicit comparison

### Test Types

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Verify component interactions
- **Security tests**: Verify security system
- **Edge case tests**: Paranoid edge case checks

## Adding New Tests

When adding new tests:

1. Follow existing class structure (`Test*Success`, `Test*Errors`, `Test*EdgeCases`)
2. Use descriptive names: `test_<what_it_does>_<expected_result>`
3. Add docstring with "What it does" and "Purpose"
4. Use print() for logging test steps

## Troubleshooting

### Tests fail with ImportError

```bash
# Make sure you're in project root
cd /path/to/kiro-gateway

# pytest.ini already contains pythonpath = .
# Just run pytest
pytest
```

### Tests pass locally but fail in CI

- Check dependency versions in requirements.txt
- Ensure all mocks correctly isolate external calls

### Async tests don't work

```bash
# Make sure pytest-asyncio is installed
pip install pytest-asyncio

# Check for @pytest.mark.asyncio decorator
```

## Coverage Metrics

To check code coverage:

```bash
# Install coverage
pip install pytest-cov

# Run with coverage report
pytest --cov=kiro --cov-report=html

# View report
open htmlcov/index.html  # macOS/Linux
start htmlcov/index.html  # Windows
```

## Contacts and Support

If you find bugs or have suggestions for test improvements, create an issue in the project repository.
