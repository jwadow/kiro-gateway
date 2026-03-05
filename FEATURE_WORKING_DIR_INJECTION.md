# Feature: Working Directory Context Injection

## Problem

Claude Code (and other AI coding assistants) sometimes lose track of their current working directory, leading to errors like:

```bash
cd: PublicVersion/DownAria-API: No such file or directory
```

This happens when:
1. The model is already in the target directory
2. But doesn't realize it from the conversation context
3. And tries to `cd` into a relative path that doesn't exist from the current location

## Solution

The gateway now automatically extracts working directory information from tool result error messages and injects it into the system prompt, providing the model with explicit context about its current location.

## How It Works

### 1. Detection

The gateway scans tool result error messages for working directory information:

```
"File does not exist. Note: your current working directory is D:\MyGitRepository\TownProject\DownAria-Project\PublicVersion\DownAria-API."
```

Pattern matched (case-insensitive):
```regex
your current working directory is ([^\.\n]+)
```

Supports both:
- Windows paths: `D:\path\to\dir`
- Unix paths: `/path/to/dir`

### 2. Extraction

The gateway extracts the most recent working directory from the conversation history:

```python
def extract_working_directory_from_messages(
    messages: List[AnthropicMessage],
) -> Optional[str]:
    """
    Extracts working directory from tool result error messages.
    
    Searches in reverse order (most recent first) for working directory info.
    """
```

### 3. Injection

If a working directory is found, it's injected into the system prompt:

```markdown
## Current Working Directory

You are currently in: `D:\MyGitRepository\TownProject\DownAria-Project\PublicVersion\DownAria-API`

When running bash commands:
- Use relative paths from this directory
- Or use absolute paths
- Avoid `cd` to subdirectories that don't exist relative to this location
```

## Configuration

Enable/disable via environment variable:

```bash
# .env
INJECT_WORKING_DIR=true  # Default: enabled
```

Or disable:

```bash
INJECT_WORKING_DIR=false
```

## Benefits

✅ **Prevents path confusion** - Model knows exactly where it is
✅ **Reduces failed commands** - Fewer "No such file or directory" errors
✅ **Better context awareness** - Model can make smarter path decisions
✅ **Transparent** - Works automatically without user intervention
✅ **Configurable** - Can be disabled if not needed

## Example

**Before (without injection):**

```
User: Check the logs in PublicVersion/DownAria-API
Assistant: [runs] cd PublicVersion/DownAria-API && cat logs/error.log
Error: cd: PublicVersion/DownAria-API: No such file or directory
```

**After (with injection):**

```
System Prompt: You are currently in: D:\...\DownAria-Project\PublicVersion\DownAria-API

User: Check the logs
Assistant: [runs] cat logs/error.log  # Uses relative path correctly
Success: [log contents]
```

## Implementation Details

### Files Modified

1. **kiro/converters_anthropic.py**
   - Added `extract_working_directory_from_messages()` function
   - Modified `anthropic_to_kiro()` to inject working directory

2. **kiro/config.py**
   - Added `INJECT_WORKING_DIR` configuration flag

3. **tests/unit/test_converters_anthropic.py**
   - Added 8 comprehensive tests for extraction and injection

### Test Coverage

- ✅ Extract from Windows paths
- ✅ Extract from Unix paths
- ✅ Extract from most recent message
- ✅ Handle string content
- ✅ Handle list content (tool_result blocks)
- ✅ Case-insensitive matching
- ✅ Injection when enabled
- ✅ No injection when disabled

All 80 tests passed ✅

## Performance Impact

- **Minimal** - Only scans messages when feature is enabled
- **Efficient** - Searches in reverse order (most recent first)
- **Cached** - Working directory extracted once per request

## Compatibility

- ✅ Works with Anthropic Messages API
- ✅ Compatible with Claude Code
- ✅ Compatible with other AI coding assistants
- ✅ No breaking changes to existing functionality

## Future Enhancements

Potential improvements:
1. Support for OpenAI format (currently Anthropic only)
2. Extract from `pwd` command results
3. Track working directory changes across conversation
4. Inject into tool descriptions instead of system prompt

## Usage

No action required - feature is enabled by default!

To disable:
```bash
# .env
INJECT_WORKING_DIR=false
```

## Logging

When working directory is injected, you'll see:

```
INFO - Injected working directory into system prompt: /path/to/dir
```

## Troubleshooting

**Q: Working directory not being detected?**

A: Make sure error messages include the pattern:
```
Note: your current working directory is /path/to/dir
```

**Q: Want to see what's being injected?**

A: Enable debug logging:
```bash
DEBUG_MODE=all
```

Then check `debug_logs/kiro_request_body.json` for the system prompt.

**Q: Feature not working?**

A: Check configuration:
```bash
# Should be true or not set (defaults to true)
INJECT_WORKING_DIR=true
```

## Related Issues

Fixes common errors:
- `cd: No such file or directory`
- Path confusion in multi-directory projects
- Relative path resolution issues

## Credits

Implemented as part of Kiro Gateway v2.4
Feature request from real-world usage patterns
