# Tool Call Size Guard Implementation Plan

> **For agentic workers:** Use subagent-driven-development (recommended) or executing-plans skill.

**Goal:** Inject a system prompt addition that instructs the model to split large file writes into chunks, preventing Kiro API's ~9KB tool call output truncation.  
**Architecture:** New config constant + new function in `converters_core.py` following the existing `get_thinking_system_prompt_addition()` pattern. Injected in `build_kiro_payload()` only when tools are present.  
**Tech Stack:** Python, pytest

---

### Task 1: Add config constant

**Files:**
- Modify: `kiro/config.py` (after TRUNCATION_RECOVERY block, ~line 329)

- [ ] **Step 1: Add constant**

In `kiro/config.py`, after the `TRUNCATION_RECOVERY` line, add:

```python
# ==================================================================================================
# Tool Call Size Guard Settings
# ==================================================================================================

# Inject system prompt instruction to prevent tool call arguments exceeding
# Kiro API's ~9KB output limit (causes silent truncation to empty {})
# Default: true (enabled) — disable only if you handle chunking at the client level
TOOL_CALL_SIZE_GUARD: bool = os.getenv("TOOL_CALL_SIZE_GUARD", "true").lower() in ("true", "1", "yes")
```

- [ ] **Step 2: Verify import works**
```bash
cd /root/project/kiro-gateway && python3 -c "from kiro.config import TOOL_CALL_SIZE_GUARD; print(TOOL_CALL_SIZE_GUARD)"
```
Expected: `True`

---

### Task 2: Add function + integration in converters_core.py

**Files:**
- Modify: `kiro/converters_core.py`

- [ ] **Step 1: Add function after `get_truncation_recovery_system_addition()`**

```python
def get_tool_call_size_guard_system_addition(tools: Optional[List["UnifiedTool"]]) -> str:
    """
    Generate system prompt addition that prevents large tool call arguments.

    Kiro API silently truncates tool call output streams exceeding ~9KB,
    causing tool calls to arrive with empty arguments ({}). This instruction
    tells the model to split large file writes into chunks using Edit/edit.

    Only injected when tools are present — no tools means no tool calls to guard.

    Args:
        tools: List of tools in the current request (or None)

    Returns:
        System prompt addition text, or empty string if guard is disabled or no tools
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

- [ ] **Step 2: Integrate in `build_kiro_payload()` after truncation_system_addition block**

Find this block in `build_kiro_payload()`:
```python
    # Add truncation recovery legitimization to system prompt if enabled
    truncation_system_addition = get_truncation_recovery_system_addition()
    if truncation_system_addition:
        full_system_prompt = full_system_prompt + truncation_system_addition if full_system_prompt else truncation_system_addition.strip()
```

Add immediately after:
```python
    # Add tool call size guard instruction if tools are present
    size_guard_addition = get_tool_call_size_guard_system_addition(tools)
    if size_guard_addition:
        full_system_prompt = full_system_prompt + size_guard_addition if full_system_prompt else size_guard_addition.strip()
```

- [ ] **Step 3: Add TOOL_CALL_SIZE_GUARD to imports in converters_core.py**

The function uses a local import (`from kiro.config import TOOL_CALL_SIZE_GUARD`) — no change needed at module level.

---

### Task 3: Write tests

**Files:**
- Modify: `tests/unit/test_converters_core.py`

- [ ] **Step 1: Write failing tests**

Add a new test class at the end of `tests/unit/test_converters_core.py`:

```python
class TestToolCallSizeGuard:
    """Tests for get_tool_call_size_guard_system_addition and its integration."""

    def test_returns_empty_when_disabled(self):
        """
        What it does: Returns empty string when TOOL_CALL_SIZE_GUARD=false.
        Purpose: Ensure users can opt out of the guard.
        """
        tools = [UnifiedTool(name="Write", description="Write a file", input_schema={})]
        with patch("kiro.config.TOOL_CALL_SIZE_GUARD", False):
            result = get_tool_call_size_guard_system_addition(tools)
        assert result == ""

    def test_returns_empty_when_no_tools(self):
        """
        What it does: Returns empty string when tools list is None or empty.
        Purpose: Guard is irrelevant without tools.
        """
        with patch("kiro.config.TOOL_CALL_SIZE_GUARD", True):
            assert get_tool_call_size_guard_system_addition(None) == ""
            assert get_tool_call_size_guard_system_addition([]) == ""

    def test_returns_instruction_when_tools_present(self):
        """
        What it does: Returns non-empty instruction when tools are present and guard is enabled.
        Purpose: Core behavior — instruction must be present.
        """
        tools = [UnifiedTool(name="Write", description="Write a file", input_schema={})]
        with patch("kiro.config.TOOL_CALL_SIZE_GUARD", True):
            result = get_tool_call_size_guard_system_addition(tools)
        assert len(result) > 0
        assert "7KB" in result
        assert "Write" in result or "write" in result
        assert "Edit" in result or "edit" in result

    def test_injected_into_payload_when_tools_present(self):
        """
        What it does: Verifies build_kiro_payload includes size guard in system prompt.
        Purpose: Integration — guard must reach the Kiro API payload.
        """
        messages = [UnifiedMessage(role="user", content="Write a large file")]
        tools = [UnifiedTool(name="Write", description="Write a file", input_schema={"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}})]
        with patch("kiro.config.TOOL_CALL_SIZE_GUARD", True), \
             patch("kiro.config.FAKE_REASONING_ENABLED", False), \
             patch("kiro.config.TRUNCATION_RECOVERY", False):
            result = build_kiro_payload(
                messages=messages,
                system_prompt="You are helpful.",
                model_id="claude-sonnet-4-5",
                tools=tools,
                conversation_id="test-conv",
                profile_arn="",
                thinking_config=ThinkingConfig(enabled=False),
            )
        # System prompt is in the first user message content (no history)
        current_content = result.payload["conversationState"]["currentMessage"]["userInputMessage"]["content"]
        assert "7KB" in current_content
        assert "Tool Call Size Constraint" in current_content

    def test_not_injected_when_no_tools(self):
        """
        What it does: Verifies size guard is absent from payload when no tools.
        Purpose: Avoid polluting system prompt for non-tool requests.
        """
        messages = [UnifiedMessage(role="user", content="Hello")]
        with patch("kiro.config.TOOL_CALL_SIZE_GUARD", True), \
             patch("kiro.config.FAKE_REASONING_ENABLED", False), \
             patch("kiro.config.TRUNCATION_RECOVERY", False):
            result = build_kiro_payload(
                messages=messages,
                system_prompt="",
                model_id="claude-sonnet-4-5",
                tools=None,
                conversation_id="test-conv",
                profile_arn="",
                thinking_config=ThinkingConfig(enabled=False),
            )
        current_content = result.payload["conversationState"]["currentMessage"]["userInputMessage"]["content"]
        assert "Tool Call Size Constraint" not in current_content
```

- [ ] **Step 2: Run tests to verify they fail**
```bash
cd /root/project/kiro-gateway && python -m pytest tests/unit/test_converters_core.py::TestToolCallSizeGuard -v 2>&1 | tail -20
```
Expected: 5 failures (function not defined)

- [ ] **Step 3: Run tests after implementation to verify they pass**
```bash
cd /root/project/kiro-gateway && python -m pytest tests/unit/test_converters_core.py::TestToolCallSizeGuard -v 2>&1 | tail -20
```
Expected: 5 passes

---

### Task 4: Update .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Add config entry**

Find the `TRUNCATION_RECOVERY` line in `.env.example` and add after it:

```
# Tool Call Size Guard (default: true)
# Injects system prompt to prevent large file writes from being truncated by Kiro API (~9KB limit)
# Disable only if you handle chunking at the client level (e.g., custom CLAUDE.md instructions)
# TOOL_CALL_SIZE_GUARD=true
```

---

### Task 5: Full test suite + commit

- [ ] **Step 1: Run full test suite**
```bash
cd /root/project/kiro-gateway && python -m pytest tests/unit/ -x -q 2>&1 | tail -20
```
Expected: All pass

- [ ] **Step 2: Commit**
```bash
cd /root/project/kiro-gateway && git add kiro/config.py kiro/converters_core.py .env.example tests/unit/test_converters_core.py docs/superpowers/
git commit -m "feat(gateway): add tool call size guard to prevent Kiro API truncation

Kiro API silently truncates tool call output streams exceeding ~9KB,
causing Write/write tool calls to arrive with empty arguments ({}).

Injects a system prompt addition (when tools are present) instructing
the model to split large file writes into chunks using Edit/edit.

Controlled by TOOL_CALL_SIZE_GUARD env var (default: true).
Follows existing pattern of get_thinking_system_prompt_addition()."
```
