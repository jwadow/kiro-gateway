"""
Runtime tool-name aliasing for Kiro's 64-character tool name limit.

This module lives outside the upstream kiro/ tree. main.py installs it at
startup so kiro-gateway can keep upstream files sync-friendly while still
handling long MCP tool names (e.g. names emitted by aggregating MCP gateways
that exceed Kiro's 64-character limit).

The install hook patches a small surface in kiro.{converters_core,parsers,
streaming_*} to:

  - Replace strict >64-char validation with silent registration.
  - Rewrite tool names client→Kiro to a stable hashed alias on the way in.
  - Rewrite tool names Kiro→client back to the original on the way out
    (both stream events and bracket-formatted tool calls).

All replacements are idempotent and reversible via uninstall_tool_name_aliasing,
which is intended for unit tests.
"""

import hashlib
import re
from typing import Any, AsyncGenerator, Dict, Iterable, Optional

from loguru import logger


MAX_KIRO_TOOL_NAME_LENGTH = 64
_KIRO_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SAFE_SUFFIX_RE = re.compile(r"[^A-Za-z0-9_-]+")

_alias_to_original: Dict[str, str] = {}
_original_to_alias: Dict[str, str] = {}
_reserved_kiro_names = set()
_installed = False
_originals: Dict[str, Any] = {}


def needs_alias(name: str) -> bool:
    return not bool(_KIRO_TOOL_NAME_RE.match(name or ""))


def _build_alias(name: str, digest_len: int) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:digest_len]
    suffix_source = name.rsplit("__", 1)[-1] or name
    suffix = _SAFE_SUFFIX_RE.sub("_", suffix_source).strip("_-") or "tool"
    prefix = f"t_{digest}_"
    max_suffix_len = MAX_KIRO_TOOL_NAME_LENGTH - len(prefix)
    return prefix + suffix[-max_suffix_len:]


def alias_for_tool_name(name: str) -> str:
    """Return the Kiro-facing name for a client-facing tool name."""
    if not needs_alias(name):
        return name

    if name in _original_to_alias:
        return _original_to_alias[name]

    alias = _build_alias(name, 12)
    digest_len = 16
    while (
        alias in _reserved_kiro_names
        or (alias in _alias_to_original and _alias_to_original[alias] != name)
    ):
        alias = _build_alias(name, digest_len)
        digest_len += 4

    _original_to_alias[name] = alias
    _alias_to_original[alias] = name
    logger.debug(f"Aliased long Kiro tool name: '{name}' -> '{alias}'")
    return alias


def original_for_tool_name(name: str) -> str:
    """Return the client-facing name for a Kiro-facing alias."""
    return _alias_to_original.get(name, name)


def _register_tool_names(tools: Optional[Iterable[Any]]) -> None:
    if not tools:
        return
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str) and not needs_alias(name):
            _reserved_kiro_names.add(name)
    for tool in tools:
        name = getattr(tool, "name", None)
        if isinstance(name, str):
            alias_for_tool_name(name)


def _alias_tool_use(tool_use: Dict[str, Any]) -> Dict[str, Any]:
    name = tool_use.get("name")
    if isinstance(name, str):
        tool_use["name"] = alias_for_tool_name(name)
    return tool_use


def _restore_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    func = tool_call.get("function")
    if isinstance(func, dict):
        name = func.get("name")
        if isinstance(name, str):
            func["name"] = original_for_tool_name(name)
    name = tool_call.get("name")
    if isinstance(name, str):
        tool_call["name"] = original_for_tool_name(name)
    return tool_call


def _restore_event_tool_name(event: Any) -> Any:
    if getattr(event, "type", None) == "tool_use" and getattr(event, "tool_use", None):
        _restore_tool_call(event.tool_use)
    return event


def install_tool_name_aliasing() -> None:
    """Install runtime patches without modifying upstream kiro/ modules."""
    global _installed
    if _installed:
        return

    import kiro.converters_core as converters_core
    import kiro.parsers as parsers
    import kiro.streaming_core as streaming_core
    import kiro.streaming_openai as streaming_openai
    import kiro.streaming_anthropic as streaming_anthropic

    _originals.update(
        validate_tool_names=converters_core.validate_tool_names,
        convert_tools_to_kiro_format=converters_core.convert_tools_to_kiro_format,
        extract_tool_uses_from_message=converters_core.extract_tool_uses_from_message,
        parse_bracket_tool_calls=parsers.parse_bracket_tool_calls,
        parse_kiro_stream=streaming_core.parse_kiro_stream,
    )

    def validate_tool_names_with_aliases(tools):
        _register_tool_names(tools)

    def convert_tools_to_kiro_format_with_aliases(tools):
        _register_tool_names(tools)
        if not tools:
            return _originals["convert_tools_to_kiro_format"](tools)

        aliased_tools = []
        for tool in tools:
            aliased_tools.append(
                converters_core.UnifiedTool(
                    name=alias_for_tool_name(tool.name),
                    description=tool.description,
                    input_schema=tool.input_schema,
                )
            )
        return _originals["convert_tools_to_kiro_format"](aliased_tools)

    def extract_tool_uses_from_message_with_aliases(content, tool_calls=None):
        tool_uses = _originals["extract_tool_uses_from_message"](content, tool_calls)
        return [_alias_tool_use(tool_use) for tool_use in tool_uses]

    def parse_bracket_tool_calls_with_restore(response_text):
        tool_calls = _originals["parse_bracket_tool_calls"](response_text)
        return [_restore_tool_call(tool_call) for tool_call in tool_calls]

    async def parse_kiro_stream_with_restore(*args, **kwargs) -> AsyncGenerator[Any, None]:
        async for event in _originals["parse_kiro_stream"](*args, **kwargs):
            yield _restore_event_tool_name(event)

    converters_core.validate_tool_names = validate_tool_names_with_aliases
    converters_core.convert_tools_to_kiro_format = convert_tools_to_kiro_format_with_aliases
    converters_core.extract_tool_uses_from_message = extract_tool_uses_from_message_with_aliases

    parsers.parse_bracket_tool_calls = parse_bracket_tool_calls_with_restore
    streaming_core.parse_bracket_tool_calls = parse_bracket_tool_calls_with_restore
    streaming_openai.parse_bracket_tool_calls = parse_bracket_tool_calls_with_restore
    streaming_anthropic.parse_bracket_tool_calls = parse_bracket_tool_calls_with_restore

    streaming_core.parse_kiro_stream = parse_kiro_stream_with_restore
    streaming_openai.parse_kiro_stream = parse_kiro_stream_with_restore
    streaming_anthropic.parse_kiro_stream = parse_kiro_stream_with_restore

    _installed = True
    logger.info("Installed Kiro tool-name aliasing extension")


def uninstall_tool_name_aliasing() -> None:
    """Restore patched functions. Intended for unit tests."""
    global _installed
    if _originals:
        import kiro.converters_core as converters_core
        import kiro.parsers as parsers
        import kiro.streaming_core as streaming_core
        import kiro.streaming_openai as streaming_openai
        import kiro.streaming_anthropic as streaming_anthropic

        converters_core.validate_tool_names = _originals["validate_tool_names"]
        converters_core.convert_tools_to_kiro_format = _originals["convert_tools_to_kiro_format"]
        converters_core.extract_tool_uses_from_message = _originals["extract_tool_uses_from_message"]

        parsers.parse_bracket_tool_calls = _originals["parse_bracket_tool_calls"]
        streaming_core.parse_bracket_tool_calls = _originals["parse_bracket_tool_calls"]
        streaming_openai.parse_bracket_tool_calls = _originals["parse_bracket_tool_calls"]
        streaming_anthropic.parse_bracket_tool_calls = _originals["parse_bracket_tool_calls"]

        streaming_core.parse_kiro_stream = _originals["parse_kiro_stream"]
        streaming_openai.parse_kiro_stream = _originals["parse_kiro_stream"]
        streaming_anthropic.parse_kiro_stream = _originals["parse_kiro_stream"]

    _originals.clear()
    _alias_to_original.clear()
    _original_to_alias.clear()
    _reserved_kiro_names.clear()
    _installed = False
