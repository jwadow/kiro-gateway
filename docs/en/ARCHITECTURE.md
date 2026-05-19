# Architectural Overview: Kiro Gateway

## 1. System Purpose and Goals

The project is a high-level proxy gateway implementing the **"Adapter"** structural design pattern.

The main goal of the system is to provide transparent compatibility between multiple heterogeneous interfaces:

### Supported API Formats

| API | Endpoints | Status |
|-----|-----------|--------|
| **OpenAI** | `/v1/models`, `/v1/chat/completions` | ✅ Supported |
| **Anthropic** | `/v1/messages` | ✅ Supported |

### Architectural Model

```
┌─────────────────────────────────────────────────────────────────┐
│                          Clients                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI SDK/Tools   │       │ Anthropic SDK/Tools │         │
│  │  (Cursor, Cline,    │       │ (Claude Code,       │         │
│  │   Continue, etc.)   │       │  Anthropic SDK)     │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Kiro Gateway                               │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Adapter     │       │  Anthropic Adapter  │         │
│  │  /v1/chat/...       │       │  /v1/messages       │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
│             └──────────────┬───────────────┘                    │
│                            ▼                                    │
│             ┌─────────────────────────────┐                     │
│             │      Core Layer             │                     │
│             │  (Shared conversion logic)  │                     │
│             └──────────────┬──────────────┘                     │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Kiro API                                 │
│              (AWS CodeWhisperer Backend)                        │
└─────────────────────────────────────────────────────────────────┘
```

The system acts as a "translator", allowing the use of any tools, libraries, and IDE plugins developed for OpenAI and Anthropic ecosystems with Claude models through the Kiro API.

**Both APIs work simultaneously** on the same server without any configuration switching.

## 2. Project Structure

The project is organized as a modular Python package `kiro/`:

```
kiro-gateway/
├── main.py                    # Entry point, FastAPI application creation
├── requirements.txt           # Python dependencies
├── .env.example               # Environment configuration example
│
├── kiro/              # Main package
│   ├── __init__.py            # Package exports, version
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # SHARED LAYER - Reused by all APIs
│   │   # ═══════════════════════════════════════════════════════
│   ├── config.py              # Configuration and constants
│   ├── auth.py                # KiroAuthManager - token management
│   ├── cache.py               # ModelInfoCache - model cache
│   ├── http_client.py         # HTTP client with retry logic
│   ├── parsers.py             # AWS SSE stream parsers
│   ├── utils.py               # Helper utilities
│   ├── tokenizer.py           # Token counting (tiktoken)
│   ├── debug_logger.py        # Debug request logging
│   ├── exceptions.py          # Exception handlers
│   ├── thinking_parser.py     # Thinking blocks parser
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # CORE LAYER - Shared core for all APIs
│   │   # ═══════════════════════════════════════════════════════
│   ├── converters_core.py     # Shared Kiro payload building logic
│   ├── streaming_core.py      # Shared Kiro stream parsing logic
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # OPENAI API LAYER
│   │   # ═══════════════════════════════════════════════════════
│   ├── models_openai.py       # Pydantic models for OpenAI API
│   ├── converters_openai.py   # OpenAI → Kiro adapter
│   ├── routes_openai.py       # FastAPI routes for OpenAI
│   ├── streaming_openai.py    # Kiro → OpenAI SSE formatter
│   │
│   │   # ═══════════════════════════════════════════════════════
│   │   # ANTHROPIC API LAYER
│   │   # ═══════════════════════════════════════════════════════
│   ├── models_anthropic.py    # Pydantic models for Anthropic API
│   ├── converters_anthropic.py # Anthropic → Kiro adapter
│   ├── routes_anthropic.py    # FastAPI routes for Anthropic
│   └── streaming_anthropic.py # Kiro → Anthropic SSE formatter
│
├── tests/                     # Tests
│   ├── conftest.py            # Pytest fixtures
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
│
├── docs/                      # Documentation
│   ├── ru/                    # Russian version
│   └── en/                    # English version
│
└── debug_logs/                # Debug logs (generated when DEBUG_MODE=all or DEBUG_MODE=errors)
```

### Organization Principle: Shared Core + Thin Adapters

The architecture is built on the principle of **maximum code reuse**:

| Layer | Purpose | Files |
|-------|---------|-------|
| **Shared Layer** | Infrastructure independent of API format | `auth.py`, `http_client.py`, `cache.py`, `parsers.py`, `tokenizer.py` |
| **Core Layer** | Shared business logic for conversion | `converters_core.py`, `streaming_core.py` |
| **API Layer** | Thin adapters for specific formats | `*_openai.py`, `*_anthropic.py` |

## 3. Architectural Topology and Components

The system is built on the asynchronous `FastAPI` framework and uses an event-driven lifecycle management model (`Lifespan Events`).

### 3.1. Entry Point (`main.py`)

The `main.py` file is responsible for:

1. **Logging configuration** — Loguru setup with colored output
2. **Configuration validation** — `validate_configuration()` function checks:
   - Presence of `.env` file
   - Presence of credentials (REFRESH_TOKEN or KIRO_CREDS_FILE)
3. **Lifespan Manager** — creation and initialization of:
   - `KiroAuthManager` for token management
   - `ModelInfoCache` for model caching
4. **Error handler registration** — `validation_exception_handler` for 422 errors
5. **Route connection** — `app.include_router(router)`

### 3.2. Configuration Module (`kiro/config.py`)

Centralized storage of all settings:

| Parameter | Description | Default Value |
|-----------|-------------|---------------|
| `PROXY_API_KEY` | API key for proxy access | `changeme_proxy_secret` |
| `REFRESH_TOKEN` | Kiro refresh token | from `.env` |
| `PROFILE_ARN` | AWS CodeWhisperer profile ARN | from `.env` |
| `REGION` | AWS region | `us-east-1` |
| `KIRO_CREDS_FILE` | Path to JSON credentials file | from `.env` |
| `TOKEN_REFRESH_THRESHOLD` | Time before token refresh | 600 sec (10 min) |
| `MAX_RETRIES` | Max retry attempts | 3 |
| `BASE_RETRY_DELAY` | Base retry delay | 1.0 sec |
| `MODEL_CACHE_TTL` | Model cache TTL | 3600 sec (1 hour) |
| `DEFAULT_MAX_INPUT_TOKENS` | Default max input tokens | 200000 |
| `TOOL_DESCRIPTION_MAX_LENGTH` | Max tool description length | 10000 characters |
| `DEBUG_MODE` | Debug logging mode | `off` (off/errors/all) |
| `DEBUG_DIR` | Debug logs directory | `debug_logs` |
| `APP_VERSION` | Application version | `0.0.0` |

**Helper functions:**
- `get_kiro_refresh_url(region)` — URL for token refresh
- `get_kiro_api_host(region)` — main API host
- `get_kiro_q_host(region)` — Q API host
- `get_internal_model_id(external_model)` — model name conversion

### 3.3. Pydantic Models (`kiro/models_openai.py`)

#### Models for `/v1/models`

| Model | Description |
|-------|-------------|
| `OpenAIModel` | AI model description (id, object, created, owned_by) |
| `ModelList` | Model list for endpoint response |

#### Models for `/v1/chat/completions`

| Model | Description |
|-------|-------------|
| `ChatMessage` | Chat message (role, content, tool_calls, tool_call_id) |
| `ToolFunction` | Tool function description (name, description, parameters) |
| `Tool` | OpenAI format tool (type, function) |
| `ChatCompletionRequest` | Generation request (model, messages, stream, tools, ...) |

#### Response Models

| Model | Description |
|-------|-------------|
| `ChatCompletionChoice` | Single response variant |
| `ChatCompletionUsage` | Token information (prompt_tokens, completion_tokens, credits_used) |
| `ChatCompletionResponse` | Full response (non-streaming) |
| `ChatCompletionChunk` | Streaming chunk |
| `ChatCompletionChunkDelta` | Delta changes in chunk |
| `ChatCompletionChunkChoice` | Variant in streaming chunk |

### 3.4. State Management Layer

#### KiroAuthManager (`kiro/auth.py`)

**Role:** Stateful singleton encapsulating Kiro token management logic.

**Capabilities:**
- Loading credentials from `.env` or JSON file
- Support for `expiresAt` to check token expiration time
- Automatic token refresh 10 minutes before expiration
- Saving updated tokens back to JSON file
- Support for different AWS regions
- Unique fingerprint generation for User-Agent

**Concurrency Control:** Uses `asyncio.Lock` to protect against race conditions.

**Main methods:**
- `get_access_token()` — returns valid token, refreshing if necessary
- `force_refresh()` — forced token refresh (on 403)
- `is_token_expiring_soon()` — expiration time check

**Properties:**
- `profile_arn` — profile ARN
- `region` — AWS region
- `api_host` — API host for region
- `q_host` — Q API host for region
- `fingerprint` — unique machine fingerprint

```python
# Usage example
auth_manager = KiroAuthManager(
    refresh_token="your_token",
    region="us-east-1",
    creds_file="~/.aws/sso/cache/kiro-auth-token.json"
)
token = await auth_manager.get_access_token()
```

#### ModelInfoCache (`kiro/cache.py`)

**Role:** Thread-safe storage for model configurations.

**Population Strategy:** 
- Lazy Loading via `/ListAvailableModels`
- Cache TTL: 1 hour
- Fallback to static model list

**Main methods:**
- `update(models_data)` — cache update
- `get(model_id)` — get model information
- `get_max_input_tokens(model_id)` — get token limit
- `is_empty()` / `is_stale()` — cache state check
- `get_all_model_ids()` — list of all model IDs

### 3.5. Helper Utilities (`kiro/utils.py`)

| Function | Description |
|----------|-------------|
| `get_machine_fingerprint()` | SHA256 hash of `{hostname}-{username}-kiro-gateway` |
| `get_kiro_headers(auth_manager, token)` | Form headers for Kiro API |
| `generate_completion_id()` | ID in format `chatcmpl-{uuid_hex}` |
| `generate_conversation_id()` | UUID for conversation |
| `generate_tool_call_id()` | ID in format `call_{uuid_hex[:8]}` |

### 3.6. Conversion Layer (`kiro/converters_openai.py`)

#### Message Conversion

OpenAI messages are transformed into Kiro conversationState:

1. **System prompt** — added to the first user message
2. **Message history** — fully passed in `history` array
3. **Adjacent message merging** — messages with the same role are merged
4. **Tool calls** — OpenAI tools format support
5. **Tool results** — correct transmission of tool call results

#### Long Tool Description Handling

**Problem:** Kiro API returns error 400 for too long descriptions in `toolSpecification.description`.

**Solution:** Tool Documentation Reference Pattern
- If `description ≤ TOOL_DESCRIPTION_MAX_LENGTH` → leave as is
- If `description > TOOL_DESCRIPTION_MAX_LENGTH`:
  * In `toolSpecification.description` → reference: `"[Full documentation in system prompt under '## Tool: {name}']"`
  * In system prompt, section `"## Tool: {name}"` with full description is added

**Function:** `process_tools_with_long_descriptions(tools)` → `(processed_tools, tool_documentation)`

#### Main Functions

| Function | Description |
|----------|-------------|
| `extract_text_content(content)` | Extract text from various formats |
| `merge_adjacent_messages(messages)` | Merge adjacent messages with same role |
| `build_kiro_history(messages, model_id)` | Build history array for Kiro |
| `build_kiro_payload(request_data, conversation_id, profile_arn)` | Full payload for request |

#### Model Mapping

External model names are converted to internal Kiro IDs:

| External Name | Internal Kiro ID |
|---------------|------------------|
| `claude-opus-4-5` | `claude-opus-4.5` |
| `claude-opus-4-5-20251101` | `claude-opus-4.5` |
| `claude-haiku-4-5` | `claude-haiku-4.5` |
| `claude-haiku-4.5` | `claude-haiku-4.5` (direct passthrough) |
| `claude-sonnet-4-5` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4-5-20250929` | `CLAUDE_SONNET_4_5_20250929_V1_0` |
| `claude-sonnet-4` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-sonnet-4-20250514` | `CLAUDE_SONNET_4_20250514_V1_0` |
| `claude-3-7-sonnet-20250219` | `CLAUDE_3_7_SONNET_20250219_V1_0` |
| `auto` | `claude-sonnet-4.5` (alias) |

### 3.7. Parsing Layer (`kiro/parsers.py`)

#### AwsEventStreamParser

Advanced AWS SSE format parser with support for:

- **Bracket counting** — correct parsing of nested JSON objects
- **Content deduplication** — filtering of duplicate events
- **Tool calls** — parsing of structured and bracket-style tool calls
- **Escape sequences** — decoding of `\n` and others

#### Event Types

| Event | Description |
|-------|-------------|
| `content` | Text content of the response |
| `tool_start` | Start of tool call (name, toolUseId) |
| `tool_input` | Continuation of input for tool call |
| `tool_stop` | End of tool call |
| `usage` | Credit consumption information |
| `context_usage` | Context usage percentage |

#### Helper Functions

| Function | Description |
|----------|-------------|
| `find_matching_brace(text, start_pos)` | Find closing brace with nesting support |
| `parse_bracket_tool_calls(response_text)` | Parse `[Called func with args: {...}]` |
| `deduplicate_tool_calls(tool_calls)` | Remove duplicate tool calls |

### 3.8. Streaming (`kiro/streaming_openai.py`)

#### stream_kiro_to_openai

Async generator for transforming Kiro stream to OpenAI format.

**Functionality:**
- Parse AWS SSE stream via `AwsEventStreamParser`
- Form OpenAI `chat.completion.chunk`
- Handle tool calls (structured and bracket-style)
- Calculate usage based on `contextUsagePercentage`
- Debug logging via `debug_logger`

#### collect_stream_response

Collects full response from streaming for non-streaming mode.

### 3.9. HTTP Client (`kiro/http_client.py`)

#### KiroHttpClient

Automatic error handling with exponential backoff:

| Error Code | Action |
|------------|--------|
| `403` | Token refresh via `force_refresh()` + retry |
| `429` | Exponential backoff: `BASE_RETRY_DELAY * (2 ** attempt)` |
| `5xx` | Exponential backoff (up to MAX_RETRIES attempts) |
| Timeout | Exponential backoff |

**Delay formula:** `1s, 2s, 4s` (with `BASE_RETRY_DELAY=1.0`)

**Methods:**
- `request_with_retry(method, url, json_data, stream)` — request with retry
- `close()` — close client

Supports async context manager (`async with`).

### 3.10. Routes (`kiro/routes_openai.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check (status, message, version) |
| `/health` | GET | Detailed health check (status, timestamp, version) |
| `/v1/models` | GET | List of available models (requires API key) |
| `/v1/chat/completions` | POST | Chat completions (requires API key) |

**Authentication:** Bearer token in `Authorization` header

### 3.11. Exception Handling (`kiro/exceptions.py`)

| Function | Description |
|----------|-------------|
| `sanitize_validation_errors(errors)` | Convert bytes to strings for JSON serialization |
| `validation_exception_handler(request, exc)` | Pydantic validation error handler (422) |

### 3.12. Debug Logging (`kiro/debug_logger.py`)

**Class:** `DebugLogger` (singleton)

**Activation:** `DEBUG_MODE=all` or `DEBUG_MODE=errors` in `.env`

**Methods:**
| Method | Description |
|--------|-------------|
| `prepare_new_request()` | Clear directory for new request |
| `log_request_body(body)` | Save incoming request |
| `log_kiro_request_body(body)` | Save request to Kiro API |
| `log_raw_chunk(chunk)` | Append raw chunk from Kiro |
| `log_modified_chunk(chunk)` | Append transformed chunk |

**Files in `debug_logs/`:**
- `request_body.json` — incoming request (OpenAI format)
- `kiro_request_body.json` — request to Kiro API
- `response_stream_raw.txt` — raw stream from Kiro
- `response_stream_modified.txt` — transformed stream (OpenAI format)

### 3.13. Tokenizer (`kiro/tokenizer.py`)

**Problem:** Kiro API does not return token counts directly. Instead, the API only provides `context_usage_percentage` — the percentage of model context usage.

**Solution:** Tokenizer module based on `tiktoken` (OpenAI's Rust library) for fast token counting.

**Features:**
- Uses `cl100k_base` encoding (GPT-4), close to Claude tokenization
- Correction factor `CLAUDE_CORRECTION_FACTOR = 1.15` for improved accuracy
- Lazy initialization for faster imports
- Fallback to rough estimation if tiktoken is unavailable

**Token calculation formula in response:**
```
total_tokens = context_usage_percentage × max_input_tokens  (from Kiro API)
completion_tokens = tiktoken(response)                       (our calculation)
prompt_tokens = total_tokens - completion_tokens             (subtraction)
```

**Main functions:**

| Function | Description |
|----------|-------------|
| `count_tokens(text)` | Count tokens in text |
| `count_message_tokens(messages)` | Count tokens in message list |
| `count_tools_tokens(tools)` | Count tokens in tool definitions |
| `estimate_request_tokens(messages, tools)` | Full request token estimation |

**Debug log:**
```
[Usage] claude-opus-4-5: prompt_tokens=142211 (subtraction), completion_tokens=769 (tiktoken), total_tokens=142980 (API Kiro)
```

**Accuracy:** ~97-99.7% compared to API data.

### 3.14. Kiro API Endpoints

All URLs are dynamically formed based on the region:

*   **Token Refresh:** `POST https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
*   **List Models:** `GET https://q.{region}.amazonaws.com/ListAvailableModels`
*   **Generate Response:** `POST https://codewhisperer.{region}.amazonaws.com/generateAssistantResponse`

## 4. Detailed Data Flow

### 4.1 Multi-API Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Client      │       │  Anthropic Client   │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              │ POST /v1/chat/completions    │ POST /v1/messages
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API LAYER                                  │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  routes_openai.py   │       │ routes_anthropic.py │         │
│  │  Security Gate      │       │ Security Gate       │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
│             │                              │                    │
│             ▼                              ▼                    │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │converters_openai.py │       │converters_anthropic │         │
│  │ Extract system      │       │ System already      │         │
│  │ from messages       │       │ separate in request │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              └──────────────┬───────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE LAYER                                 │
│             ┌─────────────────────────────┐                     │
│             │    converters_core.py       │                     │
│             │  build_kiro_payload()       │                     │
│             │  build_kiro_history()       │                     │
│             │  process_tools()            │                     │
│             └──────────────┬──────────────┘                     │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SHARED LAYER                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ KiroAuthManager │  │ KiroHttpClient  │  │  ModelInfoCache │ │
│  │   (auth.py)     │  │(http_client.py) │  │   (cache.py)    │ │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘ │
└───────────┼────────────────────┼────────────────────────────────┘
            │                    │
            │                    │ POST /generateAssistantResponse
            │                    ▼
            │         ┌─────────────────────────────────────┐
            │         │              Kiro API                   │
            │         └──────────────────┬──────────────────────┘
            │                            │
            │                            │ AWS SSE Stream
            │                            ▼
┌───────────┼────────────────────────────────────────────────────┐
│           │            CORE LAYER                              │
│           │  ┌─────────────────────────────┐                   │
│           │  │    streaming_core.py        │                   │
│           │  │  parse_kiro_stream()        │                   │
│           │  │  → KiroEvent objects        │                   │
│           │  └──────────────┬──────────────┘                   │
└────────────────────────────┼───────────────────────────────────┘
                             │
              ┌──────────────┴───────────────┐
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      OUTPUT LAYER                               │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │streaming_openai.py  │       │streaming_anthropic  │         │
│  │ format_openai_sse() │       │format_anthropic_sse │         │
│  │                     │       │                     │         │
│  │ data: {...}         │       │ event: type         │         │
│  │ data: [DONE]        │       │ data: {...}         │         │
│  └──────────┬──────────┘       └──────────┬──────────┘         │
└─────────────┼──────────────────────────────┼───────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          CLIENTS                                │
│  ┌─────────────────────┐       ┌─────────────────────┐         │
│  │  OpenAI Client      │       │  Anthropic Client   │         │
│  └─────────────────────┘       └─────────────────────┘         │
└─────────────────────────────────┘
```

### 4.2 OpenAI API Flow

```
OpenAI Client
     │ POST /v1/chat/completions
     ▼
routes_openai.py ──► converters_openai.py ──► converters_core.py
     │                                              │
     │                                              ▼
     │                                        Kiro Payload
     │                                              │
     ▼                                              ▼
KiroAuthManager ──────────────────────────► KiroHttpClient
                                                   │
                                                   ▼
                                              Kiro API
                                                   │
                                                   ▼
streaming_core.py ◄─────────────────────── AWS SSE Stream
     │
     ▼
streaming_openai.py
     │
     ▼
OpenAI SSE Format ──────────────────────► OpenAI Client
```

### 4.3 Anthropic API Flow

```
Anthropic Client
     │ POST /v1/messages
     ▼
routes_anthropic.py ──► converters_anthropic.py ──► converters_core.py
     │                                                    │
     │                                                    ▼
     │                                              Kiro Payload
     │                                                    │
     ▼                                                    ▼
KiroAuthManager ──────────────────────────────────► KiroHttpClient
                                                         │
                                                         ▼
                                                    Kiro API
                                                         │
                                                         ▼
streaming_core.py ◄─────────────────────────────── AWS SSE Stream
     │
     ▼
streaming_anthropic.py
     │
     ▼
Anthropic SSE Format ──────────────────────────► Anthropic Client
```

## 5. Available Models

| Model | Description | Credits |
|-------|-------------|---------|
| `claude-opus-4-5` | Top-tier model | ~2.2 |
| `claude-opus-4-5-20251101` | Top-tier model (version) | ~2.2 |
| `claude-sonnet-4-5` | Enhanced model | ~1.3 |
| `claude-sonnet-4-5-20250929` | Enhanced model (version) | ~1.3 |
| `claude-sonnet-4` | Balanced model | ~1.3 |
| `claude-sonnet-4-20250514` | Balanced (version) | ~1.3 |
| `claude-haiku-4-5` | Fast model | ~0.4 |
| `claude-3-7-sonnet-20250219` | Legacy model | ~1.0 |

## 6. Configuration

### Environment Variables (.env)

```env
# Required
REFRESH_TOKEN="your_kiro_refresh_token"
PROXY_API_KEY="your_proxy_secret"

# Optional
PROFILE_ARN="arn:aws:codewhisperer:..."
KIRO_REGION="us-east-1"
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Debug
DEBUG_MODE="off"  # off/errors/all
DEBUG_DIR="debug_logs"

# Limits
TOOL_DESCRIPTION_MAX_LENGTH="10000"
```

### JSON Credentials File (optional)

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1"
}
```

## 7. API Endpoints

### 7.1 Common Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health check |

### 7.2 OpenAI-compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List of available models |
| `/v1/chat/completions` | POST | Chat completions (streaming/non-streaming) |

**Authentication:** `Authorization: Bearer {PROXY_API_KEY}`

### 7.3 Anthropic-compatible Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/messages` | POST | Messages API (streaming/non-streaming) |

**Authentication:** `x-api-key: {PROXY_API_KEY}` + `anthropic-version: 2023-06-01`

### 7.4 Admin Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/accounts/usage` | GET | Account pool status + Kiro credits usage |

**Authentication:** `Authorization: Bearer {PROXY_API_KEY}`

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `account_id` | string | — | Filter to a single account |
| `force_refresh` | bool | `false` | Bypass cache (min 30 s per account) |

**Response shape:**

| Field | Type | Description |
|-------|------|-------------|
| `object` | `"list"` | Always `"list"` |
| `fetched_at` | ISO 8601 | Server time of response |
| `accounts[].account_id` | string | Credential file path (account identifier) |
| `accounts[].enabled` | bool | False if account failed to initialize |
| `accounts[].circuit_state` | `"healthy"\|"tripped"` | Circuit-breaker state (tripped = ≥3 consecutive failures) |
| `accounts[].stats` | object | Gateway-level request counters |
| `accounts[].profile` | object\|null | Kiro profile info (cached 24 h) |
| `accounts[].usage` | object\|null | Credits usage summary (cached 5 min) |
| `accounts[].usage.current_usage` | float | Credits used this period |
| `accounts[].usage.usage_limit` | float | Total credits limit for this period |
| `accounts[].usage.percent_used` | float | `current_usage / usage_limit × 100` |
| `accounts[].usage.next_reset_at` | ISO 8601 | Next billing period reset time |
| `accounts[].stale` | bool | True if cached data could not be refreshed |
| `accounts[].error` | string\|null | Error message if last fetch failed |

**New module: `kiro/usage_limits.py`**

| Symbol | Description |
|--------|-------------|
| `UsageCache` | Per-account TTL cache (5 min usage, 24 h profile) |
| `UsageLimitsResult` | Dataclass wrapping raw `GetUsageLimits` response |
| `ProfileResult` | Dataclass wrapping raw `GetProfile` response |
| `fetch_usage_limits(auth_manager)` | Calls `GET /getUsageLimits`, returns `UsageLimitsResult` |
| `fetch_profile(auth_manager)` | Calls `POST /GetProfile`, returns `ProfileResult` |
| `AccountUsageService` | Singleton coordinating cache + per-account `asyncio.Lock` |

### 7.5 Format Comparison

| Aspect | OpenAI | Anthropic |
|--------|--------|-----------|
| System prompt | In `messages` with `role: "system"` | Separate `system` field |
| Content | String or array | Always array of content blocks |
| Stop reason | `finish_reason: "stop"` | `stop_reason: "end_turn"` |
| Usage | `prompt_tokens`, `completion_tokens` | `input_tokens`, `output_tokens` |
| Streaming | `data: {...}\n\n` + `data: [DONE]` | `event: type\ndata: {...}\n\n` |
| Tool format | `{type: "function", function: {...}}` | `{name: "...", input_schema: {...}}` |

## 8. Implementation Features

### Tool Calling

Support for OpenAI-compatible tools format:

```json
{
  "tools": [{
    "type": "function",
    "function": {
      "name": "get_weather",
      "description": "Get weather for a location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {"type": "string"}
        }
      }
    }
  }]
}
```

### Streaming

Full SSE streaming support with correct OpenAI format:

```
data: {"id":"chatcmpl-...","object":"chat.completion.chunk",...}

data: [DONE]
```

### Debugging

When `DEBUG_MODE=all` or `DEBUG_MODE=errors`, all requests and responses are logged in `debug_logs/`:
- `request_body.json` — incoming request
- `kiro_request_body.json` — request to Kiro API
- `response_stream_raw.txt` — raw stream from Kiro
- `response_stream_modified.txt` — transformed stream

## 9. Extensibility

### Adding a New API Format

The modular architecture allows easy addition of support for other API formats. Thanks to the Core Layer, most of the logic is already implemented.

#### Steps to Add a New Format (e.g., Gemini)

1. **Create models** — `models_gemini.py`
   ```python
   class GeminiRequest(BaseModel):
       """Pydantic model for Gemini request."""
       contents: List[GeminiContent]
       ...
   ```

2. **Create conversion adapter** — `converters_gemini.py`
   ```python
   from kiro.converters_core import build_kiro_payload
   
   def gemini_to_kiro(request: GeminiRequest, ...) -> dict:
       """Converts Gemini request to Kiro payload."""
       # Extract data from Gemini format
       system_prompt = extract_system_instruction(request)
       messages = convert_gemini_contents(request.contents)
       tools = convert_gemini_tools(request.tools)
       
       # Use shared core
       return build_kiro_payload(
           messages=messages,
           system_prompt=system_prompt,
           tools=tools,
           ...
       )
   ```

3. **Create streaming formatter** — `streaming_gemini.py`
   ```python
   from kiro.streaming_core import parse_kiro_stream
   
   async def stream_to_gemini(response, ...) -> AsyncGenerator[str, None]:
       """Formats Kiro events to Gemini SSE."""
       async for event in parse_kiro_stream(response):
           yield format_gemini_chunk(event)
   ```

4. **Create routes** — `routes_gemini.py`
   ```python
   router = APIRouter()
   
   @router.post("/v1beta/models/{model}:generateContent")
   async def generate_content(request: GeminiRequest):
       ...
   ```

5. **Connect in main.py**
   ```python
   from kiro.routes_gemini import router as gemini_router
   app.include_router(gemini_router)
   ```

### What Gets Reused Automatically

When adding a new format, the following components work out of the box:

| Component | Functionality |
|-----------|---------------|
| `auth.py` | Kiro token management |
| `http_client.py` | HTTP with retry logic |
| `cache.py` | Model cache |
| `parsers.py` | AWS SSE parsing |
| `tokenizer.py` | Token counting |
| `converters_core.py` | Kiro payload building |
| `streaming_core.py` | Kiro stream parsing |

## 10. Dependencies

Main project dependencies (from `requirements.txt`):

| Package | Purpose |
|---------|---------|
| `fastapi` | Asynchronous web framework |
| `uvicorn` | ASGI server |
| `httpx` | Asynchronous HTTP client |
| `pydantic` | Data validation and models |
| `python-dotenv` | Environment variable loading |
| `loguru` | Advanced logging |
| `tiktoken` | Fast token counting |
