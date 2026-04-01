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
Kiro Gateway - Proxy for Kiro API.

This package provides a modular architecture for proxying
OpenAI API requests to Kiro (AWS CodeWhisperer).

Modules:
    - config: Configuration and constants
    - models: Pydantic models for OpenAI API
    - auth: Kiro authentication manager
    - cache: Model metadata cache
    - utils: Helper utilities
    - converters: OpenAI <-> Kiro format conversion
    - parsers: AWS SSE stream parsers
    - streaming: Response streaming logic
    - http_client: HTTP client with retry logic
    - routes: FastAPI routes
    - exceptions: Exception handlers
"""

# Version is imported from config.py — the single source of truth
# This allows changing the version in only one place
from kiro.config import APP_VERSION as __version__

__author__ = "Jwadow"

# Main components for convenient import
from kiro.auth import KiroAuthManager
from kiro.cache import ModelInfoCache
from kiro.http_client import KiroHttpClient
from kiro.routes_openai import router
from kiro.model_resolver import ModelResolver, normalize_model_name, get_model_id_for_kiro

# Configuration
from kiro.config import (
    PROXY_API_KEY,
    REGION,
    API_REGION,
    HIDDEN_MODELS,
    APP_VERSION,
)

# Models
from kiro.models_openai import (
    ChatCompletionRequest,
    ChatMessage,
    OpenAIModel,
    ModelList,
)

# Converters
from kiro.converters_openai import build_kiro_payload
from kiro.converters_core import (
    extract_text_content,
    merge_adjacent_messages,
)

# Parsers
from kiro.parsers import (
    AwsEventStreamParser,
    parse_bracket_tool_calls,
)

# Streaming
from kiro.streaming_openai import (
    stream_kiro_to_openai,
    collect_stream_response,
)

# Exceptions
from kiro.exceptions import (
    validation_exception_handler,
    sanitize_validation_errors,
)

__all__ = [
    # Version
    "__version__",
    
    # Main classes
    "KiroAuthManager",
    "ModelInfoCache",
    "KiroHttpClient",
    "ModelResolver",
    "router",
    
    # Configuration
    "PROXY_API_KEY",
    "REGION",
    "API_REGION",
    "HIDDEN_MODELS",
    "APP_VERSION",
    
    # Model resolution
    "normalize_model_name",
    "get_model_id_for_kiro",
    
    # Models
    "ChatCompletionRequest",
    "ChatMessage",
    "OpenAIModel",
    "ModelList",
    
    # Converters
    "build_kiro_payload",
    "extract_text_content",
    "merge_adjacent_messages",
    
    # Parsers
    "AwsEventStreamParser",
    "parse_bracket_tool_calls",
    
    # Streaming
    "stream_kiro_to_openai",
    "collect_stream_response",
    
    # Exceptions
    "validation_exception_handler",
    "sanitize_validation_errors",
]