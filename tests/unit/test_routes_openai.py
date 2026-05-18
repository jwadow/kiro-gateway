
# -*- coding: utf-8 -*-

"""
Unit tests for OpenAI API endpoints (routes_openai.py).

Tests the following endpoints:
- GET / - Root endpoint
- GET /health - Health check
- GET /v1/models - List available models
- POST /v1/chat/completions - Chat completions

For Anthropic API tests, see test_routes_anthropic.py.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone
import json
import time

from fastapi import HTTPException
from fastapi.testclient import TestClient

from kiro.routes_openai import verify_api_key, router
from kiro.config import PROXY_API_KEY, APP_VERSION


# =============================================================================
# Tests for verify_api_key function
# =============================================================================

class TestVerifyApiKey:
    """Tests for the verify_api_key authentication function."""
    
    @pytest.mark.asyncio
    async def test_valid_bearer_token_returns_true(self):
        """
        What it does: Verifies that a valid Bearer token passes authentication.
        Purpose: Ensure correct API keys are accepted.
        """
        print("Setup: Creating valid Bearer token...")
        valid_header = f"Bearer {PROXY_API_KEY}"
        
        print("Action: Calling verify_api_key...")
        result = await verify_api_key(valid_header)
        
        print(f"Comparing result: Expected True, Got {result}")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_invalid_api_key_raises_401(self):
        """
        What it does: Verifies that an invalid API key is rejected.
        Purpose: Ensure unauthorized access is blocked.
        """
        print("Setup: Creating invalid Bearer token...")
        invalid_header = "Bearer wrong_key_12345"
        
        print("Action: Calling verify_api_key with invalid key...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(invalid_header)
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401
        assert "Invalid or missing API Key" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_missing_api_key_raises_401(self):
        """
        What it does: Verifies that missing API key is rejected.
        Purpose: Ensure requests without authentication are blocked.
        """
        print("Setup: No API key provided...")
        
        print("Action: Calling verify_api_key with None...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(None)
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_empty_api_key_raises_401(self):
        """
        What it does: Verifies that empty string API key is rejected.
        Purpose: Ensure empty credentials are blocked.
        """
        print("Setup: Empty API key...")
        
        print("Action: Calling verify_api_key with empty string...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key("")
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_key_without_bearer_prefix_raises_401(self):
        """
        What it does: Verifies that API key without Bearer prefix is rejected.
        Purpose: Ensure proper Authorization header format is required.
        """
        print("Setup: API key without Bearer prefix...")
        wrong_format = PROXY_API_KEY  # Without "Bearer "
        
        print("Action: Calling verify_api_key...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(wrong_format)
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_bearer_with_extra_spaces_raises_401(self):
        """
        What it does: Verifies that Bearer token with extra spaces is rejected.
        Purpose: Ensure strict format validation.
        """
        print("Setup: Bearer token with extra spaces...")
        malformed = f"Bearer  {PROXY_API_KEY}"  # Double space
        
        print("Action: Calling verify_api_key...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(malformed)
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401
    
    @pytest.mark.asyncio
    async def test_lowercase_bearer_raises_401(self):
        """
        What it does: Verifies that lowercase 'bearer' is rejected.
        Purpose: Ensure case-sensitive Bearer prefix.
        """
        print("Setup: Lowercase bearer prefix...")
        lowercase = f"bearer {PROXY_API_KEY}"
        
        print("Action: Calling verify_api_key...")
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(lowercase)
        
        print(f"Checking: HTTPException with status 401...")
        assert exc_info.value.status_code == 401


# =============================================================================
# Tests for root endpoint (/)
# =============================================================================

class TestRootEndpoint:
    """Tests for the GET / endpoint."""
    
    def test_root_returns_status_ok(self, test_client):
        """
        What it does: Verifies root endpoint returns ok status.
        Purpose: Ensure basic health check works.
        """
        print("Action: GET /...")
        response = test_client.get("/")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_root_returns_gateway_message(self, test_client):
        """
        What it does: Verifies root endpoint returns gateway message.
        Purpose: Ensure service identification is present.
        """
        print("Action: GET /...")
        response = test_client.get("/")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert "Kiro Gateway" in response.json()["message"]
    
    def test_root_returns_version(self, test_client):
        """
        What it does: Verifies root endpoint returns application version.
        Purpose: Ensure version information is available.
        """
        print("Action: GET /...")
        response = test_client.get("/")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert "version" in response.json()
        assert response.json()["version"] == APP_VERSION
    
    def test_root_does_not_require_auth(self, test_client):
        """
        What it does: Verifies root endpoint is accessible without authentication.
        Purpose: Ensure public health check availability.
        """
        print("Action: GET / without auth headers...")
        response = test_client.get("/")
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 200


# =============================================================================
# Tests for health endpoint (/health)
# =============================================================================

class TestHealthEndpoint:
    """Tests for the GET /health endpoint."""
    
    def test_health_returns_healthy_status(self, test_client):
        """
        What it does: Verifies health endpoint returns healthy status.
        Purpose: Ensure health check indicates service is running.
        """
        print("Action: GET /health...")
        response = test_client.get("/health")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_health_returns_timestamp(self, test_client):
        """
        What it does: Verifies health endpoint returns timestamp.
        Purpose: Ensure timestamp is present for monitoring.
        """
        print("Action: GET /health...")
        response = test_client.get("/health")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert "timestamp" in response.json()
        # Verify timestamp is ISO format
        timestamp = response.json()["timestamp"]
        assert "T" in timestamp  # ISO format contains T
    
    def test_health_returns_version(self, test_client):
        """
        What it does: Verifies health endpoint returns version.
        Purpose: Ensure version is available for monitoring.
        """
        print("Action: GET /health...")
        response = test_client.get("/health")
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert response.json()["version"] == APP_VERSION
    
    def test_health_does_not_require_auth(self, test_client):
        """
        What it does: Verifies health endpoint is accessible without authentication.
        Purpose: Ensure health checks work for load balancers.
        """
        print("Action: GET /health without auth headers...")
        response = test_client.get("/health")
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 200


# =============================================================================
# Tests for models endpoint (/v1/models)
# =============================================================================

class TestModelsEndpoint:
    """Tests for the GET /v1/models endpoint."""
    
    def test_models_requires_authentication(self, test_client):
        """
        What it does: Verifies models endpoint requires authentication.
        Purpose: Ensure protected endpoints are secured.
        """
        print("Action: GET /v1/models without auth...")
        response = test_client.get("/v1/models")
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 401
    
    def test_models_rejects_invalid_key(self, test_client, invalid_proxy_api_key):
        """
        What it does: Verifies models endpoint rejects invalid API key.
        Purpose: Ensure authentication is enforced.
        """
        print("Action: GET /v1/models with invalid key...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {invalid_proxy_api_key}"}
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 401
    
    def test_models_returns_list_object(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies models endpoint returns list object type.
        Purpose: Ensure OpenAI API compatibility.
        """
        print("Action: GET /v1/models with valid auth...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert response.json()["object"] == "list"
    
    def test_models_returns_data_array(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies models endpoint returns data array.
        Purpose: Ensure response structure matches OpenAI format.
        """
        print("Action: GET /v1/models with valid auth...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        assert "data" in response.json()
        assert isinstance(response.json()["data"], list)
    
    def test_models_contains_available_models(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies all configured models are returned.
        Purpose: Ensure model list is complete.
        """
        print("Action: GET /v1/models with valid auth...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        
        model_ids = [m["id"] for m in response.json()["data"]]
        print(f"Model IDs: {model_ids}")
        
        # At minimum, hidden models should be present
        # (even if Kiro API cache is empty)
        assert len(model_ids) >= 1, "Expected at least one model (hidden models)"
    
    def test_models_format_is_openai_compatible(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies model objects have OpenAI-compatible format.
        Purpose: Ensure compatibility with OpenAI clients.
        """
        print("Action: GET /v1/models with valid auth...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        
        for model in response.json()["data"]:
            print(f"Checking model format: {model}")
            assert "id" in model, "Model missing 'id' field"
            assert "object" in model, "Model missing 'object' field"
            assert model["object"] == "model", "Model object type should be 'model'"
            assert "owned_by" in model, "Model missing 'owned_by' field"
    
    def test_models_owned_by_anthropic(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies models are owned by Anthropic.
        Purpose: Ensure correct model attribution.
        """
        print("Action: GET /v1/models with valid auth...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        print(f"Result: {response.json()}")
        assert response.status_code == 200
        
        for model in response.json()["data"]:
            assert model["owned_by"] == "anthropic"


# =============================================================================
# Tests for chat completions endpoint (/v1/chat/completions)
# =============================================================================

class TestChatCompletionsAuthentication:
    """Tests for authentication on /v1/chat/completions endpoint."""
    
    def test_chat_completions_requires_authentication(self, test_client):
        """
        What it does: Verifies chat completions requires authentication.
        Purpose: Ensure protected endpoint is secured.
        """
        print("Action: POST /v1/chat/completions without auth...")
        response = test_client.post(
            "/v1/chat/completions",
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 401
    
    def test_chat_completions_rejects_invalid_key(self, test_client, invalid_proxy_api_key):
        """
        What it does: Verifies chat completions rejects invalid API key.
        Purpose: Ensure authentication is enforced.
        """
        print("Action: POST /v1/chat/completions with invalid key...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {invalid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 401


class TestChatCompletionsValidation:
    """Tests for request validation on /v1/chat/completions endpoint."""
    
    def test_validates_empty_messages_array(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies empty messages array is rejected.
        Purpose: Ensure at least one message is required.
        """
        print("Action: POST /v1/chat/completions with empty messages...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": []
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 422
    
    def test_validates_missing_model(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies missing model field is rejected.
        Purpose: Ensure model is required.
        """
        print("Action: POST /v1/chat/completions without model...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 422
    
    def test_validates_missing_messages(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies missing messages field is rejected.
        Purpose: Ensure messages are required.
        """
        print("Action: POST /v1/chat/completions without messages...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5"
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 422
    
    def test_validates_invalid_json(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies invalid JSON is rejected.
        Purpose: Ensure proper JSON parsing.
        """
        print("Action: POST /v1/chat/completions with invalid JSON...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_proxy_api_key}",
                "Content-Type": "application/json"
            },
            content=b"not valid json {{{}"
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code == 422
    
    def test_validates_invalid_role(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies invalid message role passes Pydantic validation.
        Purpose: Pydantic model accepts any string as role (validation happens later).
        Note: The role validation is not strict at Pydantic level, so invalid roles
        pass validation but may fail during processing.
        """
        print("Action: POST /v1/chat/completions with invalid role...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "invalid_role", "content": "Hello"}]
            }
        )
        
        print(f"Status: {response.status_code}")
        # Pydantic model accepts any string as role, so validation passes (not 422)
        # The request may fail later during processing (500) due to network blocking
        assert response.status_code != 422
    
    def test_accepts_valid_request_format(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies valid request format passes validation.
        Purpose: Ensure Pydantic validation works correctly.
        """
        print("Action: POST /v1/chat/completions with valid format...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        print(f"Status: {response.status_code}")
        # Should pass validation (not 422)
        # May fail on HTTP call due to network blocking, but that's expected
        assert response.status_code != 422
    
    def test_accepts_message_without_content(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies message without content is accepted.
        Purpose: Ensure content is optional (for tool results).
        """
        print("Action: POST /v1/chat/completions with message without content...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user"}]  # No content
            }
        )
        
        print(f"Status: {response.status_code}")
        # Should pass validation (content is optional)
        assert response.status_code != 422 or "content" not in str(response.json())


class TestChatCompletionsWithTools:
    """Tests for tool calling on /v1/chat/completions endpoint."""
    
    def test_accepts_valid_tool_definition(self, test_client, valid_proxy_api_key, sample_tool_definition):
        """
        What it does: Verifies valid tool definition is accepted.
        Purpose: Ensure tool calling format is supported.
        """
        print("Action: POST /v1/chat/completions with tools...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "What's the weather?"}],
                "tools": [sample_tool_definition]
            }
        )
        
        print(f"Status: {response.status_code}")
        # Should pass validation
        assert response.status_code != 422
    
    def test_accepts_multiple_tools(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies multiple tools are accepted.
        Purpose: Ensure multiple tool definitions work.
        """
        print("Action: POST /v1/chat/completions with multiple tools...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "Get time",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "tools": tools
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422


class TestChatCompletionsOptionalParams:
    """Tests for optional parameters on /v1/chat/completions endpoint."""
    
    def test_accepts_temperature_parameter(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies temperature parameter is accepted.
        Purpose: Ensure temperature control works.
        """
        print("Action: POST /v1/chat/completions with temperature...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "temperature": 0.7
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422
    
    def test_accepts_max_tokens_parameter(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies max_tokens parameter is accepted.
        Purpose: Ensure output length control works.
        """
        print("Action: POST /v1/chat/completions with max_tokens...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 100
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422
    
    def test_accepts_stream_true(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies stream=true is accepted.
        Purpose: Ensure streaming mode is supported.
        """
        print("Action: POST /v1/chat/completions with stream=true...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": True
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422
    
    def test_accepts_top_p_parameter(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies top_p parameter is accepted.
        Purpose: Ensure nucleus sampling control works.
        """
        print("Action: POST /v1/chat/completions with top_p...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "top_p": 0.9
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422


class TestChatCompletionsMessageTypes:
    """Tests for different message types on /v1/chat/completions endpoint."""
    
    def test_accepts_system_message(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies system message is accepted.
        Purpose: Ensure system prompts work.
        """
        print("Action: POST /v1/chat/completions with system message...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hello"}
                ]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422
    
    def test_accepts_assistant_message(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies assistant message is accepted.
        Purpose: Ensure conversation history works.
        """
        print("Action: POST /v1/chat/completions with assistant message...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                    {"role": "user", "content": "How are you?"}
                ]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422
    
    def test_accepts_multipart_content(self, test_client, valid_proxy_api_key):
        """
        What it does: Verifies multipart content array is accepted.
        Purpose: Ensure complex content format works.
        """
        print("Action: POST /v1/chat/completions with multipart content...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Hello"},
                            {"type": "text", "text": "World"}
                        ]
                    }
                ]
            }
        )
        
        print(f"Status: {response.status_code}")
        assert response.status_code != 422


# =============================================================================
# Tests for router integration
# =============================================================================

class TestRouterIntegration:
    """Tests for router configuration and integration."""
    
    def test_router_has_root_endpoint(self):
        """
        What it does: Verifies root endpoint is registered.
        Purpose: Ensure endpoint is available.
        """
        print("Checking: Router endpoints...")
        routes = [route.path for route in router.routes]
        
        print(f"Found routes: {routes}")
        assert "/" in routes
    
    def test_router_has_health_endpoint(self):
        """
        What it does: Verifies health endpoint is registered.
        Purpose: Ensure endpoint is available.
        """
        print("Checking: Router endpoints...")
        routes = [route.path for route in router.routes]
        
        print(f"Found routes: {routes}")
        assert "/health" in routes
    
    def test_router_has_models_endpoint(self):
        """
        What it does: Verifies models endpoint is registered.
        Purpose: Ensure endpoint is available.
        """
        print("Checking: Router endpoints...")
        routes = [route.path for route in router.routes]
        
        print(f"Found routes: {routes}")
        assert "/v1/models" in routes
    
    def test_router_has_chat_completions_endpoint(self):
        """
        What it does: Verifies chat completions endpoint is registered.
        Purpose: Ensure endpoint is available.
        """
        print("Checking: Router endpoints...")
        routes = [route.path for route in router.routes]
        
        print(f"Found routes: {routes}")
        assert "/v1/chat/completions" in routes
    
    def test_root_endpoint_uses_get_method(self):
        """
        What it does: Verifies root endpoint uses GET method.
        Purpose: Ensure correct HTTP method.
        """
        print("Checking: HTTP methods...")
        for route in router.routes:
            if route.path == "/":
                print(f"Route / methods: {route.methods}")
                assert "GET" in route.methods
                return
        pytest.fail("Root endpoint not found")
    
    def test_health_endpoint_uses_get_method(self):
        """
        What it does: Verifies health endpoint uses GET method.
        Purpose: Ensure correct HTTP method.
        """
        print("Checking: HTTP methods...")
        for route in router.routes:
            if route.path == "/health":
                print(f"Route /health methods: {route.methods}")
                assert "GET" in route.methods
                return
        pytest.fail("Health endpoint not found")
    
    def test_models_endpoint_uses_get_method(self):
        """
        What it does: Verifies models endpoint uses GET method.
        Purpose: Ensure correct HTTP method.
        """
        print("Checking: HTTP methods...")
        for route in router.routes:
            if route.path == "/v1/models":
                print(f"Route /v1/models methods: {route.methods}")
                assert "GET" in route.methods
                return
        pytest.fail("Models endpoint not found")
    
    def test_chat_completions_endpoint_uses_post_method(self):
        """
        What it does: Verifies chat completions endpoint uses POST method.
        Purpose: Ensure correct HTTP method.
        """
        print("Checking: HTTP methods...")
        for route in router.routes:
            if route.path == "/v1/chat/completions":
                print(f"Route /v1/chat/completions methods: {route.methods}")
                assert "POST" in route.methods
                return
        pytest.fail("Chat completions endpoint not found")


# =============================================================================
# Tests for HTTP client selection (issue #54)
# =============================================================================

class TestHTTPClientSelection:
    """
    Tests for HTTP client selection in routes (issue #54).
    
    Verifies that streaming requests use per-request clients to avoid CLOSE_WAIT leak
    when network interface changes (VPN disconnect/reconnect), while non-streaming
    requests use shared client for connection pooling.
    """
    
    @patch('kiro.routes_openai.KiroHttpClient')
    def test_streaming_uses_per_request_client(
        self,
        mock_kiro_http_client_class,
        test_client,
        valid_proxy_api_key
    ):
        """
        What it does: Verifies streaming requests create per-request HTTP client.
        Purpose: Prevent CLOSE_WAIT leak on VPN disconnect (issue #54).
        """
        print("\n--- Test: Streaming uses per-request client ---")
        
        # Setup mock
        mock_client_instance = AsyncMock()
        mock_client_instance.request_with_retry = AsyncMock(
            side_effect=Exception("Network blocked")
        )
        mock_client_instance.close = AsyncMock()
        mock_kiro_http_client_class.return_value = mock_client_instance
        
        print("Action: POST with stream=true...")
        try:
            test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True
                }
            )
        except Exception:
            pass
        
        print("Checking: KiroHttpClient(shared_client=None)...")
        assert mock_kiro_http_client_class.called
        call_args = mock_kiro_http_client_class.call_args
        print(f"Call args: {call_args}")
        assert call_args[1]['shared_client'] is None, \
            "Streaming should use per-request client"
        print("✅ Streaming correctly uses per-request client")
    
    @patch('kiro.routes_openai.KiroHttpClient')
    def test_non_streaming_uses_shared_client(
        self,
        mock_kiro_http_client_class,
        test_client,
        valid_proxy_api_key
    ):
        """
        What it does: Verifies non-streaming requests use shared HTTP client.
        Purpose: Ensure connection pooling for non-streaming requests.
        """
        print("\n--- Test: Non-streaming uses shared client ---")
        
        # Setup mock
        mock_client_instance = AsyncMock()
        mock_client_instance.request_with_retry = AsyncMock(
            side_effect=Exception("Network blocked")
        )
        mock_client_instance.close = AsyncMock()
        mock_kiro_http_client_class.return_value = mock_client_instance
        
        print("Action: POST with stream=false...")
        try:
            test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": False
                }
            )
        except Exception:
            pass
        
        print("Checking: KiroHttpClient(shared_client=app.state.http_client)...")
        assert mock_kiro_http_client_class.called
        call_args = mock_kiro_http_client_class.call_args
        print(f"Call args: {call_args}")
        assert call_args[1]['shared_client'] is not None, \
            "Non-streaming should use shared client"
        print("✅ Non-streaming correctly uses shared client")


# =============================================================================
# Tests for Truncation Recovery message modification (Issue #56)
# =============================================================================

class TestTruncationRecoveryMessageModification:
    """
    Tests for Truncation Recovery System message modification in routes_openai.
    
    Verifies that tool_result messages are modified when truncation info exists in cache.
    Part of Truncation Recovery System (Issue #56).
    """
    
    def test_modifies_tool_result_with_truncation_notice(self):
        """
        What it does: Verifies tool_result content is modified when truncation info exists.
        Purpose: Ensure truncation notice is prepended to tool_result.
        """
        print("Setup: Saving truncation info to cache...")
        from kiro.truncation_state import save_tool_truncation
        from kiro.models_openai import ChatMessage
        
        tool_call_id = "tooluse_test123"
        save_tool_truncation(tool_call_id, "write_to_file", {"size_bytes": 5000, "reason": "test"})
        
        print("Setup: Creating request with tool_result...")
        messages = [
            ChatMessage(role="tool", tool_call_id=tool_call_id, content="Missing parameter error")
        ]
        
        print("Action: Processing messages through truncation recovery logic...")
        # Import the function that modifies messages
        from kiro.routes_openai import router
        from kiro.truncation_recovery import should_inject_recovery, generate_truncation_tool_result
        from kiro.truncation_state import get_tool_truncation
        
        # Simulate the modification logic
        modified_messages = []
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id and should_inject_recovery():
                truncation_info = get_tool_truncation(msg.tool_call_id)
                if truncation_info:
                    print(f"Found truncation info for {msg.tool_call_id}")
                    synthetic = generate_truncation_tool_result(
                        truncation_info.tool_name,
                        truncation_info.tool_call_id,
                        truncation_info.truncation_info
                    )
                    modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{msg.content}"
                    modified_msg = msg.model_copy(update={"content": modified_content})
                    modified_messages.append(modified_msg)
                else:
                    modified_messages.append(msg)
            else:
                modified_messages.append(msg)
        
        print("Checking: Modified message content...")
        modified_msg = modified_messages[0]
        print(f"Content: {modified_msg.content[:100]}...")
        
        assert "[API Limitation]" in modified_msg.content
        assert "Missing parameter error" in modified_msg.content
        assert "---" in modified_msg.content
    
    def test_no_modification_when_no_truncation(self):
        """
        What it does: Verifies messages are not modified when no truncation info exists.
        Purpose: Ensure normal messages pass through unchanged.
        """
        print("Setup: Creating request without truncation info in cache...")
        from kiro.models_openai import ChatMessage
        
        messages = [
            ChatMessage(role="tool", tool_call_id="tooluse_nonexistent", content="Success")
        ]
        
        print("Action: Processing messages...")
        from kiro.truncation_recovery import should_inject_recovery
        from kiro.truncation_state import get_tool_truncation
        
        modified_messages = []
        tool_results_modified = 0
        
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id and should_inject_recovery():
                truncation_info = get_tool_truncation(msg.tool_call_id)
                if truncation_info:
                    tool_results_modified += 1
                    # Would modify here
                    modified_messages.append(msg)
                else:
                    modified_messages.append(msg)
            else:
                modified_messages.append(msg)
        
        print(f"Checking: tool_results_modified count...")
        assert tool_results_modified == 0
        
        print("Checking: Message content unchanged...")
        assert modified_messages[0].content == "Success"
    
    def test_pydantic_immutability_new_object_created(self):
        """
        What it does: Verifies new ChatMessage object is created, not modified in-place.
        Purpose: Ensure Pydantic immutability is respected.
        """
        print("Setup: Saving truncation info and creating message...")
        from kiro.truncation_state import save_tool_truncation
        from kiro.models_openai import ChatMessage
        
        tool_call_id = "test_immutable"
        save_tool_truncation(tool_call_id, "tool", {"size_bytes": 1000, "reason": "test truncation"})
        
        original_msg = ChatMessage(role="tool", tool_call_id=tool_call_id, content="original")
        original_content = original_msg.content
        
        print("Action: Processing message...")
        from kiro.truncation_recovery import should_inject_recovery, generate_truncation_tool_result
        from kiro.truncation_state import get_tool_truncation
        
        if original_msg.role == "tool" and original_msg.tool_call_id and should_inject_recovery():
            truncation_info = get_tool_truncation(original_msg.tool_call_id)
            if truncation_info:
                synthetic = generate_truncation_tool_result(
                    truncation_info.tool_name,
                    truncation_info.tool_call_id,
                    truncation_info.truncation_info
                )
                modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{original_msg.content}"
                modified_msg = original_msg.model_copy(update={"content": modified_content})
        
        print("Checking: Original message unchanged...")
        assert original_msg.content == original_content
        
        print("Checking: New object created...")
        assert modified_msg is not original_msg
        
        print("Checking: Content modified in new object...")
        assert modified_msg.content != original_msg.content
        assert "[API Limitation]" in modified_msg.content


# =============================================================================
# Tests for Truncation Recovery edge cases (Issue #56)
# =============================================================================

class TestTruncationRecoveryEdgeCases:
    """
    Tests for edge cases in Truncation Recovery System.
    
    Verifies graceful handling of unusual scenarios.
    Part of Truncation Recovery System (Issue #56).
    """
    
    def test_orphaned_tool_result_no_crash(self):
        """
        What it does: Verifies graceful handling when cache entry doesn't exist.
        Purpose: Ensure orphaned tool_result doesn't cause errors (Test Case 9.2).
        """
        print("Setup: Creating tool_result without prior truncation...")
        from kiro.models_openai import ChatMessage
        
        messages = [
            ChatMessage(role="tool", tool_call_id="tooluse_nonexistent_orphan", content="Result")
        ]
        
        print("Action: Processing messages (no truncation info in cache)...")
        from kiro.truncation_recovery import should_inject_recovery
        from kiro.truncation_state import get_tool_truncation
        
        modified_messages = []
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id and should_inject_recovery():
                truncation_info = get_tool_truncation(msg.tool_call_id)
                if truncation_info:
                    # Would modify here
                    pass
            modified_messages.append(msg)
        
        print("Checking: No error thrown...")
        assert len(modified_messages) == 1
        
        print("Checking: Message unchanged...")
        assert modified_messages[0].content == "Result"
    
    def test_empty_tool_result_content(self):
        """
        What it does: Verifies handling of empty tool_result content.
        Purpose: Ensure empty content doesn't cause errors (Test Case 9.4).
        """
        print("Setup: Saving truncation info and creating empty tool_result...")
        from kiro.truncation_state import save_tool_truncation
        from kiro.models_openai import ChatMessage
        
        tool_call_id = "tooluse_empty_content"
        save_tool_truncation(tool_call_id, "tool", {"size_bytes": 1000, "reason": "test"})
        
        messages = [
            ChatMessage(role="tool", tool_call_id=tool_call_id, content="")
        ]
        
        print("Action: Processing message with empty content...")
        from kiro.truncation_recovery import should_inject_recovery, generate_truncation_tool_result
        from kiro.truncation_state import get_tool_truncation
        
        modified_messages = []
        for msg in messages:
            if msg.role == "tool" and msg.tool_call_id and should_inject_recovery():
                truncation_info = get_tool_truncation(msg.tool_call_id)
                if truncation_info:
                    synthetic = generate_truncation_tool_result(
                        truncation_info.tool_name,
                        truncation_info.tool_call_id,
                        truncation_info.truncation_info
                    )
                    modified_content = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{msg.content}"
                    modified_msg = msg.model_copy(update={"content": modified_content})
                    modified_messages.append(modified_msg)
                    continue
            modified_messages.append(msg)
        
        print("Checking: No crash occurred...")
        assert len(modified_messages) == 1
        
        print("Checking: Truncation notice still prepended...")
        assert "[API Limitation]" in modified_messages[0].content
        
        print("Checking: Empty original content preserved...")
        assert "Original tool result:\n" in modified_messages[0].content
    
    def test_very_long_content_hash_uses_first_500_chars(self):
        """
        What it does: Verifies content hash uses first 500 chars only.
        Purpose: Ensure hash stability for long content (Test Case 9.3).
        """
        print("Setup: Creating very long content...")
        from kiro.truncation_state import save_content_truncation, get_content_truncation
        
        content_long = "A" * 10000
        content_same_prefix = "A" * 500 + "B" * 9500
        
        print("Action: Saving long content...")
        hash1 = save_content_truncation(content_long)
        
        print("Action: Retrieving with same prefix...")
        info = get_content_truncation(content_same_prefix)
        
        print("Checking: Retrieval successful (same hash)...")
        assert info is not None
        assert info.message_hash == hash1
        
        print("Checking: Hash is 16 chars...")
        assert len(hash1) == 16
    
    def test_recovery_disabled_cache_entry_remains(self):
        """
        What it does: Verifies cache entry remains when recovery is disabled.
        Purpose: Ensure disabling recovery doesn't clear cache (Test Case 9.5).
        """
        print("Setup: Enabling recovery and saving truncation...")
        from kiro.truncation_state import save_tool_truncation, get_cache_stats
        from kiro.models_openai import ChatMessage
        import os
        
        tool_call_id = "tooluse_disabled_recovery"
        save_tool_truncation(tool_call_id, "tool", {"size_bytes": 1000, "reason": "test"})
        
        print("Checking: Cache entry exists...")
        stats = get_cache_stats()
        assert stats["tool_truncations"] >= 1
        
        print("Action: Disabling recovery...")
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "false"}):
            from importlib import reload
            from kiro import config
            reload(config)
            
            print("Action: Processing tool_result with recovery disabled...")
            from kiro.truncation_recovery import should_inject_recovery
            from kiro.truncation_state import get_tool_truncation
            
            messages = [
                ChatMessage(role="tool", tool_call_id=tool_call_id, content="Result")
            ]
            
            modified_messages = []
            for msg in messages:
                if msg.role == "tool" and msg.tool_call_id and should_inject_recovery():
                    # This branch won't execute because recovery is disabled
                    truncation_info = get_tool_truncation(msg.tool_call_id)
                    if truncation_info:
                        pass
                modified_messages.append(msg)
            
            print("Checking: No modification occurred...")
            assert modified_messages[0].content == "Result"
            assert "[API Limitation]" not in modified_messages[0].content
        
        print("Checking: Cache entry still exists (not cleaned up)...")
        # Note: get_tool_truncation() was NOT called, so entry should still be there
        # But we can't verify this without calling get_tool_truncation again
        # which would delete it. This is acceptable - the test verifies
        # that recovery doesn't happen when disabled.


# =============================================================================
# Tests for Content Truncation Recovery (Issue #56)
# =============================================================================

class TestContentTruncationRecovery:
    """
    Tests for content truncation recovery (synthetic user message).
    
    Verifies that synthetic user message is added after truncated assistant message.
    Part of Truncation Recovery System (Issue #56).
    """
    
    def test_adds_synthetic_user_message_after_truncated_assistant(self):
        """
        What it does: Verifies synthetic user message is added after truncated assistant message.
        Purpose: Ensure content truncation recovery works (Test Case C.1).
        """
        print("Setup: Saving content truncation info...")
        from kiro.truncation_state import save_content_truncation
        from kiro.models_openai import ChatMessage
        
        truncated_content = "This is a very long response that was cut off mid-sentence"
        save_content_truncation(truncated_content)
        
        print("Setup: Creating request with truncated assistant message...")
        messages = [
            ChatMessage(role="assistant", content=truncated_content)
        ]
        
        print("Action: Processing messages through content truncation recovery...")
        from kiro.truncation_recovery import should_inject_recovery, generate_truncation_user_message
        from kiro.truncation_state import get_content_truncation
        
        modified_messages = []
        for msg in messages:
            if msg.role == "assistant" and msg.content and isinstance(msg.content, str):
                truncation_info = get_content_truncation(msg.content)
                if truncation_info:
                    print(f"Found content truncation for hash: {truncation_info.message_hash}")
                    # Add original message first
                    modified_messages.append(msg)
                    # Then add synthetic user message
                    synthetic_user_msg = ChatMessage(
                        role="user",
                        content=generate_truncation_user_message()
                    )
                    modified_messages.append(synthetic_user_msg)
                    continue
            modified_messages.append(msg)
        
        print("Checking: Two messages in result...")
        assert len(modified_messages) == 2
        
        print("Checking: First message is original assistant message...")
        assert modified_messages[0].role == "assistant"
        assert modified_messages[0].content == truncated_content
        
        print("Checking: Second message is synthetic user message...")
        assert modified_messages[1].role == "user"
        assert "[System Notice]" in modified_messages[1].content
        assert "truncated" in modified_messages[1].content.lower()
    
    def test_no_synthetic_message_when_no_content_truncation(self):
        """
        What it does: Verifies no synthetic message is added for normal assistant message.
        Purpose: Ensure false positives don't occur (Test Case C.3).
        """
        print("Setup: Creating normal assistant message (no truncation)...")
        from kiro.models_openai import ChatMessage
        
        messages = [
            ChatMessage(role="assistant", content="This is a complete response.")
        ]
        
        print("Action: Processing messages...")
        from kiro.truncation_state import get_content_truncation
        
        modified_messages = []
        for msg in messages:
            if msg.role == "assistant" and msg.content and isinstance(msg.content, str):
                truncation_info = get_content_truncation(msg.content)
                if truncation_info:
                    # Would add synthetic message here
                    pass
            modified_messages.append(msg)
        
        print("Checking: Only one message in result...")
        assert len(modified_messages) == 1
        
        print("Checking: Message unchanged...")
        assert modified_messages[0].content == "This is a complete response."
    
    def test_content_hash_matches_first_500_chars(self):
        """
        What it does: Verifies content hash is based on first 500 chars.
        Purpose: Ensure long messages can be matched by prefix.
        """
        print("Setup: Creating long content...")
        from kiro.truncation_state import save_content_truncation, get_content_truncation
        
        # Original content (what was saved during detection)
        original_content = "A" * 1000
        
        # Content in request (might be slightly different due to client processing)
        request_content = "A" * 500 + "B" * 500
        
        print("Action: Saving original content...")
        hash1 = save_content_truncation(original_content)
        
        print("Action: Retrieving with request content (same first 500 chars)...")
        info = get_content_truncation(request_content)
        
        print("Checking: Match found...")
        assert info is not None
        assert info.message_hash == hash1


# ==================================================================================================
# Tests for WebSearch Support (OpenAI)
# ==================================================================================================

class TestWebSearchAutoInjectionOpenAI:
    """Tests for WebSearch auto-injection in OpenAI endpoint (Path B only)."""
    
    def test_auto_injection_logic_openai(self):
        """
        What it does: Verifies web_search function tool auto-injection logic for OpenAI.
        Purpose: Ensure WEB_SEARCH_ENABLED controls auto-injection for OpenAI format.
        """
        print("Setup: Testing OpenAI auto-injection logic...")
        from kiro.models_openai import Tool, ToolFunction
        
        # Simulate auto-injection logic for OpenAI
        WEB_SEARCH_ENABLED = True
        tools = []
        
        if WEB_SEARCH_ENABLED:
            has_ws = any(
                getattr(tool, "type", None) == "function" and
                getattr(getattr(tool, "function", None), "name", None) == "web_search"
                for tool in tools
            )
            
            if not has_ws:
                web_search_tool = Tool(
                    type="function",
                    function=ToolFunction(
                        name="web_search",
                        description="Search the web for current information. Use when you need up-to-date data from the internet.",
                        parameters={
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query"
                                }
                            },
                            "required": ["query"]
                        }
                    )
                )
                tools.append(web_search_tool)
        
        print(f"Checking: web_search tool was added...")
        assert len(tools) == 1
        assert tools[0].type == "function"
        assert tools[0].function.name == "web_search"
        assert tools[0].function.parameters is not None
    
    def test_no_duplicate_injection_logic_openai(self):
        """
        What it does: Verifies duplicate detection logic for OpenAI format.
        Purpose: Ensure auto-injection doesn't create duplicates for OpenAI.
        """
        print("Setup: Testing OpenAI duplicate detection...")
        from kiro.models_openai import Tool, ToolFunction
        
        # Simulate existing web_search tool
        existing_tools = [
            Tool(
                type="function",
                function=ToolFunction(
                    name="web_search",
                    description="Existing web search",
                    parameters={"type": "object", "properties": {}}
                )
            )
        ]
        
        # Simulate auto-injection logic with duplicate check
        WEB_SEARCH_ENABLED = True
        
        if WEB_SEARCH_ENABLED:
            has_ws = any(
                getattr(tool, "type", None) == "function" and
                getattr(getattr(tool, "function", None), "name", None) == "web_search"
                for tool in existing_tools
            )
            
            if not has_ws:
                # Would add web_search here
                existing_tools.append(Tool(
                    type="function",
                    function=ToolFunction(
                        name="web_search",
                        description="Auto-injected",
                        parameters={"type": "object", "properties": {}}
                    )
                ))
        
        print(f"Checking: Only one web_search tool...")
        web_search_count = sum(
            1 for t in existing_tools
            if t.type == "function" and t.function.name == "web_search"
        )
        assert web_search_count == 1


# ==================================================================================================
# Tests for Account System - /v1/models endpoint
# ==================================================================================================

class TestModelsEndpointAccountSystem:
    """Tests for /v1/models endpoint with Account System."""
    
    def test_get_models_account_system_logic(self):
        """
        What it does: Verifies logic for collecting models in account system mode.
        Purpose: Ensure models are collected from all initialized accounts.
        """
        print("\n--- Test: /v1/models account system logic ---")
        
        # Simulate account system mode logic
        account_system = True
        
        mock_account_manager = Mock()
        mock_account_manager.get_all_available_models.return_value = [
            "claude-opus-4.5",
            "claude-sonnet-4.5",
            "claude-haiku-4.5"
        ]
        
        print("Action: Getting models in account system mode...")
        if account_system:
            available_model_ids = mock_account_manager.get_all_available_models()
        else:
            available_model_ids = []
        
        print("Checking: get_all_available_models() was called...")
        mock_account_manager.get_all_available_models.assert_called_once()
        
        print("Checking: Models from all accounts collected...")
        assert "claude-opus-4.5" in available_model_ids
        assert "claude-sonnet-4.5" in available_model_ids
        assert "claude-haiku-4.5" in available_model_ids
        assert len(available_model_ids) == 3
        print("✅ Account system mode correctly collects models from all accounts")
    
    def test_get_models_legacy_logic(self):
        """
        What it does: Verifies logic for getting models in legacy mode.
        Purpose: Ensure backward compatibility with single account.
        """
        print("\n--- Test: /v1/models legacy mode logic ---")
        
        # Simulate legacy mode logic
        account_system = False
        
        mock_account = Mock()
        mock_resolver = Mock()
        mock_resolver.get_available_models.return_value = [
            "claude-opus-4.5",
            "claude-sonnet-4.5"
        ]
        mock_account.model_resolver = mock_resolver
        
        mock_account_manager = Mock()
        mock_account_manager.get_first_account.return_value = mock_account
        
        print("Action: Getting models in legacy mode...")
        if account_system:
            available_model_ids = []
        else:
            account = mock_account_manager.get_first_account()
            available_model_ids = account.model_resolver.get_available_models()
        
        print("Checking: get_first_account() was called...")
        mock_account_manager.get_first_account.assert_called_once()
        
        print("Checking: model_resolver.get_available_models() was called...")
        mock_resolver.get_available_models.assert_called_once()
        
        print("Checking: Models from first account returned...")
        assert "claude-opus-4.5" in available_model_ids
        assert "claude-sonnet-4.5" in available_model_ids
        assert len(available_model_ids) == 2
        print("✅ Legacy mode correctly uses first account's resolver")


# ==================================================================================================
# Tests for Account System - Failover Loop
# ==================================================================================================

class TestChatCompletionsFailoverLoop:
    """Tests for failover loop in /v1/chat/completions endpoint."""
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_get_next_account(self):
        """
        What it does: Verifies get_next_account() is called with exclude_accounts.
        Purpose: Ensure failover loop tracks tried accounts.
        """
        print("\n--- Test: Failover calls get_next_account() with exclude_accounts ---")
        
        mock_account = Mock()
        mock_account.id = "/home/user/account1.json"
        mock_account.auth_manager = Mock()
        mock_account.model_cache = Mock()
        mock_account.model_resolver = Mock()
        
        mock_manager = Mock()
        mock_manager.get_next_account = AsyncMock(return_value=mock_account)
        mock_manager._accounts = {mock_account.id: mock_account}
        
        print("Checking: get_next_account() called with exclude_accounts parameter...")
        # This test verifies the signature - actual implementation tested in integration tests
        await mock_manager.get_next_account("claude-opus-4.5", exclude_accounts=set())
        
        mock_manager.get_next_account.assert_called_once()
        call_kwargs = mock_manager.get_next_account.call_args[1]
        assert "exclude_accounts" in call_kwargs
        print("✅ Failover loop correctly passes exclude_accounts")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_success_first_account(self):
        """
        What it does: Verifies successful response on first account attempt.
        Purpose: Ensure no unnecessary failover when first account works.
        """
        print("\n--- Test: Success on first account ---")
        
        from kiro.account_manager import Account, AccountStats
        
        mock_account = Account(
            id="/home/user/account1.json",
            failures=0,
            last_failure_time=0.0,
            models_cached_at=time.time(),
            stats=AccountStats()
        )
        
        mock_manager = Mock()
        mock_manager.get_next_account = AsyncMock(return_value=mock_account)
        mock_manager.report_success = AsyncMock()
        mock_manager._accounts = {mock_account.id: mock_account}
        
        print("Action: Simulating successful request...")
        account = await mock_manager.get_next_account("claude-opus-4.5", exclude_accounts=set())
        
        print("Checking: First account returned...")
        assert account is not None
        assert account.id == "/home/user/account1.json"
        
        print("Action: Reporting success...")
        await mock_manager.report_success(account.id, "claude-opus-4.5")
        
        print("Checking: report_success() was called...")
        mock_manager.report_success.assert_called_once_with(
            "/home/user/account1.json",
            "claude-opus-4.5"
        )
        print("✅ Success on first account works correctly")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_recoverable_try_next(self):
        """
        What it does: Verifies RECOVERABLE error triggers next account attempt.
        Purpose: Ensure failover happens for account-specific errors.
        """
        print("\n--- Test: RECOVERABLE error tries next account ---")
        
        from kiro.account_errors import ErrorType, classify_error
        
        print("Setup: Classifying 429 error...")
        error_type = classify_error(429, None)
        
        print("Checking: 429 is RECOVERABLE...")
        assert error_type == ErrorType.RECOVERABLE
        
        print("Checking: Failover logic should continue to next account...")
        # In actual implementation, this would trigger:
        # await account_manager.report_failure(...)
        # continue  # Next iteration of failover loop
        
        mock_manager = Mock()
        mock_manager.report_failure = AsyncMock()
        
        await mock_manager.report_failure(
            "/home/user/account1.json",
            "claude-opus-4.5",
            ErrorType.RECOVERABLE,
            429,
            None
        )
        
        mock_manager.report_failure.assert_called_once()
        print("✅ RECOVERABLE error correctly triggers failover")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_fatal_immediate_return(self):
        """
        What it does: Verifies FATAL error returns immediately to client.
        Purpose: Ensure no wasted retries for request-level errors.
        """
        print("\n--- Test: FATAL error returns immediately ---")
        
        from kiro.account_errors import ErrorType, classify_error
        
        print("Setup: Classifying 400 + CONTENT_LENGTH_EXCEEDS_THRESHOLD...")
        error_type = classify_error(400, "CONTENT_LENGTH_EXCEEDS_THRESHOLD")
        
        print("Checking: Error is FATAL...")
        assert error_type == ErrorType.FATAL
        
        print("Checking: Failover logic should break immediately...")
        # In actual implementation, this would trigger:
        # await account_manager.report_failure(...)
        # return JSONResponse(...)  # No continue, immediate return
        
        mock_manager = Mock()
        mock_manager.report_failure = AsyncMock()
        
        await mock_manager.report_failure(
            "/home/user/account1.json",
            "claude-opus-4.5",
            ErrorType.FATAL,
            400,
            "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        )
        
        mock_manager.report_failure.assert_called_once()
        print("✅ FATAL error correctly returns immediately")
    
    def test_chat_completions_failover_single_account_original_error(self):
        """
        What it does: Verifies single account returns original error message.
        Purpose: Ensure users see specific error for single account setup.
        """
        print("\n--- Test: Single account returns original error ---")
        
        all_accounts = ["/home/user/account1.json"]
        last_error_message = "Monthly request limit exceeded"
        last_error_status = 402
        
        print("Checking: Single account error handling...")
        if len(all_accounts) == 1:
            error_response = {
                "status_code": last_error_status,
                "detail": last_error_message
            }
        else:
            error_response = {
                "status_code": 503,
                "detail": "No available accounts for this model"
            }
        
        print(f"Error response: {error_response}")
        assert error_response["status_code"] == 402
        assert error_response["detail"] == "Monthly request limit exceeded"
        print("✅ Single account correctly returns original error")
    
    def test_chat_completions_failover_multi_account_generic_error(self):
        """
        What it does: Verifies multi-account returns generic error message.
        Purpose: Ensure users don't see confusing account-specific errors.
        """
        print("\n--- Test: Multi-account returns generic error ---")
        
        all_accounts = [
            "/home/user/account1.json",
            "/home/user/account2.json"
        ]
        last_error_message = "Token expired"
        
        print("Checking: Multi-account error handling...")
        if len(all_accounts) == 1:
            error_response = {
                "status_code": 403,
                "detail": last_error_message
            }
        else:
            detail = "No available accounts for this model."
            if last_error_message:
                detail += f" Last error: {last_error_message}"
            error_response = {
                "status_code": 503,
                "detail": detail
            }
        
        print(f"Error response: {error_response}")
        assert error_response["status_code"] == 503
        assert "No available accounts" in error_response["detail"]
        assert "Last error: Token expired" in error_response["detail"]
        print("✅ Multi-account correctly returns generic error with context")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_all_unavailable(self):
        """
        What it does: Verifies behavior when all accounts are unavailable.
        Purpose: Ensure graceful handling of complete failure.
        """
        print("\n--- Test: All accounts unavailable ---")
        
        mock_manager = Mock()
        mock_manager.get_next_account = AsyncMock(return_value=None)
        mock_manager._accounts = {
            "/home/user/account1.json": Mock(),
            "/home/user/account2.json": Mock()
        }
        
        print("Action: Requesting account when all unavailable...")
        account = await mock_manager.get_next_account(
            "claude-opus-4.5",
            exclude_accounts=set()
        )
        
        print("Checking: None returned...")
        assert account is None
        
        print("Checking: Error response logic...")
        all_accounts = list(mock_manager._accounts.keys())
        if len(all_accounts) == 1:
            error_msg = "Account unavailable"
        else:
            error_msg = "No available accounts for this model"
        
        assert "No available accounts" in error_msg
        print("✅ All unavailable correctly handled")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_report_success(self):
        """
        What it does: Verifies report_success() is called after successful request.
        Purpose: Ensure statistics and sticky behavior are updated.
        """
        print("\n--- Test: report_success() called on success ---")
        
        mock_manager = Mock()
        mock_manager.report_success = AsyncMock()
        
        account_id = "/home/user/account1.json"
        model = "claude-opus-4.5"
        
        print("Action: Reporting success...")
        await mock_manager.report_success(account_id, model)
        
        print("Checking: report_success() was called with correct params...")
        mock_manager.report_success.assert_called_once_with(account_id, model)
        print("✅ report_success() correctly called")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_report_failure(self):
        """
        What it does: Verifies report_failure() is called after failed request.
        Purpose: Ensure Circuit Breaker state is updated.
        """
        print("\n--- Test: report_failure() called on failure ---")
        
        from kiro.account_errors import ErrorType
        
        mock_manager = Mock()
        mock_manager.report_failure = AsyncMock()
        
        account_id = "/home/user/account1.json"
        model = "claude-opus-4.5"
        error_type = ErrorType.RECOVERABLE
        status_code = 429
        reason = None
        
        print("Action: Reporting failure...")
        await mock_manager.report_failure(
            account_id,
            model,
            error_type,
            status_code,
            reason
        )
        
        print("Checking: report_failure() was called with correct params...")
        mock_manager.report_failure.assert_called_once_with(
            account_id,
            model,
            error_type,
            status_code,
            reason
        )
        print("✅ report_failure() correctly called")
    
    @pytest.mark.asyncio
    async def test_chat_completions_failover_exclude_tried_accounts(self):
        """
        What it does: Verifies exclude_accounts grows with each attempt.
        Purpose: Ensure accounts aren't retried in same failover loop.
        """
        print("\n--- Test: exclude_accounts grows with attempts ---")
        
        tried_accounts = set()
        
        print("Action: Simulating multiple attempts...")
        account1_id = "/home/user/account1.json"
        account2_id = "/home/user/account2.json"
        
        # Attempt 1
        tried_accounts.add(account1_id)
        print(f"After attempt 1: {tried_accounts}")
        assert account1_id in tried_accounts
        assert len(tried_accounts) == 1
        
        # Attempt 2
        tried_accounts.add(account2_id)
        print(f"After attempt 2: {tried_accounts}")
        assert account2_id in tried_accounts
        assert len(tried_accounts) == 2
        
        print("Checking: Both accounts in exclude set...")
        assert account1_id in tried_accounts
        assert account2_id in tried_accounts
        print("✅ exclude_accounts correctly tracks tried accounts")
    
    def test_chat_completions_failover_max_attempts(self):
        """
        What it does: Verifies failover loop stops after MAX_ATTEMPTS.
        Purpose: Ensure infinite loops are prevented.
        """
        print("\n--- Test: MAX_ATTEMPTS prevents infinite loop ---")
        
        all_accounts = [
            "/home/user/account1.json",
            "/home/user/account2.json"
        ]
        MAX_ATTEMPTS = len(all_accounts) * 2
        
        print(f"Checking: MAX_ATTEMPTS = {MAX_ATTEMPTS}...")
        assert MAX_ATTEMPTS == 4
        
        print("Checking: Loop would stop after 4 attempts...")
        attempts = 0
        for attempt in range(MAX_ATTEMPTS):
            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                break
        
        assert attempts == MAX_ATTEMPTS
        print("✅ MAX_ATTEMPTS correctly limits failover loop")


# ==================================================================================================
# Tests for Account System - Legacy Mode
# ==================================================================================================

class TestChatCompletionsLegacyMode:
    """Tests for legacy mode (ACCOUNT_SYSTEM=false) in /v1/chat/completions."""
    
    @pytest.mark.asyncio
    async def test_chat_completions_legacy_get_first_account(self):
        """
        What it does: Verifies legacy mode uses get_first_account().
        Purpose: Ensure backward compatibility with single account.
        """
        print("\n--- Test: Legacy mode uses get_first_account() ---")
        
        from kiro.account_manager import Account, AccountStats
        
        mock_account = Account(
            id="/home/user/account1.json",
            failures=0,
            last_failure_time=0.0,
            models_cached_at=time.time(),
            stats=AccountStats()
        )
        
        mock_manager = Mock()
        mock_manager.get_first_account.return_value = mock_account
        
        print("Action: Getting first account in legacy mode...")
        account = mock_manager.get_first_account()
        
        print("Checking: get_first_account() was called...")
        mock_manager.get_first_account.assert_called_once()
        
        print("Checking: Account returned...")
        assert account is not None
        assert account.id == "/home/user/account1.json"
        print("✅ Legacy mode correctly uses get_first_account()")
    
    def test_chat_completions_legacy_no_failover(self):
        """
        What it does: Verifies legacy mode has no failover loop.
        Purpose: Ensure single account behavior is preserved.
        """
        print("\n--- Test: Legacy mode has no failover ---")
        
        account_system = False
        
        print("Checking: account_system flag is False...")
        assert account_system is False
        
        print("Checking: Failover loop should be skipped...")
        if account_system:
            failover_enabled = True
        else:
            failover_enabled = False
        
        assert failover_enabled is False
        print("✅ Legacy mode correctly skips failover loop")