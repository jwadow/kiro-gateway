# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Kiro Gateway Configuration.

Centralized storage for all settings, constants, and mappings.
Loads environment variables and provides typed access to them.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _get_raw_env_value(var_name: str, env_file: str = ".env") -> Optional[str]:
    """
    Read variable value from .env file without processing escape sequences.
    
    This is necessary for correct handling of Windows paths where backslashes
    (e.g., D:\\Projects\\file.json) may be incorrectly interpreted
    as escape sequences (\\a -> bell, \\n -> newline, etc.).
    
    Args:
        var_name: Environment variable name
        env_file: Path to .env file (default ".env")
    
    Returns:
        Raw variable value or None if not found
    """
    env_path = Path(env_file)
    if not env_path.exists():
        return None
    
    try:
        # Read file as-is, without interpretation
        content = env_path.read_text(encoding="utf-8")
        
        # Search for variable considering different formats:
        # VAR="value" or VAR='value' or VAR=value
        # Pattern captures value with or without quotes
        pattern = rf'^{re.escape(var_name)}=(["\']?)(.+?)\1\s*$'
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            
            match = re.match(pattern, line)
            if match:
                # Return value as-is, without processing escape sequences
                return match.group(2)
    except Exception:
        pass
    
    return None

# ==================================================================================================
# Server Settings
# ==================================================================================================

# Server host (default: 0.0.0.0 - listen on all interfaces)
# Use "127.0.0.1" to only allow local connections
DEFAULT_SERVER_HOST: str = "0.0.0.0"
SERVER_HOST: str = os.getenv("SERVER_HOST", DEFAULT_SERVER_HOST)

# Server port (default: 8000)
# Can be overridden by CLI: python main.py --port 9000
# Or by uvicorn directly: uvicorn main:app --port 9000
DEFAULT_SERVER_PORT: int = 8000
SERVER_PORT: int = int(os.getenv("SERVER_PORT", str(DEFAULT_SERVER_PORT)))

# ==================================================================================================
# Proxy Server Settings
# ==================================================================================================

# API key for proxy access (clients must pass it in Authorization header)
PROXY_API_KEY: str = os.getenv("PROXY_API_KEY", "my-super-secret-password-123")

# ==================================================================================================
# VPN/Proxy Settings for Kiro API Access
# ==================================================================================================

# VPN/Proxy URL for accessing Kiro API through a proxy server.
# Leave empty to connect directly (default).
#
# Use cases:
#   - China: GFW (Great Firewall) blocks AWS endpoints
#   - Corporate networks: Often require mandatory proxy
#   - Privacy: Hide your IP address from AWS
#
# Supports HTTP and SOCKS5 protocols.
# Authentication can be embedded in the URL.
#
# Examples:
#   VPN_PROXY_URL=http://127.0.0.1:7890
#   VPN_PROXY_URL=socks5://127.0.0.1:1080
#   VPN_PROXY_URL=http://user:password@proxy.company.com:8080
#   VPN_PROXY_URL=192.168.1.100:8080  (defaults to http://)
VPN_PROXY_URL: str = os.getenv("VPN_PROXY_URL", "")

# ==================================================================================================
# Kiro API Credentials
# ==================================================================================================

# Refresh token for updating access token
REFRESH_TOKEN: str = os.getenv("REFRESH_TOKEN", "")

# Profile ARN for AWS CodeWhisperer
PROFILE_ARN: str = os.getenv("PROFILE_ARN", "")

# AWS SSO/auth region (default us-east-1)
# This region is used for OIDC token refresh endpoint: https://oidc.{region}.amazonaws.com/token
#
# IMPORTANT: SSO region may differ from Q API region!
# - SSO region: Where your AWS SSO/IAM Identity Center is configured
# - API region: Where Q Developer API endpoints are available (q.{region}.amazonaws.com)
#
# The gateway automatically detects the correct API region from your credentials:
# - SQLite (kiro-cli): Extracts from profile ARN in state table
# - JSON (Kiro IDE): Uses region field from credentials file
# - Environment variables: Falls back to this SSO region
#
# For manual override of API region, use KIRO_API_REGION environment variable.
# See: https://github.com/jwadow/kiro-gateway/issues/132
REGION: str = os.getenv("KIRO_REGION", "us-east-1")

# Path to credentials file (optional, alternative to .env)
# Read directly from .env to avoid escape sequence issues on Windows
# (e.g., \a in path D:\Projects\adolf is interpreted as bell character)
_raw_creds_file = _get_raw_env_value("KIRO_CREDS_FILE") or os.getenv("KIRO_CREDS_FILE", "")
# Normalize path for cross-platform compatibility
KIRO_CREDS_FILE: str = str(Path(_raw_creds_file)) if _raw_creds_file else ""

# Path to kiro-cli SQLite database (optional, for AWS SSO OIDC authentication)
# Default location: ~/.local/share/kiro-cli/data.sqlite3 (Linux/macOS)
# or ~/.local/share/amazon-q/data.sqlite3 (amazon-q-developer-cli)
_raw_cli_db_file = _get_raw_env_value("KIRO_CLI_DB_FILE") or os.getenv("KIRO_CLI_DB_FILE", "")
KIRO_CLI_DB_FILE: str = str(Path(_raw_cli_db_file)) if _raw_cli_db_file else ""

# Disable SQLite write-back (read-only mode)
# When enabled, gateway will only read from kiro-cli database without modifying it.
# Useful when kiro-cli is actively managing tokens and you don't want gateway to interfere.
# Default: false (write-back enabled)
SQLITE_READONLY: bool = os.getenv("SQLITE_READONLY", "false").lower() in ("true", "1", "yes")

# ==================================================================================================
# Kiro API URL Templates
# ==================================================================================================

# URL for token refresh (Kiro Desktop Auth)
KIRO_REFRESH_URL_TEMPLATE: str = "https://prod.{region}.auth.desktop.kiro.dev/refreshToken"

# URL for token refresh (AWS SSO OIDC - used by kiro-cli)
AWS_SSO_OIDC_URL_TEMPLATE: str = "https://oidc.{region}.amazonaws.com/token"

# Host for main API (generateAssistantResponse)
# Universal endpoint for all regions (us-east-1, eu-central-1, etc.)
# See: https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/security-data-perimeter.html
# Fixed in issue #58 - codewhisperer.{region}.amazonaws.com doesn't exist for non-us-east-1 regions
KIRO_API_HOST_TEMPLATE: str = "https://q.{region}.amazonaws.com"

# Host for Q API (ListAvailableModels)
KIRO_Q_HOST_TEMPLATE: str = "https://q.{region}.amazonaws.com"

# ==================================================================================================
# Token Settings
# ==================================================================================================

# Time before token expiration when refresh is needed (in seconds)
# Default 10 minutes - refresh token in advance to avoid errors
TOKEN_REFRESH_THRESHOLD: int = 600

# ==================================================================================================
# Retry Configuration
# ==================================================================================================

# Maximum number of retry attempts on errors
MAX_RETRIES: int = 3

# Base delay between attempts (seconds)
# Uses exponential backoff: delay * (2 ** attempt)
BASE_RETRY_DELAY: float = 1.0

# ==================================================================================================
# Hidden Models Configuration
# ==================================================================================================

# Hidden models - not returned by Kiro /ListAvailableModels API but still functional.
# These ARE shown in our /v1/models endpoint!
# Use dot format for consistency with API models.
#
# Format: "display_name" → "internal_kiro_id"
# Display names use dots (e.g., "claude-3.7-sonnet") for consistency with Kiro API.
#
# Why "hidden"? These models work but are not advertised by Kiro's /ListAvailableModels.
# We expose them to our users because they're useful.
HIDDEN_MODELS: Dict[str, str] = {
    # Claude 3.7 Sonnet - legacy flagship model, still works!
    # Hidden in Kiro API but functional. Great for users who prefer it.
    "claude-3.7-sonnet": "CLAUDE_3_7_SONNET_20250219_V1_0",
    
    # Add other hidden/experimental models here as discovered.
    # Example: "claude-secret-model": "INTERNAL_SECRET_MODEL_ID",
}

# ==================================================================================================
# Model Aliases Configuration
# ==================================================================================================

# Model aliases - custom names that map to real model IDs.
# This feature allows creating alternative names for models to avoid namespace conflicts
# with IDE-specific model names (e.g., Cursor's "auto" model).
#
# Format: {"alias_name": "real_model_id"}
# - alias_name: The name that will appear in /v1/models and can be used in requests
# - real_model_id: The actual model ID that will be sent to Kiro API
#
# Use cases:
# - Avoid conflicts with IDE-specific model names (e.g., Cursor's "auto")
# - Create user-friendly shortcuts (e.g., "my-opus" → "claude-opus-4.5")
# - Support legacy model names from other providers
#
# Example:
#   MODEL_ALIASES = {
#       "auto-kiro": "auto",
#       "my-opus": "claude-opus-4.5",
#       "gpt-5": "claude-sonnet-4.5"
#   }
#
# Default: {"auto-kiro": "auto"} to avoid Cursor IDE conflict
MODEL_ALIASES: Dict[str, str] = {
    "auto-kiro": "auto",  # Default alias to avoid Cursor's "auto" model conflict
}

# Models to hide from /v1/models endpoint.
# These models still work when requested directly, but are not shown in the model list.
# This is useful when you want to show only aliases instead of original model names.
#
# Use case: Hide "auto" from list to show only "auto-kiro" alias, avoiding confusion.
#
# Example:
#   HIDDEN_FROM_LIST = ["auto", "claude-old-model"]
#
# Default: ["auto"] to show only "auto-kiro" alias
HIDDEN_FROM_LIST: List[str] = ["auto"]

# ==================================================================================================
# Fallback Models Configuration (DNS Failure Recovery)
# ==================================================================================================

# Fallback model list - used when /ListAvailableModels API is unreachable.
# This ensures basic functionality even with DNS/network issues.
#
# IMPORTANT: This list represents known models at the time of this gateway version.
# - Some models may not be available on your Kiro plan (e.g., Opus on free tier)
# - New models released after this version won't appear here
# - Update gateway regularly to get the latest model list
FALLBACK_MODELS: List[Dict[str, str]] = [
    {"modelId": "auto"},
    {"modelId": "claude-sonnet-4"},
    {"modelId": "claude-haiku-4.5"},
    {"modelId": "claude-sonnet-4.5"},
    {"modelId": "claude-opus-4.5"},
]

# ==================================================================================================
# Model Cache Settings
# ==================================================================================================

# Model cache TTL in seconds (1 hour)
MODEL_CACHE_TTL: int = 3600

# Default maximum number of input tokens
DEFAULT_MAX_INPUT_TOKENS: int = 200000

# ==================================================================================================
# Tool Description Handling (Kiro API Limitations)
# ==================================================================================================

# Kiro API returns 400 "Improperly formed request" error when tool descriptions
# in toolSpecification.description are too long.
#
# Solution: Tool Documentation Reference Pattern
# - If description ≤ limit → keep as is
# - If description > limit:
#   * In toolSpecification.description → reference to system prompt:
#     "[Full documentation in system prompt under '## Tool: {name}']"
#   * In system prompt, a section "## Tool: {name}" with full description is added
#
# The model sees an explicit reference and knows exactly where to find full documentation.

# Maximum length of tool description in characters.
# Descriptions longer than this limit will be moved to system prompt.
# Set to 0 to disable (not recommended - will cause Kiro API errors).
TOOL_DESCRIPTION_MAX_LENGTH: int = int(os.getenv("TOOL_DESCRIPTION_MAX_LENGTH", "10000"))

# ==================================================================================================
# Truncation Recovery Settings
# ==================================================================================================

# Enable automatic truncation recovery (synthetic message injection)
# When enabled, gateway will inject synthetic messages ONLY when truncation is detected:
# - For tool calls: synthetic tool_result with error message
# - For content: synthetic user message notifying about truncation
# This helps the model understand and adapt to Kiro API limitations
# Default: true (enabled)
TRUNCATION_RECOVERY: bool = os.getenv("TRUNCATION_RECOVERY", "true").lower() in ("true", "1", "yes")

# ==================================================================================================
# Logging Settings
# ==================================================================================================

# Log level for the application
# Available levels: TRACE, DEBUG, INFO, WARNING, ERROR, CRITICAL
# Default: INFO (recommended for production)
# Set to DEBUG for detailed troubleshooting
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ==================================================================================================
# First Token Timeout Settings (Streaming Retry)
# ==================================================================================================

# Timeout for waiting for the first token from the model (in seconds).
# If the model doesn't respond within this time, the request will be cancelled and retried.
# This helps handle "stuck" requests when the model takes too long to think.
# Default: 30 seconds (recommended for production)
# Set a lower value (e.g., 10-15) for more aggressive retry.
FIRST_TOKEN_TIMEOUT: float = float(os.getenv("FIRST_TOKEN_TIMEOUT", "15"))

# Read timeout for streaming responses (in seconds).
# This is the maximum time to wait for data between chunks during streaming.
# Should be longer than FIRST_TOKEN_TIMEOUT since the model may pause between chunks
# while "thinking" (especially for tool calls or complex reasoning).
# Default: 300 seconds (5 minutes) - generous timeout to avoid premature disconnects.
STREAMING_READ_TIMEOUT: float = float(os.getenv("STREAMING_READ_TIMEOUT", "300"))

# Maximum number of attempts on first token timeout.
# After exhausting all attempts, an error will be returned.
# Default: 3 attempts
FIRST_TOKEN_MAX_RETRIES: int = int(os.getenv("FIRST_TOKEN_MAX_RETRIES", "3"))

# Inactivity timeout for streaming responses (in seconds).
# This is an APPLICATION-LEVEL timeout that tracks time since the last meaningful
# SSE chunk was received from the upstream provider. Unlike STREAMING_READ_TIMEOUT
# (which is an httpx-level TCP read timeout that resets on any bytes including
# TCP keepalives), this timeout only resets when actual data chunks arrive.
#
# This prevents the gateway from hanging indefinitely when the upstream provider
# accepts the connection and keeps it alive but stops sending data.
# Default: 300 seconds (5 minutes)
STREAMING_INACTIVITY_TIMEOUT: float = float(os.getenv("STREAMING_INACTIVITY_TIMEOUT", "300"))

# Timeout for receiving HTTP response headers from upstream (in seconds).
# This is a wall-clock timeout on the initial request phase — from sending the
# request to receiving the first byte of the HTTP response (status + headers).
# Once headers arrive and streaming begins, this timeout no longer applies.
#
# Prevents the gateway from hanging when the upstream accepts the TCP connection
# but never sends an HTTP response. Normal responses return headers in <5s;
# 120s is generous enough for slow starts while catching dead connections.
# Default: 120 seconds (2 minutes)
RESPONSE_HEADERS_TIMEOUT: float = float(os.getenv("RESPONSE_HEADERS_TIMEOUT", "120"))

# Interval for logging long-running streaming requests (in seconds).
# When a streaming request is in progress, a periodic log line is emitted
# so operators can see that the gateway is still waiting for data.
# Default: 60 seconds
STREAMING_LOG_INTERVAL: float = float(os.getenv("STREAMING_LOG_INTERVAL", "60"))

# ==================================================================================================
# Debug Settings
# ==================================================================================================

# Debug logging mode:
# - off: disabled (default)
# - errors: save logs only for failed requests (4xx, 5xx)
# - all: save logs for every request (overwrites on each request)
_DEBUG_MODE_RAW: str = os.getenv("DEBUG_MODE", "").lower()

if _DEBUG_MODE_RAW in ("off", "errors", "all"):
    DEBUG_MODE: str = _DEBUG_MODE_RAW
else:
    DEBUG_MODE: str = "off"

# Directory for debug log files
DEBUG_DIR: str = os.getenv("DEBUG_DIR", "debug_logs")


def _warn_timeout_configuration():
    """
    Print warning if timeout configuration is suboptimal.
    Called at application startup.
    
    FIRST_TOKEN_TIMEOUT should be less than STREAMING_READ_TIMEOUT:
    - FIRST_TOKEN_TIMEOUT: time to wait for model to START responding
    - STREAMING_READ_TIMEOUT: time to wait BETWEEN chunks during streaming
    """
    if FIRST_TOKEN_TIMEOUT >= STREAMING_READ_TIMEOUT:
        import sys
        YELLOW = "\033[93m"
        RESET = "\033[0m"
        
        warning_text = f"""
{YELLOW}⚠️  WARNING: Suboptimal timeout configuration detected.
    
    FIRST_TOKEN_TIMEOUT ({FIRST_TOKEN_TIMEOUT}s) >= STREAMING_READ_TIMEOUT ({STREAMING_READ_TIMEOUT}s)
    
    These timeouts serve different purposes:
      - FIRST_TOKEN_TIMEOUT: time to wait for model to START responding (default: 15s)
      - STREAMING_READ_TIMEOUT: time to wait BETWEEN chunks during streaming (default: 300s)
    
    Recommendation: FIRST_TOKEN_TIMEOUT should be LESS than STREAMING_READ_TIMEOUT.
    
    Example configuration:
      FIRST_TOKEN_TIMEOUT=15
      STREAMING_READ_TIMEOUT=300{RESET}
"""
        print(warning_text, file=sys.stderr)

# ==================================================================================================
# Fake Reasoning Settings (Extended Thinking via Tag Injection)
# ==================================================================================================

# Enable fake reasoning - injects special tags into requests to enable model reasoning.
# When enabled, the model will include its reasoning process in the response wrapped in tags.
# The response is then parsed and converted to OpenAI-compatible reasoning_content format.
#
# WHY "FAKE"? This is NOT native extended thinking API support. Instead, we inject
# <thinking_mode>enabled</thinking_mode> tags into the prompt, and the model responds
# with <thinking>...</thinking> blocks that we parse and convert to reasoning_content.
# It works great, but it's a hack - hence "fake" reasoning.
#
# Default: true (enabled) - provides premium experience out of the box
_FAKE_REASONING_RAW: str = os.getenv("FAKE_REASONING", "").lower()
# Default is True - if env var is not set or empty, enable fake reasoning
FAKE_REASONING_ENABLED: bool = _FAKE_REASONING_RAW not in ("false", "0", "no", "disabled", "off")

# Maximum thinking length in tokens (default budget when client doesn't specify).
# This value is injected into the request as <max_thinking_length>{value}</max_thinking_length>
# Higher values allow for more detailed reasoning but increase response time and token usage.
# Default: 4000 tokens
FAKE_REASONING_MAX_TOKENS: int = int(os.getenv("FAKE_REASONING_MAX_TOKENS", "4000"))

# Maximum budget cap for fake reasoning when client sends thinking budget.
#
# WHY CAP? Fake reasoning uses output tokens (not separate thinking tokens like native API).
# Large budgets can cause the model to spend ALL output tokens on reasoning with NOTHING
# left for actual content. This cap prevents that.
#
# Default: 10000 tokens (2.5x default budget of 4000)
# - Allows deeper reasoning than default
# - Prevents excessive token consumption
# - Still leaves room for actual response
#
# Set to 0 to disable capping (not recommended for production).
FAKE_REASONING_BUDGET_CAP: int = int(os.getenv("FAKE_REASONING_BUDGET_CAP", "10000"))

# How to handle the thinking block in responses:
# - "as_reasoning_content": Extract to reasoning_content field (OpenAI-compatible, recommended)
# - "remove": Remove thinking block completely, return only final answer
# - "pass": Pass through as-is with original tags in content
# - "strip_tags": Remove tags but keep thinking content in regular content
#
# Default: "as_reasoning_content"
_FAKE_REASONING_HANDLING_RAW: str = os.getenv("FAKE_REASONING_HANDLING", "as_reasoning_content").lower()
if _FAKE_REASONING_HANDLING_RAW in ("as_reasoning_content", "remove", "pass", "strip_tags"):
    FAKE_REASONING_HANDLING: str = _FAKE_REASONING_HANDLING_RAW
else:
    FAKE_REASONING_HANDLING: str = "as_reasoning_content"

# List of opening tags to detect thinking blocks.
# The parser will look for any of these tags at the start of the response.
# Order matters - first match wins.
FAKE_REASONING_OPEN_TAGS: List[str] = ["<thinking>", "<think>", "<reasoning>", "<thought>"]

# Maximum size of initial buffer for tag detection (characters).
# If no thinking tag is found within this limit, content is treated as regular response.
# Lower values = faster first token, but may miss tags with leading whitespace.
# Default: 30 characters (enough for longest tag + some whitespace)
FAKE_REASONING_INITIAL_BUFFER_SIZE: int = int(os.getenv("FAKE_REASONING_INITIAL_BUFFER_SIZE", "20"))


# ==================================================================================================
# Payload Size Guard Settings
# ==================================================================================================

# Payload size limit in bytes (Kiro API rejects > ~615KB with cryptic 400 error)
# Default 600KB provides safety margin below the ~615KB hard limit
KIRO_MAX_PAYLOAD_BYTES: int = int(os.getenv("KIRO_MAX_PAYLOAD_BYTES", "600000"))

# Auto-trim payload when over limit (default: false - disabled)
# Enable this if you use many tools (30+) and hit "Improperly formed request" errors
# When false, returns a clear error instead of trimming
AUTO_TRIM_PAYLOAD: bool = os.getenv("AUTO_TRIM_PAYLOAD", "false").lower() in ("true", "1", "yes")

# ==================================================================================================
# WebSearch Settings (MCP Tool Emulation)
# ==================================================================================================

# Enable web_search tool auto-injection (default: true)
# When enabled, web_search is automatically added as a tool for MCP emulation (Path B)
# Model decides whether to use it or not
#
# Note: Native Anthropic server-side tools (Path A) work ALWAYS, regardless of this setting
WEB_SEARCH_ENABLED: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in ("true", "1", "yes")

# ==================================================================================================
# Application Version
# ==================================================================================================

APP_VERSION: str = "2.4-dev.7"
APP_TITLE: str = "Kiro Gateway"
APP_DESCRIPTION: str = "Proxy gateway for Kiro API (Amazon Q Developer / AWS CodeWhisperer). OpenAI and Anthropic compatible. Made by @jwadow"


def get_kiro_refresh_url(region: str) -> str:
    """Return Kiro Desktop Auth token refresh URL for the specified region."""
    return KIRO_REFRESH_URL_TEMPLATE.format(region=region)


def get_aws_sso_oidc_url(region: str) -> str:
    """Return AWS SSO OIDC token URL for the specified region."""
    return AWS_SSO_OIDC_URL_TEMPLATE.format(region=region)


def get_kiro_api_host(region: str) -> str:
    """Return API host for the specified region."""
    return KIRO_API_HOST_TEMPLATE.format(region=region)


def get_kiro_q_host(region: str) -> str:
    """Return Q API host for the specified region."""
    return KIRO_Q_HOST_TEMPLATE.format(region=region)

