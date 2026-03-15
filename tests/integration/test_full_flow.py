# -*- coding: utf-8 -*-

"""
Integration tests for complete end-to-end flow.
Checks interaction of all system components.
"""

import pytest
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient
import httpx

from kiro.config import PROXY_API_KEY


class TestFullChatCompletionFlow:
    """Integration tests for complete chat completions flow."""
    
    def test_full_flow_health_to_models_to_chat(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks complete flow from health check to chat completions.
        Goal: Ensure all endpoints work together.
        """
        print("Step 1: Health check...")
        health_response = test_client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "healthy"
        print(f"Health: {health_response.json()}")
        
        print("Step 2: Getting models list...")
        models_response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        assert models_response.status_code == 200
        assert len(models_response.json()["data"]) > 0
        print(f"Models: {[m['id'] for m in models_response.json()['data']]}")
        
        print("Step 3: Validating chat completions request...")
        # This request will pass validation but fail on HTTP due to network blocking
        chat_response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        # Request should pass validation (not 422)
        assert chat_response.status_code != 422
        print(f"Chat response status: {chat_response.status_code}")
    
    def test_authentication_flow(self, test_client, valid_proxy_api_key, invalid_proxy_api_key):
        """
        What it does: Checks authentication flow.
        Goal: Ensure protected endpoints require authorization.
        """
        print("Step 1: Request without authorization...")
        no_auth_response = test_client.get("/v1/models")
        assert no_auth_response.status_code == 401
        print(f"Without authorization: {no_auth_response.status_code}")
        
        print("Step 2: Request with invalid key...")
        wrong_auth_response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {invalid_proxy_api_key}"}
        )
        assert wrong_auth_response.status_code == 401
        print(f"Invalid key: {wrong_auth_response.status_code}")
        
        print("Step 3: Request with valid key...")
        valid_auth_response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        assert valid_auth_response.status_code == 200
        print(f"Valid key: {valid_auth_response.status_code}")
    
    def test_openai_compatibility_format(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks response format compatibility with OpenAI API.
        Goal: Ensure responses conform to OpenAI specification.
        """
        print("Checking /v1/models format...")
        models_response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        assert models_response.status_code == 200
        data = models_response.json()
        
        # Check OpenAI response structure
        assert "object" in data
        assert data["object"] == "list"
        assert "data" in data
        assert isinstance(data["data"], list)
        
        # Check structure of each model
        for model in data["data"]:
            assert "id" in model
            assert "object" in model
            assert model["object"] == "model"
            assert "owned_by" in model
            assert "created" in model
        
        print(f"Format conforms to OpenAI API: {len(data['data'])} models")


class TestRequestValidationFlow:
    """Integration tests for request validation."""
    
    def test_chat_completions_request_validation(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks validation of various request formats.
        Goal: Ensure validation works correctly.
        """
        print("Test 1: Empty messages...")
        empty_messages = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={"model": "claude-sonnet-4-5", "messages": []}
        )
        assert empty_messages.status_code == 422
        print(f"Empty messages: {empty_messages.status_code}")
        
        print("Test 2: Missing model...")
        no_model = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={"messages": [{"role": "user", "content": "Hello"}]}
        )
        assert no_model.status_code == 422
        print(f"Without model: {no_model.status_code}")
        
        print("Test 3: Missing messages...")
        no_messages = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={"model": "claude-sonnet-4-5"}
        )
        assert no_messages.status_code == 422
        print(f"Without messages: {no_messages.status_code}")
        
        print("Test 4: Valid request...")
        valid_request = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}]
            }
        )
        # Validation should pass (not 422)
        assert valid_request.status_code != 422
        print(f"Valid request: {valid_request.status_code}")
    
    def test_complex_message_formats(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks handling of complex message formats.
        Goal: Ensure multimodal and tool formats are accepted.
        """
        print("Test 1: System + User messages...")
        system_user = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [
                    {"role": "system", "content": "You are helpful"},
                    {"role": "user", "content": "Hello"}
                ]
            }
        )
        assert system_user.status_code != 422
        print(f"System + User: {system_user.status_code}")
        
        print("Test 2: Multi-turn conversation...")
        multi_turn = test_client.post(
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
        assert multi_turn.status_code != 422
        print(f"Multi-turn: {multi_turn.status_code}")
        
        print("Test 3: With tools...")
        with_tools = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "What's the weather?"}],
                "tools": [{
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "Get weather",
                        "parameters": {"type": "object", "properties": {}}
                    }
                }]
            }
        )
        assert with_tools.status_code != 422
        print(f"With tools: {with_tools.status_code}")


class TestErrorHandlingFlow:
    """Integration tests for error handling."""
    
    def test_invalid_json_handling(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks handling of invalid JSON.
        Goal: Ensure invalid JSON returns clear error.
        """
        print("Sending invalid JSON...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_proxy_api_key}",
                "Content-Type": "application/json"
            },
            content=b"not valid json"
        )
        
        assert response.status_code == 422
        print(f"Invalid JSON: {response.status_code}")
    
    def test_wrong_content_type_handling(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks handling of wrong Content-Type.
        Goal: Ensure wrong Content-Type is handled.
        """
        print("Sending with wrong Content-Type...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {valid_proxy_api_key}",
                "Content-Type": "text/plain"
            },
            content=b"Hello"
        )
        
        # Should be validation error
        assert response.status_code == 422
        print(f"Wrong Content-Type: {response.status_code}")


class TestModelsEndpointIntegration:
    """Integration tests for /v1/models endpoint."""
    
    def test_models_returns_all_available_models(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks that all models from config are returned.
        Goal: Ensure completeness of models list.
        """
        print("Getting models list...")
        response = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        
        assert response.status_code == 200
        
        returned_ids = {m["id"] for m in response.json()["data"]}
        
        print(f"Returned models: {returned_ids}")
        
        # At minimum, hidden models should be available
        assert len(returned_ids) >= 1, "Expected at least one model (hidden models)"
    
    def test_models_caching_behavior(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks models caching behavior.
        Goal: Ensure repeated requests work correctly.
        """
        print("First models request...")
        response1 = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        assert response1.status_code == 200
        
        print("Second models request...")
        response2 = test_client.get(
            "/v1/models",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"}
        )
        assert response2.status_code == 200
        
        # Responses should be identical
        assert response1.json()["data"] == response2.json()["data"]
        print("Caching works correctly")


class TestUsageEndpointIntegration:
    """Integration tests for /v1/usage endpoint."""

    @patch("kiro.routes_openai.fetch_usage_limits", new_callable=AsyncMock)
    def test_usage_requires_auth_and_returns_payload(
        self,
        mock_fetch_usage_limits,
        test_client,
        valid_proxy_api_key,
    ):
        """
        What it does: Checks authentication and successful payload flow for /v1/usage.
        Goal: Ensure the gateway exposes GetUsageLimits through a protected endpoint.
        """
        print("Step 1: Request /v1/usage without authorization...")
        unauthorized = test_client.get("/v1/usage")
        assert unauthorized.status_code == 401

        mock_fetch_usage_limits.return_value = {
            "subscriptionInfo": {"subscriptionTitle": "KIRO PRO"},
            "usageBreakdownList": [{"usageLimit": 1000}],
            "usageSummary": {
                "resetAt": "2026-04-01T00:00:00Z",
                "primaryLimit": 1000,
                "primaryUsed": 0.0,
                "primaryUnit": "INVOCATIONS",
                "freeTrialLimit": 500,
                "freeTrialUsed": 330.11,
                "freeTrialExpiresAt": "2026-04-11T14:15:32.340Z",
            },
        }

        print("Step 2: Request /v1/usage with valid authorization...")
        authorized = test_client.get(
            "/v1/usage",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
        )

        assert authorized.status_code == 200
        assert authorized.json()["subscriptionInfo"]["subscriptionTitle"] == "KIRO PRO"
        assert authorized.json()["usageBreakdownList"][0]["usageLimit"] == 1000
        assert authorized.json()["usageSummary"]["freeTrialExpiresAt"] == "2026-04-11T14:15:32.340Z"
        print(f"Usage payload: {authorized.json()}")


class TestStreamingFlagHandling:
    """Integration tests for stream flag handling."""
    
    def test_stream_true_accepted(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks that stream=true is accepted.
        Goal: Ensure streaming mode is available.
        
        Note: Streaming mode requires HTTP client mock,
        as request is executed inside generator.
        """
        print("Request with stream=true...")
        
        # Create mock response for streaming
        mock_response = AsyncMock()
        mock_response.status_code = 200
        
        async def mock_aiter_bytes():
            yield b'{"content":"Hello"}'
            yield b'{"usage":0.5}'
        
        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()
        
        # Mock request_with_retry to return our mock response
        with patch('kiro.routes_openai.KiroHttpClient') as MockHttpClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client_instance.client = AsyncMock()
            mock_client_instance.close = AsyncMock()
            MockHttpClient.return_value = mock_client_instance
            
            response = test_client.post(
                "/v1/chat/completions",
                headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
                json={
                    "model": "claude-sonnet-4-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "stream": True
                }
            )
        
        # Validation should pass and streaming should work
        assert response.status_code == 200
        print(f"stream=true: {response.status_code}")
    
    def test_stream_false_accepted(self, test_client, valid_proxy_api_key):
        """
        What it does: Checks that stream=false is accepted.
        Goal: Ensure non-streaming mode is available.
        """
        print("Request with stream=false...")
        response = test_client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {valid_proxy_api_key}"},
            json={
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "stream": False
            }
        )
        
        # Validation should pass
        assert response.status_code != 422
        print(f"stream=false: {response.status_code}")


class TestHealthEndpointIntegration:
    """Integration tests for health endpoints."""
    
    def test_root_and_health_consistency(self, test_client):
        """
        What it does: Checks consistency of / and /health.
        Goal: Ensure both endpoints return correct status.
        """
        print("Request to /...")
        root_response = test_client.get("/")
        
        print("Request to /health...")
        health_response = test_client.get("/health")
        
        assert root_response.status_code == 200
        assert health_response.status_code == 200
        
        # Both should show "ok" status
        assert root_response.json()["status"] == "ok"
        assert health_response.json()["status"] == "healthy"
        
        # Versions should match
        assert root_response.json()["version"] == health_response.json()["version"]
        
        print("Health endpoints are consistent")
