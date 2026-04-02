# -*- coding: utf-8 -*-
"""
Utilities for handling response_format: json_object.

Strips markdown code block wrappers from responses when the caller
requested raw JSON output via response_format.
"""

import re

# Matches ```json\n...\n``` or ```\n...\n``` wrapping the entire response
_MD_JSON_BLOCK_RE = re.compile(
    r'^\s*```(?:json)?\s*\n(.*?)\n\s*```\s*$',
    re.DOTALL
)


def strip_markdown_json_wrapper(content: str) -> str:
    """
    Strip markdown code block wrapper from JSON content.
    
    If the content is wrapped in ```json ... ``` or ``` ... ```,
    extract the inner content. Only strips if the entire response
    is a single code block.
    
    Args:
        content: Response content that may be markdown-wrapped
    
    Returns:
        Unwrapped content, or original content if no wrapper found
    """
    if not content:
        return content
    
    m = _MD_JSON_BLOCK_RE.match(content)
    if m:
        return m.group(1).strip()
    
    return content
