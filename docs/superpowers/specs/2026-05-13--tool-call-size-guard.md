# Tool Call Size Guard — Design Spec

**Date:** 2026-05-13

## Problem

Kiro API has a hard ~9KB limit on tool call output stream. When a model generates
tool call arguments larger than this (e.g., writing a large file), Kiro truncates
the stream mid-JSON without a stop event. The gateway falls back to `{}` (empty
arguments), causing the tool call to silently fail.

## Solution

Inject a system prompt addition that instructs the model to split large file writes
into chunks, using the tools available in both Claude Code and OpenCode.

## Tool Sets (Verified)

| Client | Create file | Edit file | Append |
|--------|-------------|-----------|--------|
| Claude Code | `Write` (`file_path`, `content`) | `Edit` (`file_path`, `old_string`, `new_string`) | No — use `Edit` |
| OpenCode | `write` (`filePath`, `content`) | `edit` (`filePath`, `oldString`, `newString`) | No — use `edit` |

Neither client has a dedicated append/insert tool. Appending is done via `Edit`/`edit`
by matching the last line of the file as `old_string`.

## Design

### New config constant in `kiro/config.py`

```python
# Tool Call Size Guard Settings
# Injects system prompt instruction to prevent tool call arguments exceeding
# Kiro API's ~9KB output limit (causes silent truncation to {})
TOOL_CALL_SIZE_GUARD: bool = os.getenv("TOOL_CALL_SIZE_GUARD", "true").lower() in ("true", "1", "yes")
```

Default: `true` (enabled). Users can disable with `TOOL_CALL_SIZE_GUARD=false`.

### New function in `kiro/converters_core.py`

```python
def get_tool_call_size_guard_system_addition(tools: Optional[List[UnifiedTool]]) -> str:
    """
    Returns system prompt addition that prevents large tool call arguments.
    Only injected when tools are present (no tools = no tool calls to guard).
    """
    from kiro.config import TOOL_CALL_SIZE_GUARD
    if not TOOL_CALL_SIZE_GUARD or not tools:
        return ""
    return (
        "\n\n---\n"
        "# Tool Call Size Constraint\n\n"
        "This API enforces a strict limit: tool call arguments must not exceed ~7KB "
        "(approximately 150-200 lines of code).\n\n"
        "**Rules for file operations:**\n"
        "- Never write more than ~150 lines or ~7KB of content in a single Write/write tool call\n"
        "- For larger files: write the first chunk, then use Edit/edit to append remaining "
        "content in sequential chunks (use the last line of the current file as old_string, "
        "replace it with that line plus the next chunk)\n"
        "- Edit/edit operations are not affected by this limit\n\n"
        "Violating this limit causes the tool call to silently fail with empty arguments."
    )
```

### Integration in `build_kiro_payload()` in `kiro/converters_core.py`

Add after the existing truncation recovery system addition:

```python
# Add tool call size guard instruction if tools are present
size_guard_addition = get_tool_call_size_guard_system_addition(tools)
if size_guard_addition:
    full_system_prompt = full_system_prompt + size_guard_addition if full_system_prompt else size_guard_addition.strip()
```

### `.env.example` update

Add:
```
# Tool Call Size Guard (default: true)
# Injects system prompt to prevent large file writes from being truncated by Kiro API
# TOOL_CALL_SIZE_GUARD=true
```

## Tests

Add to `tests/unit/test_converters_core.py`:

- `test_size_guard_returns_empty_when_disabled` — TOOL_CALL_SIZE_GUARD=false → ""
- `test_size_guard_returns_empty_when_no_tools` — tools=None → ""
- `test_size_guard_returns_instruction_when_tools_present` — tools present → non-empty string
- `test_size_guard_injected_into_system_prompt` — verify `build_kiro_payload` includes it
- `test_size_guard_not_injected_without_tools` — no tools → not in system prompt

## Scope

- **Files modified:** `kiro/config.py`, `kiro/converters_core.py`, `.env.example`
- **Files tested:** `tests/unit/test_converters_core.py`
- **No changes to:** routes, streaming, parsers, models

## Non-Goals

- Does NOT modify tool schemas
- Does NOT retry failed tool calls
- Does NOT truncate content on the gateway side
