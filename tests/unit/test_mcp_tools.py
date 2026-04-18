# -*- coding: utf-8 -*-

"""
Tests for MCP Tools Support (WebSearch).

Tests cover:
- ID generation
- MCP API calls
- Search summary generation
- Query extraction from messages
- Native web_search handler (Path A)
- SSE emulation (Anthropic and OpenAI formats)
"""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime

from kiro.mcp_tools import (
    generate_random_id,
    call_kiro_mcp_api,
    generate_search_summary,
    extract_query_from_messages,
    handle_native_web_search,
    generate_anthropic_web_search_sse,
    generate_openai_web_search_sse
)


# ==================================================================================================
# Tests for ID Generation
# ==================================================================================================

class TestIDGeneration:
    """Tests for random ID generation."""
    
    def test_generate_random_id_length(self):
        """
        What it does: Verifies ID generation with exact length.
        Purpose: Ensure generate_random_id returns correct length.
        """
        print("Setup: Generating IDs of different lengths...")
        
        print("Action: Generate ID of length 22...")
        id_22 = generate_random_id(22)
        print(f"Comparing length: Expected 22, Got {len(id_22)}")
        assert len(id_22) == 22
        
        print("Action: Generate ID of length 8...")
        id_8 = generate_random_id(8)
        print(f"Comparing length: Expected 8, Got {len(id_8)}")
        assert len(id_8) == 8
        
        print("Action: Generate ID of length 100...")
        id_100 = generate_random_id(100)
        print(f"Comparing length: Expected 100, Got {len(id_100)}")
        assert len(id_100) == 100
    
    def test_generate_random_id_alphanumeric(self):
        """
        What it does: Verifies ID contains only alphanumeric characters.
        Purpose: Ensure no special characters in generated IDs.
        """
        print("Setup: Generating large ID to test character set...")
        
        print("Action: Generate ID of length 1000...")
        random_id = generate_random_id(1000)
        
        print(f"Checking if alphanumeric: {random_id[:50]}...")
        assert random_id.isalnum()
    
    def test_generate_random_id_uniqueness(self):
        """
        What it does: Verifies IDs are unique (probabilistically).
        Purpose: Ensure randomness works correctly.
        """
        print("Setup: Generating multiple IDs...")
        
        print("Action: Generate 100 IDs of length 22...")
        ids = [generate_random_id(22) for _ in range(100)]
        
        print(f"Comparing uniqueness: Generated {len(ids)} IDs, unique: {len(set(ids))}")
        assert len(set(ids)) == len(ids)  # All should be unique


# ==================================================================================================
# Tests for MCP API Call
# ==================================================================================================

class TestCallKiroMCPAPI:
    """Tests for MCP API calls."""
    
    @pytest.mark.asyncio
    async def test_mcp_api_success(self, mock_auth_manager):
        """
        What it does: Verifies successful MCP API call and result parsing.
        Purpose: Ensure MCP API integration works correctly.
        """
        print("Setup: Mocking successful MCP API response...")
        query = "Python tutorials"
        
        # Mock MCP response (CRITICAL: result.content[0].text is JSON STRING)
        mock_response_data = {
            "id": "web_search_tooluse_abc123_1234567890_xyz",
            "jsonrpc": "2.0",
            "result": {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "results": [
                            {
                                "title": "Python Tutorial",
                                "url": "https://python.org",
                                "snippet": "Learn Python programming",
                                "publishedDate": 1700000000000
                            }
                        ],
                        "totalResults": 1,
                        "query": "Python tutorials"
                    })
                }],
                "isError": False
            }
        }
        
        # Mock httpx.AsyncClient - CRITICAL: json() must be async
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = mock_post
        
        print("Action: Calling call_kiro_mcp_api...")
        with patch("kiro.mcp_tools.httpx.AsyncClient", return_value=mock_client):
            tool_use_id, results = await call_kiro_mcp_api(query, mock_auth_manager)
        
        print(f"Comparing tool_use_id: Got '{tool_use_id}'")
        assert tool_use_id is not None
        assert tool_use_id.startswith("srvtoolu_")
        
        print(f"Comparing results: Got {results}")
        assert results is not None
        assert results["totalResults"] == 1
        assert results["results"][0]["title"] == "Python Tutorial"
        assert results["results"][0]["url"] == "https://python.org"
    
    @pytest.mark.asyncio
    async def test_mcp_api_error_response(self, mock_auth_manager):
        """
        What it does: Verifies handling of MCP API error response.
        Purpose: Ensure errors are handled gracefully.
        """
        print("Setup: Mocking MCP API error response...")
        query = "test"
        
        # Mock error response
        mock_response_data = {
            "id": "web_search_tooluse_abc123_1234567890_xyz",
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid request"}
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value=mock_response_data)
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = mock_post
        
        print("Action: Calling call_kiro_mcp_api...")
        with patch("kiro.mcp_tools.httpx.AsyncClient", return_value=mock_client):
            tool_use_id, results = await call_kiro_mcp_api(query, mock_auth_manager)
        
        print(f"Comparing result: Expected (None, None), Got ({tool_use_id}, {results})")
        assert tool_use_id is None
        assert results is None
    
    @pytest.mark.asyncio
    async def test_mcp_api_http_error(self, mock_auth_manager):
        """
        What it does: Verifies handling of HTTP errors from MCP API.
        Purpose: Ensure non-200 status codes are handled.
        """
        print("Setup: Mocking HTTP 500 error...")
        query = "test"
        
        mock_response = Mock()
        mock_response.status_code = 500
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = mock_post
        
        print("Action: Calling call_kiro_mcp_api...")
        with patch("kiro.mcp_tools.httpx.AsyncClient", return_value=mock_client):
            tool_use_id, results = await call_kiro_mcp_api(query, mock_auth_manager)
        
        print(f"Comparing result: Expected (None, None), Got ({tool_use_id}, {results})")
        assert tool_use_id is None
        assert results is None
    
    @pytest.mark.asyncio
    async def test_mcp_api_timeout(self, mock_auth_manager):
        """
        What it does: Verifies handling of MCP API timeout.
        Purpose: Ensure timeouts are handled gracefully.
        """
        print("Setup: Mocking timeout exception...")
        query = "test"
        
        import httpx
        
        mock_post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = mock_post
        
        print("Action: Calling call_kiro_mcp_api...")
        with patch("kiro.mcp_tools.httpx.AsyncClient", return_value=mock_client):
            tool_use_id, results = await call_kiro_mcp_api(query, mock_auth_manager)
        
        print(f"Comparing result: Expected (None, None), Got ({tool_use_id}, {results})")
        assert tool_use_id is None
        assert results is None
    
    @pytest.mark.asyncio
    async def test_mcp_api_json_decode_error(self, mock_auth_manager):
        """
        What it does: Verifies handling of malformed JSON in MCP response.
        Purpose: Ensure JSON parsing errors are handled.
        """
        print("Setup: Mocking malformed JSON response...")
        query = "test"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json = Mock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
        
        mock_post = AsyncMock(return_value=mock_response)
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value.post = mock_post
        
        print("Action: Calling call_kiro_mcp_api...")
        with patch("kiro.mcp_tools.httpx.AsyncClient", return_value=mock_client):
            tool_use_id, results = await call_kiro_mcp_api(query, mock_auth_manager)
        
        print(f"Comparing result: Expected (None, None), Got ({tool_use_id}, {results})")
        assert tool_use_id is None
        assert results is None


# ==================================================================================================
# Tests for Search Summary Generation
# ==================================================================================================

class TestGenerateSearchSummary:
    """Tests for search summary formatting."""
    
    def test_generate_summary_with_results(self):
        """
        What it does: Verifies summary formatting with results.
        Purpose: Ensure XML tags and proper formatting.
        """
        print("Setup: Creating mock search results...")
        query = "Python"
        results = {
            "results": [
                {
                    "title": "Python.org",
                    "url": "https://python.org",
                    "snippet": "Official Python website with tutorials",
                    "publishedDate": 1700000000000
                },
                {
                    "title": "Python Tutorial",
                    "url": "https://docs.python.org",
                    "snippet": "Complete Python documentation",
                    "publishedDate": None  # No date
                }
            ],
            "totalResults": 2
        }
        
        print("Action: Generating summary...")
        summary = generate_search_summary(query, results)
        
        print(f"Checking XML tags...")
        assert "<web_search>" in summary
        assert "</web_search>" in summary
        
        print(f"Checking query in summary...")
        assert "Python" in summary
        
        print(f"Checking first result...")
        assert "Python.org" in summary
        assert "https://python.org" in summary
        assert "Official Python website with tutorials" in summary
        
        print(f"Checking second result...")
        assert "Python Tutorial" in summary
        assert "https://docs.python.org" in summary
        assert "Complete Python documentation" in summary
    
    def test_generate_summary_no_results(self):
        """
        What it does: Verifies summary with empty results list.
        Purpose: Ensure empty results are handled gracefully.
        """
        print("Setup: Creating empty results...")
        query = "nonexistent"
        results = {"results": [], "totalResults": 0}
        
        print("Action: Generating summary...")
        summary = generate_search_summary(query, results)
        
        print(f"Checking XML tags...")
        assert "<web_search>" in summary
        assert "</web_search>" in summary
        
        print(f"Checking query in summary...")
        assert "nonexistent" in summary
        
        print(f"Summary content: {repr(summary)}")
        # Empty results list produces empty content between tags (no "No results found")
        assert "Search results for" in summary
    
    def test_generate_summary_malformed_results(self):
        """
        What it does: Verifies handling of malformed results.
        Purpose: Ensure graceful handling of invalid data.
        """
        print("Setup: Creating malformed results...")
        query = "test"
        results = {"invalid": "structure"}
        
        print("Action: Generating summary...")
        summary = generate_search_summary(query, results)
        
        print(f"Checking for 'No results found'...")
        assert "No results found" in summary
    
    def test_generate_summary_date_formatting(self):
        """
        What it does: Verifies date formatting from milliseconds timestamp.
        Purpose: Ensure publishedDate is converted correctly.
        """
        print("Setup: Creating result with timestamp...")
        query = "test"
        # 1700000000000 ms = 2023-11-14 22:13:20 UTC
        results = {
            "results": [{
                "title": "Test",
                "url": "https://test.com",
                "snippet": "Test snippet",
                "publishedDate": 1700000000000
            }],
            "totalResults": 1
        }
        
        print("Action: Generating summary...")
        summary = generate_search_summary(query, results)
        
        print(f"Checking date format...")
        # Should contain formatted date like "14 Nov 2023"
        assert "Nov 2023" in summary or "Ноя 2023" in summary  # Depends on locale
    
    def test_generate_summary_full_snippet_no_truncation(self):
        """
        What it does: Verifies snippets are NOT truncated.
        Purpose: Ensure model gets full information.
        """
        print("Setup: Creating result with long snippet...")
        query = "test"
        long_snippet = "A" * 1000  # 1000 characters
        results = {
            "results": [{
                "title": "Test",
                "url": "https://test.com",
                "snippet": long_snippet,
                "publishedDate": None
            }],
            "totalResults": 1
        }
        
        print("Action: Generating summary...")
        summary = generate_search_summary(query, results)
        
        print(f"Checking snippet is NOT truncated...")
        assert long_snippet in summary
        assert len(long_snippet) == 1000  # Full length preserved


# ==================================================================================================
# Tests for Query Extraction
# ==================================================================================================

class TestExtractQueryFromMessages:
    """Tests for query extraction from messages."""
    
    def test_extract_query_anthropic_string_content(self):
        """
        What it does: Extracts query from Anthropic string content.
        Purpose: Ensure simple string messages work.
        """
        print("Setup: Creating Anthropic message with string content...")
        from kiro.models_anthropic import AnthropicMessage
        messages = [AnthropicMessage(role="user", content="Search for Python tutorials")]
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected 'Search for Python tutorials', Got '{query}'")
        assert query == "Search for Python tutorials"
    
    def test_extract_query_anthropic_list_content(self):
        """
        What it does: Extracts query from Anthropic list content.
        Purpose: Ensure content blocks work.
        """
        print("Setup: Creating Anthropic message with list content...")
        from kiro.models_anthropic import AnthropicMessage, TextContentBlock
        messages = [AnthropicMessage(
            role="user",
            content=[TextContentBlock(type="text", text="Python tutorials")]
        )]
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected 'Python tutorials', Got '{query}'")
        assert query == "Python tutorials"
    
    def test_extract_query_with_prefix(self):
        """
        What it does: Removes 'Perform a web search for the query:' prefix.
        Purpose: Ensure prefix is stripped correctly.
        """
        print("Setup: Creating message with prefix...")
        from kiro.models_anthropic import AnthropicMessage
        messages = [AnthropicMessage(
            role="user",
            content="Perform a web search for the query: Python"
        )]
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected 'Python', Got '{query}'")
        assert query == "Python"
    
    def test_extract_query_empty_messages(self):
        """
        What it does: Handles empty messages list.
        Purpose: Ensure None is returned for empty input.
        """
        print("Setup: Creating empty messages list...")
        messages = []
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected None, Got {query}")
        assert query is None
    
    def test_extract_query_no_text_content(self):
        """
        What it does: Handles messages without text content.
        Purpose: Ensure None is returned for non-text messages.
        """
        print("Setup: Creating message with image content...")
        from kiro.models_anthropic import AnthropicMessage, ImageContentBlock, Base64ImageSource
        messages = [AnthropicMessage(
            role="user",
            content=[ImageContentBlock(
                type="image",
                source=Base64ImageSource(
                    type="base64",
                    media_type="image/png",
                    data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
                )
            )]
        )]
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected None or empty, Got '{query}'")
        assert query is None or query == ""
    
    def test_extract_query_multiple_text_blocks(self):
        """
        What it does: Concatenates multiple text blocks.
        Purpose: Ensure all text is extracted.
        """
        print("Setup: Creating message with multiple text blocks...")
        from kiro.models_anthropic import AnthropicMessage, TextContentBlock
        messages = [AnthropicMessage(
            role="user",
            content=[
                TextContentBlock(type="text", text="Search for "),
                TextContentBlock(type="text", text="Python tutorials")
            ]
        )]
        
        print("Action: Extracting query...")
        query = extract_query_from_messages(messages, "anthropic")
        
        print(f"Comparing query: Expected 'Search for Python tutorials', Got '{query}'")
        assert query == "Search for Python tutorials"


# ==================================================================================================
# Tests for SSE Emulation
# ==================================================================================================

class TestAnthropicSSEEmulation:
    """Tests for Anthropic SSE stream generation."""
    
    @pytest.mark.asyncio
    async def test_generate_anthropic_sse_structure(self):
        """
        What it does: Verifies Anthropic SSE event structure.
        Purpose: Ensure all 11 events are generated correctly.
        """
        print("Setup: Preparing test data...")
        model = "claude-sonnet-4"
        query = "Python"
        tool_use_id = "srvtoolu_test123"
        results = {
            "results": [{"title": "Test", "url": "https://test.com", "snippet": "Test"}],
            "totalResults": 1
        }
        input_tokens = 100
        
        print("Action: Generating SSE stream...")
        events = []
        async for event in generate_anthropic_web_search_sse(model, query, tool_use_id, results, input_tokens):
            events.append(event)
        
        print(f"Comparing event count: Got {len(events)} events")
        assert len(events) >= 11  # At least 11 events (may have more text_delta chunks)
        
        print("Checking event types...")
        event_types = []
        for event in events:
            if "event:" in event:
                event_type = event.split("event:")[1].split("\n")[0].strip()
                event_types.append(event_type)
        
        print(f"Event types: {event_types}")
        assert "message_start" in event_types
        assert "content_block_start" in event_types
        assert "content_block_delta" in event_types
        assert "content_block_stop" in event_types
        assert "message_delta" in event_types
        assert "message_stop" in event_types


class TestOpenAISSEEmulation:
    """Tests for OpenAI SSE stream generation."""
    
    @pytest.mark.asyncio
    async def test_generate_openai_sse_structure(self):
        """
        What it does: Verifies OpenAI SSE event structure.
        Purpose: Ensure OpenAI format is correct.
        """
        print("Setup: Preparing test data...")
        model = "claude-sonnet-4"
        query = "Python"
        tool_use_id = "srvtoolu_test123"
        results = {
            "results": [{"title": "Test", "url": "https://test.com", "snippet": "Test"}],
            "totalResults": 1
        }
        input_tokens = 100
        
        print("Action: Generating SSE stream...")
        chunks = []
        async for chunk in generate_openai_web_search_sse(model, query, tool_use_id, results, input_tokens):
            chunks.append(chunk)
        
        print(f"Comparing chunk count: Got {len(chunks)} chunks")
        assert len(chunks) >= 3  # At least: role, content chunks, finish + [DONE]
        
        print("Checking for [DONE] marker...")
        assert any("[DONE]" in chunk for chunk in chunks)
        
        print("Checking for role delta (flexible matching)...")
        assert any('"role"' in chunk and '"assistant"' in chunk for chunk in chunks)
        
        print("Checking for finish_reason (flexible matching)...")
        assert any('"finish_reason"' in chunk and '"stop"' in chunk for chunk in chunks)
        
        print("Checking for data: prefix...")
        assert any(chunk.startswith("data:") for chunk in chunks)
        
        print("Checking for usage information...")
        assert any('"usage"' in chunk for chunk in chunks)
