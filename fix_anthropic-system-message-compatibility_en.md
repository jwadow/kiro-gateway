Branch: `fix/anthropic-system-message-compatibility`
Title: `Fix: Kiro Gateway Anthropic system message compatibility`

# Description

- Fixes Claude Code requests that place a `system` message inside the Anthropic `messages` array.
- Promotes inline system instructions into the Kiro system prompt instead of rejecting them or treating them as user input.
- Preserves the existing user/assistant conversation history and adds regression coverage.

# Root Cause

Claude Code sent a request containing `messages[1].role = "system"`. The gateway schema only accepted `user` and `assistant` roles, so Pydantic rejected the request with HTTP 422 before conversion.

## Old Logic

- `AnthropicMessage.role` was limited to `user` and `assistant`.
- The converter attempted to process every message as conversation history.
- Inline system messages could not pass validation and never reached the Kiro adapter.

## New Logic

- Allow `system` as a compatibility role in `AnthropicMessage`.
- Extract all inline system messages before conversation conversion.
- Combine extracted system text in source order and merge it with the top-level Anthropic `system` field.
- Convert only user and assistant messages into Kiro conversation history.

## Why it works

- Claude Code's actual request shape is accepted by the API model.
- System instructions retain system semantics and are not silently converted into user messages.
- Existing conversation ordering remains unchanged.
- The new tests cover extraction, ordering, content blocks, and the complete Anthropic-to-Kiro payload.

# DoD

- [x] Accept Anthropic inline system messages.
- [x] Preserve system semantics during Kiro conversion.
- [x] Add regression tests for the reported HTTP 422 shape.
- [x] Run the targeted gateway test suite.
- [x] Verify a direct gateway request and a Claude Code smoke request.

# Code Changes

- `kiro/models_anthropic.py`
  - Allows the compatibility `system` role in `AnthropicMessage`.
- `kiro/converters_anthropic.py`
  - Adds inline system-message extraction and combines it with the top-level system prompt.
  - Excludes system messages from user/assistant conversation history.
- `tests/unit/test_converters_anthropic.py`
  - Adds regression coverage for extraction, ordering, content blocks, and final payload conversion.
- `.gitignore`
  - Ignores the local Python virtual environment and normalizes the file ending.

# Validate Results

```bash
./.venv/bin/pytest -q \
  tests/unit/test_models_anthropic.py \
  tests/unit/test_converters_anthropic.py \
  tests/unit/test_routes_anthropic.py
```

Result: `249 passed, 1 warning`.

Additional smoke checks:

- Direct Anthropic-compatible gateway request: HTTP 200.
- Claude Code request through the gateway: successful response.
- Claude Code model usage: `claude-opus-5`.
- `git diff --check`: passed.

# Commit Messages

- `Fix: Kiro Gateway Anthropic system message compatibility`
  - Accepts Claude Code's inline system-message format.
  - Preserves system prompt semantics and adds regression tests.
