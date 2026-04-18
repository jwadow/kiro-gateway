# -*- coding: utf-8 -*-

"""
Common fixtures and utilities for testing Kiro Gateway.

Provides test isolation from external services and global state.
All tests MUST be completely isolated from the network.
"""

import asyncio
import json
import pytest
import time
from typing import AsyncGenerator, Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

import httpx
from fastapi.testclient import TestClient


# =============================================================================
# Event Loop Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Creates an event loop for the entire test session.
    Required for proper async fixture operation.
    """
    print("Creating event loop for test session...")
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    print("Closing event loop...")
    loop.close()


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Mocks environment variables for isolation from real credentials.
    """
    print("Setting up mocked environment variables...")
    monkeypatch.setenv("REFRESH_TOKEN", "test_refresh_token_abcdef")
    monkeypatch.setenv("PROXY_API_KEY", "test_proxy_key_12345")
    monkeypatch.setenv("PROFILE_ARN", "arn:aws:codewhisperer:us-east-1:123456789:profile/test")
    monkeypatch.setenv("KIRO_REGION", "us-east-1")
    return {
        "REFRESH_TOKEN": "test_refresh_token_abcdef",
        "PROXY_API_KEY": "test_proxy_key_12345",
        "PROFILE_ARN": "arn:aws:codewhisperer:us-east-1:123456789:profile/test",
        "KIRO_REGION": "us-east-1"
    }


# =============================================================================
# Token and Authentication Fixtures
# =============================================================================

@pytest.fixture
def valid_kiro_token():
    """Returns a valid mock Kiro access token."""
    return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.test_kiro_access_token"


@pytest.fixture
def mock_kiro_token_response(valid_kiro_token):
    """
    Factory for creating mock Kiro token refresh endpoint responses.
    """
    def _create_response(expires_in: int = 3600, token: str = None):
        return {
            "accessToken": token or valid_kiro_token,
            "refreshToken": "new_refresh_token_xyz",
            "expiresIn": expires_in,
            "profileArn": "arn:aws:codewhisperer:us-east-1:123456789:profile/test"
        }
    return _create_response


@pytest.fixture
def valid_proxy_api_key():
    """
    Returns the actual PROXY_API_KEY that the application is using.
    
    This reads the value from kiro.config, which was loaded when the app
    was imported. This ensures tests use the same key the app validates against.
    """
    from kiro.config import PROXY_API_KEY
    return PROXY_API_KEY


@pytest.fixture
def invalid_proxy_api_key():
    """Returns an invalid API key for negative tests."""
    return "invalid_wrong_secret_key"


@pytest.fixture
def auth_headers(valid_proxy_api_key):
    """
    Factory for creating valid and invalid Authorization headers.
    """
    def _create_headers(api_key: str = None, invalid: bool = False):
        if invalid:
            return {"Authorization": "Bearer wrong_key_123"}
        key = api_key or valid_proxy_api_key
        return {"Authorization": f"Bearer {key}"}
    
    return _create_headers


# =============================================================================
# Kiro Models Fixtures
# =============================================================================

@pytest.fixture
def mock_kiro_models_response():
    """
    Mock successful response from Kiro API for ListAvailableModels.
    """
    return {
        "models": [
            {
                "modelId": "claude-sonnet-4.5",
                "displayName": "Claude Sonnet 4.5",
                "tokenLimits": {
                    "maxInputTokens": 200000,
                    "maxOutputTokens": 8192
                }
            },
            {
                "modelId": "claude-opus-4.5",
                "displayName": "Claude Opus 4.5",
                "tokenLimits": {
                    "maxInputTokens": 200000,
                    "maxOutputTokens": 8192
                }
            },
            {
                "modelId": "claude-haiku-4.5",
                "displayName": "Claude Haiku 4.5",
                "tokenLimits": {
                    "maxInputTokens": 200000,
                    "maxOutputTokens": 8192
                }
            }
        ]
    }


# =============================================================================
# Kiro Streaming Response Fixtures
# =============================================================================

@pytest.fixture
def mock_kiro_streaming_chunks():
    """
    Returns a list of mock SSE chunks from Kiro API for streaming response.
    Covers: regular text, tool calls, usage.
    """
    return [
        # Chunk 1: Text start
        b'{"content":"Hello"}',
        # Chunk 2: Text continuation
        b'{"content":" World!"}',
        # Chunk 3: Tool call start
        b'{"name":"get_weather","toolUseId":"call_abc123"}',
        # Chunk 4: Tool call input
        b'{"input":"{\\"location\\": \\"Moscow\\"}"}',
        # Chunk 5: Tool call stop
        b'{"stop":true}',
        # Chunk 6: Usage
        b'{"usage":1.5}',
        # Chunk 7: Context usage
        b'{"contextUsagePercentage":25.5}',
    ]

@pytest.fixture
def mock_kiro_simple_text_chunks():
    """
    Mock simple text response from Kiro (without tool calls).
    """
    return [
        b'{"content":"This is a complete response."}',
        b'{"usage":0.5}',
        b'{"contextUsagePercentage":10.0}',
    ]


@pytest.fixture
def mock_kiro_stream_with_usage():
    """
    Mock Kiro SSE response with usage information.
    """
    return [
        b'{"content":"Final text."}',
        b'{"usage":1.3}',
        b'{"contextUsagePercentage":50.0}',
    ]


# =============================================================================
# OpenAI Request Fixtures
# =============================================================================

@pytest.fixture
def sample_openai_chat_request():
    """
    Factory for creating valid OpenAI chat completion requests.
    """
    def _create_request(
        model: str = "claude-sonnet-4-5",
        messages: list = None,
        stream: bool = False,
        temperature: float = None,
        max_tokens: int = None,
        tools: list = None,
        **kwargs
    ):
        if messages is None:
            messages = [{"role": "user", "content": "Hello, AI!"}]
        
        request = {
            "model": model,
            "messages": messages,
            "stream": stream
        }
        
        if temperature is not None:
            request["temperature"] = temperature
        if max_tokens is not None:
            request["max_tokens"] = max_tokens
        if tools is not None:
            request["tools"] = tools
        
        request.update(kwargs)
        return request
    
    return _create_request


@pytest.fixture
def sample_tool_definition():
    """
    Sample tool definition for testing tool calling.
    """
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }
    }


# =============================================================================
# HTTP Client Fixtures
# =============================================================================

@pytest.fixture
async def mock_httpx_client():
    """
    Creates a mocked httpx.AsyncClient for isolation from network requests.
    """
    print("Creating mocked httpx.AsyncClient...")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    
    # Mock methods
    mock_client.post = AsyncMock()
    mock_client.get = AsyncMock()
    mock_client.aclose = AsyncMock()
    mock_client.build_request = Mock()
    mock_client.send = AsyncMock()
    mock_client.is_closed = False
    
    return mock_client


@pytest.fixture
def mock_httpx_response():
    """
    Factory for creating mocked httpx.Response objects.
    """
    def _create_response(
        status_code: int = 200,
        json_data: Dict[str, Any] = None,
        text: str = None,
        stream_chunks: list = None
    ):
        print(f"Creating mock httpx.Response (status={status_code})...")
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.status_code = status_code
        
        if json_data is not None:
            mock_response.json = Mock(return_value=json_data)
        
        if text is not None:
            mock_response.text = text
            mock_response.content = text.encode()
        
        if stream_chunks is not None:
            # For streaming responses
            async def mock_aiter_bytes():
                for chunk in stream_chunks:
                    yield chunk
            
            mock_response.aiter_bytes = mock_aiter_bytes
        
        mock_response.raise_for_status = Mock()
        mock_response.aclose = AsyncMock()
        mock_response.aread = AsyncMock(return_value=b'{"error": "mocked error"}')
        
        return mock_response
    
    return _create_response


# =============================================================================
# Global Network Blocking
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def block_all_network_calls():
    """
    CRITICAL FIXTURE: Globally blocks ALL network calls.
    Ensures that NO test can make a real network request.
    """
    
    # Create a mock that will be used for all AsyncClient instances
    mock_async_client = AsyncMock(spec=httpx.AsyncClient)

    async def network_call_error(*args, **kwargs):
        raise RuntimeError(
            "🚨 CRITICAL ERROR: Real network request attempt detected! "
            "Test did not provide a mock for httpx.AsyncClient. "
            "All HTTP calls must be explicitly mocked."
        )

    mock_async_client.post.side_effect = network_call_error
    mock_async_client.get.side_effect = network_call_error
    mock_async_client.send.side_effect = network_call_error
    
    # Mock context manager
    mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
    mock_async_client.__aexit__ = AsyncMock()
    mock_async_client.aclose = AsyncMock()
    mock_async_client.is_closed = False

    # Patch AsyncClient in modules where it's used
    patchers = [
        patch('kiro.auth.httpx.AsyncClient', return_value=mock_async_client),
        patch('kiro.http_client.httpx.AsyncClient', return_value=mock_async_client),
        patch('kiro.streaming_openai.httpx.AsyncClient', return_value=mock_async_client),
    ]
    
    # Start patchers
    for patcher in patchers:
        patcher.start()
    
    print("🛡️ GLOBAL NETWORK BLOCKING ACTIVATED")
    
    yield

    # Stop patchers
    for patcher in patchers:
        patcher.stop()
    
    print("🛡️ GLOBAL NETWORK BLOCKING DEACTIVATED")


# =============================================================================
# Application Fixtures
# =============================================================================

@pytest.fixture
def clean_app():
    """
    Returns a "clean" application instance for each test.
    """
    print("Importing application for test...")
    from main import app
    # Reset all dependency overrides before test
    app.dependency_overrides = {}
    return app


@pytest.fixture
def test_client(clean_app):
    """
    Creates a FastAPI TestClient for synchronous endpoint tests,
    properly handling lifespan events.
    """
    print("Creating TestClient with lifespan support...")
    with TestClient(clean_app) as client:
        yield client
    print("Closing TestClient...")


@pytest.fixture
async def async_test_client(clean_app):
    """
    Creates an asynchronous test client for async endpoints.
    """
    print("Creating async test client...")
    from httpx import AsyncClient, ASGITransport
    
    transport = ASGITransport(app=clean_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    
    print("Closing async test client...")


# =============================================================================
# KiroAuthManager Fixtures
# =============================================================================

@pytest.fixture
def mock_auth_manager():
    """
    Creates a mocked KiroAuthManager for tests.
    """
    from kiro.auth import KiroAuthManager
    
    manager = KiroAuthManager(
        refresh_token="test_refresh_token",
        profile_arn="arn:aws:codewhisperer:us-east-1:123456789:profile/test",
        region="us-east-1"
    )
    
    # Set valid token
    manager._access_token = "test_access_token"
    manager._expires_at = datetime.now(timezone.utc).replace(
        year=2099  # Far in the future
    )
    
    return manager


@pytest.fixture
def expired_auth_manager():
    """
    Creates a KiroAuthManager with an expired token.
    """
    from kiro.auth import KiroAuthManager
    
    manager = KiroAuthManager(
        refresh_token="test_refresh_token",
        profile_arn="arn:aws:codewhisperer:us-east-1:123456789:profile/test",
        region="us-east-1"
    )
    
    # Set expired token
    manager._access_token = "expired_token"
    manager._expires_at = datetime.now(timezone.utc).replace(
        year=2020  # In the past
    )
    
    return manager


# =============================================================================
# ModelInfoCache Fixtures
# =============================================================================

@pytest.fixture
def sample_models_data():
    """
    Returns a list of models for testing ModelInfoCache.
    """
    return [
        {
            "modelId": "claude-sonnet-4",
            "displayName": "Claude Sonnet 4",
            "tokenLimits": {
                "maxInputTokens": 200000,
                "maxOutputTokens": 8192
            }
        },
        {
            "modelId": "claude-opus-4.5",
            "displayName": "Claude Opus 4.5",
            "tokenLimits": {
                "maxInputTokens": 200000,
                "maxOutputTokens": 8192
            }
        },
        {
            "modelId": "claude-haiku-4.5",
            "displayName": "Claude Haiku 4.5",
            "tokenLimits": {
                "maxInputTokens": 100000,
                "maxOutputTokens": 4096
            }
        }
    ]


@pytest.fixture
def empty_model_cache():
    """
    Creates an empty ModelInfoCache.
    """
    from kiro.cache import ModelInfoCache
    return ModelInfoCache()


@pytest.fixture
async def populated_model_cache(mock_kiro_models_response):
    """
    Creates a ModelInfoCache with pre-populated data.
    """
    from kiro.cache import ModelInfoCache
    
    cache = ModelInfoCache()
    await cache.update(mock_kiro_models_response["models"])
    return cache


# =============================================================================
# Time Fixtures
# =============================================================================

@pytest.fixture
def mock_time():
    """
    Mocks time.time() for predictable behavior in tests.
    """
    with patch('time.time') as mock:
        # Fixed point in time: 2024-01-01 12:00:00
        mock.return_value = 1704110400.0
        yield mock


@pytest.fixture
def mock_datetime():
    """
    Mocks datetime.now() for predictable behavior.
    """
    fixed_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    
    with patch('kiro.auth.datetime') as mock_dt:
        mock_dt.now.return_value = fixed_time
        mock_dt.fromisoformat = datetime.fromisoformat
        mock_dt.fromtimestamp = datetime.fromtimestamp
        yield mock_dt


# =============================================================================
# Temporary File Fixtures
# =============================================================================

@pytest.fixture
def temp_creds_file(tmp_path):
    """
    Creates a temporary credentials file for tests (Kiro Desktop format).
    """
    creds_file = tmp_path / "kiro-auth-token.json"
    creds_data = {
        "accessToken": "file_access_token",
        "refreshToken": "file_refresh_token",
        "expiresAt": "2099-01-01T00:00:00.000Z",
        "profileArn": "arn:aws:codewhisperer:us-east-1:123456789:profile/test",
        "region": "us-east-1"
    }
    creds_file.write_text(json.dumps(creds_data))
    return str(creds_file)


@pytest.fixture
def temp_aws_sso_creds_file(tmp_path):
    """
    Creates a temporary credentials file for tests (AWS SSO OIDC format).
    Contains clientId and clientSecret, indicating AWS SSO OIDC authentication.
    """
    creds_file = tmp_path / "aws-sso-cache.json"
    creds_data = {
        "accessToken": "aws_sso_access_token",
        "refreshToken": "aws_sso_refresh_token",
        "expiresAt": "2099-01-01T00:00:00.000Z",
        "region": "us-east-1",
        "clientId": "test_client_id_12345",
        "clientSecret": "test_client_secret_67890"
    }
    creds_file.write_text(json.dumps(creds_data))
    return str(creds_file)


@pytest.fixture
def temp_sqlite_db(tmp_path):
    """
    Creates a temporary SQLite database for tests (kiro-cli format).
    
    Contains auth_kv table with keys:
    - 'codewhisperer:odic:token': JSON with access_token, refresh_token, expires_at, region
    - 'codewhisperer:odic:device-registration': JSON with client_id, client_secret
    """
    import sqlite3
    
    db_file = tmp_path / "data.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert token data
    token_data = {
        "access_token": "sqlite_access_token",
        "refresh_token": "sqlite_refresh_token",
        "expires_at": "2099-01-01T00:00:00Z",
        "region": "eu-west-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    # Insert device registration data
    registration_data = {
        "client_id": "sqlite_client_id",
        "client_secret": "sqlite_client_secret",
        "region": "eu-west-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:device-registration", json.dumps(registration_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def temp_sqlite_db_token_only(tmp_path):
    """
    Creates a SQLite database with token only (without device-registration).
    Used for testing partial loading.
    """
    import sqlite3
    
    db_file = tmp_path / "data_token_only.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    token_data = {
        "access_token": "partial_access_token",
        "refresh_token": "partial_refresh_token",
        "region": "ap-southeast-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def temp_sqlite_db_invalid_json(tmp_path):
    """
    Creates a SQLite database with invalid JSON in value.
    Used for testing error handling.
    """
    import sqlite3
    
    db_file = tmp_path / "data_invalid.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert invalid JSON
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", "not a valid json {{{")
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def mock_aws_sso_oidc_token_response():
    """
    Factory for creating mock AWS SSO OIDC token endpoint responses.
    """
    def _create_response(
        access_token: str = "new_aws_sso_access_token",
        refresh_token: str = "new_aws_sso_refresh_token",
        expires_in: int = 3600
    ):
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "expiresIn": expires_in,
            "tokenType": "Bearer"
        }
    return _create_response


@pytest.fixture
def temp_debug_dir(tmp_path):
    """
    Creates a temporary directory for debug files.
    """
    debug_dir = tmp_path / "debug_logs"
    debug_dir.mkdir()
    return debug_dir


# =============================================================================
# Parser Fixtures
# =============================================================================

@pytest.fixture
def aws_event_parser():
    """
    Creates an AwsEventStreamParser instance for tests.
    """
    from kiro.parsers import AwsEventStreamParser
    return AwsEventStreamParser()


# =============================================================================
# Test Utilities
# =============================================================================

def create_kiro_content_chunk(content: str) -> bytes:
    """Utility for creating a Kiro SSE chunk with content."""
    return f'{{"content":"{content}"}}'.encode()


def create_kiro_tool_start_chunk(name: str, tool_id: str) -> bytes:
    """Utility for creating a Kiro SSE chunk with tool call start."""
    return f'{{"name":"{name}","toolUseId":"{tool_id}"}}'.encode()


def create_kiro_tool_input_chunk(input_json: str) -> bytes:
    """Utility for creating a Kiro SSE chunk with tool call input."""
    escaped = input_json.replace('"', '\\"')
    return f'{{"input":"{escaped}"}}'.encode()


def create_kiro_tool_stop_chunk() -> bytes:
    """Utility for creating a Kiro SSE chunk with tool call stop."""
    return b'{"stop":true}'


def create_kiro_usage_chunk(usage: float) -> bytes:
    """Utility for creating a Kiro SSE chunk with usage."""
    return f'{{"usage":{usage}}}'.encode()


def create_kiro_context_usage_chunk(percentage: float) -> bytes:
    """Utility for creating a Kiro SSE chunk with context usage."""
    return f'{{"contextUsagePercentage":{percentage}}}'.encode()


# =============================================================================
# Social Login Fixtures (for new functionality)
# =============================================================================

@pytest.fixture
def temp_sqlite_db_social(tmp_path):
    """
    Creates a temporary SQLite database with social login credentials.
    
    Contains auth_kv table with key:
    - 'kirocli:social:token': JSON with access_token, refresh_token, expires_at, provider
    
    This simulates kiro-cli with Google/GitHub social login (no client_id/client_secret).
    """
    import sqlite3
    
    db_file = tmp_path / "data_social.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert social login token data
    token_data = {
        "access_token": "social_access_token",
        "refresh_token": "social_refresh_token",
        "expires_at": "2099-01-01T00:00:00Z",
        "provider": "google",
        "profile_arn": "arn:aws:codewhisperer:us-east-1:123456789:profile/social",
        "region": "us-east-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("kirocli:social:token", json.dumps(token_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def temp_sqlite_db_all_keys(tmp_path):
    """
    Creates a SQLite database with ALL three token keys.
    
    Used for testing key priority:
    1. kirocli:social:token (highest priority)
    2. kirocli:odic:token
    3. codewhisperer:odic:token (lowest priority)
    """
    import sqlite3
    
    db_file = tmp_path / "data_all_keys.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert all three keys with different tokens
    social_data = {
        "access_token": "social_token",
        "refresh_token": "social_refresh",
        "expires_at": "2099-01-01T00:00:00Z",
        "provider": "google"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("kirocli:social:token", json.dumps(social_data))
    )
    
    odic_data = {
        "access_token": "odic_token",
        "refresh_token": "odic_refresh",
        "expires_at": "2099-01-01T00:00:00Z"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("kirocli:odic:token", json.dumps(odic_data))
    )
    
    legacy_data = {
        "access_token": "legacy_token",
        "refresh_token": "legacy_refresh",
        "expires_at": "2099-01-01T00:00:00Z"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(legacy_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


# =============================================================================
# Enterprise Kiro IDE Fixtures (Issue #45)
# =============================================================================

@pytest.fixture
def temp_enterprise_ide_creds_file(tmp_path):
    """
    Creates a temporary credentials file for Enterprise Kiro IDE.
    
    Contains:
    - clientIdHash: Hash used to locate device registration file
    - refreshToken, accessToken, expiresAt, region
    
    This simulates Enterprise Kiro IDE with IdC (AWS IAM Identity Center) login.
    """
    creds_file = tmp_path / "kiro-auth-token.json"
    creds_data = {
        "accessToken": "enterprise_access_token",
        "refreshToken": "enterprise_refresh_token",
        "expiresAt": "2099-01-01T00:00:00.000Z",
        "profileArn": "arn:aws:codewhisperer:us-east-1:123456789:profile/enterprise",
        "region": "us-east-1",
        "clientIdHash": "abc123def456"
    }
    creds_file.write_text(json.dumps(creds_data))
    return str(creds_file)


@pytest.fixture
def temp_enterprise_device_registration(tmp_path):
    """
    Creates a temporary device registration file for Enterprise Kiro IDE.
    
    Located at: ~/.aws/sso/cache/{clientIdHash}.json
    Contains: clientId, clientSecret
    """
    # Create .aws/sso/cache directory structure
    aws_dir = tmp_path / ".aws" / "sso" / "cache"
    aws_dir.mkdir(parents=True, exist_ok=True)
    
    # Create device registration file
    device_reg_file = aws_dir / "abc123def456.json"
    device_reg_data = {
        "clientId": "enterprise_client_id_12345",
        "clientSecret": "enterprise_client_secret_67890",
        "region": "us-east-1"
    }
    device_reg_file.write_text(json.dumps(device_reg_data))
    
    return str(device_reg_file)


@pytest.fixture
def temp_enterprise_ide_complete(tmp_path, monkeypatch):
    """
    Creates a complete Enterprise IDE setup with both credentials and device registration.
    
    Returns tuple: (creds_file_path, device_reg_file_path)
    """
    # Mock Path.home() to return tmp_path
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path)
    
    # Create credentials file
    creds_file = tmp_path / "kiro-auth-token.json"
    creds_data = {
        "accessToken": "enterprise_access_token",
        "refreshToken": "enterprise_refresh_token",
        "expiresAt": "2099-01-01T00:00:00.000Z",
        "profileArn": "arn:aws:codewhisperer:us-east-1:123456789:profile/enterprise",
        "region": "us-east-1",
        "clientIdHash": "abc123def456"
    }
    creds_file.write_text(json.dumps(creds_data))
    
    # Create device registration file
    aws_dir = tmp_path / ".aws" / "sso" / "cache"
    aws_dir.mkdir(parents=True, exist_ok=True)
    
    device_reg_file = aws_dir / "abc123def456.json"
    device_reg_data = {
        "clientId": "enterprise_client_id_12345",
        "clientSecret": "enterprise_client_secret_67890",
        "region": "us-east-1"
    }
    device_reg_file.write_text(json.dumps(device_reg_data))
    
    return (str(creds_file), str(device_reg_file))


# =============================================================================
# API Region Auto-Detection Fixtures
# =============================================================================

@pytest.fixture
def temp_sqlite_db_with_profile_arn(tmp_path):
    """
    Creates SQLite database with state table containing profile ARN.
    
    Tables:
    - auth_kv: token data with SSO region=eu-west-1
    - state: profile ARN with API region=eu-central-1
    
    This simulates kiro-cli with profile ARN that has different API region.
    """
    import sqlite3
    
    db_file = tmp_path / "data_with_arn.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert token data with SSO region
    token_data = {
        "access_token": "arn_access_token",
        "refresh_token": "arn_refresh_token",
        "expires_at": "2099-01-01T00:00:00Z",
        "region": "eu-west-1"  # SSO region
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    # Insert device registration
    registration_data = {
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
        "region": "eu-west-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:device-registration", json.dumps(registration_data))
    )
    
    # Create state table with profile ARN
    cursor.execute("""
        CREATE TABLE state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert profile with ARN containing different API region
    profile_data = {
        "arn": "arn:aws:codewhisperer:eu-central-1:123456789012:profile/test-profile",
        "name": "test-profile"
    }
    cursor.execute(
        "INSERT INTO state (key, value) VALUES (?, ?)",
        ("api.codewhisperer.profile", json.dumps(profile_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def temp_sqlite_db_with_empty_state_table(tmp_path):
    """
    Creates SQLite database with empty state table (no profile key).
    
    Used for testing fallback behavior when state table exists but has no profile.
    """
    import sqlite3
    
    db_file = tmp_path / "data_empty_state.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert token data
    token_data = {
        "access_token": "empty_state_access",
        "refresh_token": "empty_state_refresh",
        "expires_at": "2099-01-01T00:00:00Z",
        "region": "us-west-2"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    # Create empty state table
    cursor.execute("""
        CREATE TABLE state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture(params=[
    "not-an-arn",
    "arn:aws:codewhisperer",
    "arn:aws:codewhisperer:INVALID_REGION:account:profile",
    "arn:aws:codewhisperer::account:profile",
])
def temp_sqlite_db_with_invalid_arn(tmp_path, request):
    """
    Creates SQLite database with invalid ARN formats.
    
    Parametrized fixture that tests various invalid ARN formats:
    - Not an ARN at all
    - Too short ARN
    - Invalid region format
    - Empty region
    """
    import sqlite3
    
    db_file = tmp_path / f"data_invalid_arn_{request.param_index}.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert token data
    token_data = {
        "access_token": "invalid_arn_access",
        "refresh_token": "invalid_arn_refresh",
        "expires_at": "2099-01-01T00:00:00Z",
        "region": "ap-southeast-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    # Create state table with invalid ARN
    cursor.execute("""
        CREATE TABLE state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    profile_data = {
        "arn": request.param,  # Invalid ARN from parametrize
        "name": "test-profile"
    }
    cursor.execute(
        "INSERT INTO state (key, value) VALUES (?, ?)",
        ("api.codewhisperer.profile", json.dumps(profile_data))
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)


@pytest.fixture
def temp_sqlite_db_with_malformed_state_json(tmp_path):
    """
    Creates SQLite database with malformed JSON in state table.
    
    Used for testing graceful error handling when state table contains invalid JSON.
    """
    import sqlite3
    
    db_file = tmp_path / "data_malformed_state.sqlite3"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # Create auth_kv table
    cursor.execute("""
        CREATE TABLE auth_kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert token data
    token_data = {
        "access_token": "malformed_state_access",
        "refresh_token": "malformed_state_refresh",
        "expires_at": "2099-01-01T00:00:00Z",
        "region": "ap-south-1"
    }
    cursor.execute(
        "INSERT INTO auth_kv (key, value) VALUES (?, ?)",
        ("codewhisperer:odic:token", json.dumps(token_data))
    )
    
    # Create state table with malformed JSON
    cursor.execute("""
        CREATE TABLE state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Insert malformed JSON
    cursor.execute(
        "INSERT INTO state (key, value) VALUES (?, ?)",
        ("api.codewhisperer.profile", "not a valid json {{{")
    )
    
    conn.commit()
    conn.close()
    
    return str(db_file)
