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
Kiro Gateway - OpenAI-compatible interface for Kiro API.

Application entry point. Creates FastAPI app and connects routes.

Usage:
    # Using default settings (host: 0.0.0.0, port: 8000)
    python main.py
    
    # With CLI arguments (highest priority)
    python main.py --port 9000
    python main.py --host 127.0.0.1 --port 9000
    
    # With environment variables (medium priority)
    SERVER_PORT=9000 python main.py
    
    # Using uvicorn directly (uvicorn handles its own CLI args)
    uvicorn main:app --host 0.0.0.0 --port 8000

Priority: CLI args > Environment variables > Default values
"""

import argparse
import logging
import sys
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from kiro.config import (
    APP_TITLE,
    APP_DESCRIPTION,
    APP_VERSION,
    REFRESH_TOKEN,
    PROFILE_ARN,
    REGION,
    API_REGION,
    KIRO_CREDS_FILE,
    KIRO_CLI_DB_FILE,
    PROXY_API_KEY,
    LOG_LEVEL,
    SERVER_HOST,
    SERVER_PORT,
    DEFAULT_SERVER_HOST,
    DEFAULT_SERVER_PORT,
    STREAMING_READ_TIMEOUT,
    HIDDEN_MODELS,
    MODEL_ALIASES,
    HIDDEN_FROM_LIST,
    FALLBACK_MODELS,
    VPN_PROXY_URL,
    _warn_timeout_configuration,
)
from kiro.auth import KiroAuthManager
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver
from kiro.routes_openai import router as openai_router
from kiro.routes_anthropic import router as anthropic_router
from kiro.exceptions import validation_exception_handler
from kiro.debug_middleware import DebugLoggerMiddleware


# --- Loguru Configuration ---
logger.remove()
logger.add(
    sys.stderr,
    level=LOG_LEVEL,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """
    Intercepts logs from standard logging and redirects them to loguru.
    
    This allows capturing logs from uvicorn, FastAPI and other libraries
    that use standard logging instead of loguru.
    
    Also filters out noisy shutdown-related exceptions (CancelledError, KeyboardInterrupt)
    that are normal during Ctrl+C but uvicorn logs as ERROR.
    """
    
    # Exceptions that are normal during shutdown and should not be logged as errors
    SHUTDOWN_EXCEPTIONS = (
        "CancelledError",
        "KeyboardInterrupt",
        "asyncio.exceptions.CancelledError",
    )
    
    def emit(self, record: logging.LogRecord) -> None:
        # Filter out shutdown-related exceptions that uvicorn logs as ERROR
        # These are normal during Ctrl+C and don't need to spam the console
        if record.exc_info:
            exc_type = record.exc_info[0]
            if exc_type is not None:
                exc_name = exc_type.__name__
                if exc_name in self.SHUTDOWN_EXCEPTIONS:
                    # Suppress the full traceback, just log a simple message
                    logger.info("Server shutdown in progress...")
                    return
        
        # Also filter by message content for cases where exc_info is not set
        msg = record.getMessage()
        if any(exc in msg for exc in self.SHUTDOWN_EXCEPTIONS):
            return
        
        # Get the corresponding loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        
        # Find the caller frame for correct source display
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging_intercept():
    """
    Configures log interception from standard logging to loguru.
    
    Intercepts logs from:
    - uvicorn (access logs, error logs)
    - uvicorn.error
    - uvicorn.access
    - fastapi
    """
    # List of loggers to intercept
    loggers_to_intercept = [
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
    ]
    
    for logger_name in loggers_to_intercept:
        logging_logger = logging.getLogger(logger_name)
        logging_logger.handlers = [InterceptHandler()]
        logging_logger.propagate = False


# Configure uvicorn/fastapi log interception
setup_logging_intercept()


# ==================================================================================================
# VPN/Proxy Configuration
# ==================================================================================================
# Must be set BEFORE creating any httpx clients (including in lifespan)
# httpx automatically picks up HTTP_PROXY, HTTPS_PROXY, ALL_PROXY from environment

if VPN_PROXY_URL:
    # Normalize URL - add http:// if no scheme specified
    proxy_url_with_scheme = VPN_PROXY_URL if "://" in VPN_PROXY_URL else f"http://{VPN_PROXY_URL}"
    
    # Set environment variables for httpx to pick up automatically
    os.environ['HTTP_PROXY'] = proxy_url_with_scheme
    os.environ['HTTPS_PROXY'] = proxy_url_with_scheme
    os.environ['ALL_PROXY'] = proxy_url_with_scheme
    
    # Exclude localhost from proxy to avoid routing local requests through it
    no_proxy_hosts = os.environ.get("NO_PROXY", "")
    local_hosts = "127.0.0.1,localhost"
    if no_proxy_hosts:
        os.environ["NO_PROXY"] = f"{no_proxy_hosts},{local_hosts}"
    else:
        os.environ["NO_PROXY"] = local_hosts
    
    logger.info(f"Proxy configured: {proxy_url_with_scheme}")
    logger.debug(f"NO_PROXY: {os.environ['NO_PROXY']}")


# --- Configuration Validation ---
def validate_configuration() -> None:
    """
    Validates that required configuration is present.
    
    Checks:
    - Either REFRESH_TOKEN, KIRO_CREDS_FILE, or KIRO_CLI_DB_FILE is configured
    - Supports both .env file (local) and environment variables (Docker)
    
    Raises:
        SystemExit: If critical configuration is missing
    """
    errors = []
    
    # Check if .env file exists (optional - can use environment variables)
    env_file = Path(".env")
    
    # Check for credentials (from .env or environment variables)
    has_refresh_token = bool(REFRESH_TOKEN)
    has_creds_file = bool(KIRO_CREDS_FILE)
    has_cli_db = bool(KIRO_CLI_DB_FILE)
    
    # Check if creds file actually exists
    if KIRO_CREDS_FILE:
        creds_path = Path(KIRO_CREDS_FILE).expanduser()
        if not creds_path.exists():
            has_creds_file = False
            logger.warning(f"KIRO_CREDS_FILE not found: {KIRO_CREDS_FILE}")
    
    # Check if CLI database file actually exists
    if KIRO_CLI_DB_FILE:
        cli_db_path = Path(KIRO_CLI_DB_FILE).expanduser()
        if not cli_db_path.exists():
            has_cli_db = False
            logger.warning(f"KIRO_CLI_DB_FILE not found: {KIRO_CLI_DB_FILE}")
    
    # If no credentials found, show helpful error
    if not has_refresh_token and not has_creds_file and not has_cli_db:
        if not env_file.exists():
            # No .env file and no environment variables
            errors.append(
                "No Kiro credentials configured!\n"
                "\n"
                "To get started:\n"
                "1. Create .env file:\n"
                "   cp .env.example .env\n"
                "\n"
                "2. Edit .env and configure your credentials:\n"
                "   2.1. Set you super-secret password as PROXY_API_KEY\n"
                "   2.2. Set your Kiro credentials:\n"
                "      - Option 1: KIRO_CREDS_FILE to your Kiro credentials JSON file\n"
                "      - Option 2: REFRESH_TOKEN from Kiro IDE traffic\n"
                "      - Option 3: KIRO_CLI_DB_FILE to kiro-cli SQLite database\n"
                "\n"
                "Or use environment variables (for Docker):\n"
                "   docker run -e PROXY_API_KEY=\"...\" -e REFRESH_TOKEN=\"...\" ...\n"
                "\n"
                "See README.md for detailed instructions."
            )
        else:
            # .env exists but no credentials configured
            errors.append(
                "No Kiro credentials configured!\n"
                "\n"
                "   Configure one of the following in your .env file:\n"
                "\n"
                "Set you super-secret password as PROXY_API_KEY\n"
                "   PROXY_API_KEY=\"my-super-secret-password-123\"\n"
                "\n"
                "   Option 1 (Recommended): JSON credentials file\n"
                "      KIRO_CREDS_FILE=\"path/to/your/kiro-credentials.json\"\n"
                "\n"
                "   Option 2: Refresh token\n"
                "      REFRESH_TOKEN=\"your_refresh_token_here\"\n"
                "\n"
                "   Option 3: kiro-cli SQLite database (AWS SSO)\n"
                "      KIRO_CLI_DB_FILE=\"~/.local/share/kiro-cli/data.sqlite3\"\n"
                "\n"
                "   See README.md for how to obtain credentials."
            )
    
    # Print errors and exit if any
    if errors:
        logger.error("")
        logger.error("=" * 60)
        logger.error("  CONFIGURATION ERROR")
        logger.error("=" * 60)
        for error in errors:
            for line in error.split('\n'):
                logger.error(f"  {line}")
        logger.error("=" * 60)
        logger.error("")
        sys.exit(1)
    
    # Note: Credential loading details are logged by KiroAuthManager


# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application lifecycle.
    
    Creates and initializes:
    - Shared HTTP client with connection pooling
    - KiroAuthManager for token management
    - ModelInfoCache for model caching
    
    The shared HTTP client is used by all requests to reduce memory usage
    and enable connection reuse. This is especially important for handling
    concurrent requests efficiently (fixes issue #24).
    """
    logger.info("Starting application... Creating state managers.")
    
    # Create shared HTTP client with connection pooling
    # This reduces memory usage and enables connection reuse across requests
    # Limits: max 100 total connections, max 20 keep-alive connections
    limits = httpx.Limits(
        max_connections=100,
        max_keepalive_connections=20,
        keepalive_expiry=30.0  # Close idle connections after 30 seconds
    )
    # Timeout configuration for streaming (long read timeout for model "thinking")
    timeout = httpx.Timeout(
        connect=30.0,
        read=STREAMING_READ_TIMEOUT,  # 300 seconds for streaming
        write=30.0,
        pool=30.0
    )
    app.state.http_client = httpx.AsyncClient(
        limits=limits,
        timeout=timeout,
        follow_redirects=True
    )
    logger.info("Shared HTTP client created with connection pooling")
    
    # Create AuthManager
    # Priority: SQLite DB > JSON file > environment variables
    app.state.auth_manager = KiroAuthManager(
        refresh_token=REFRESH_TOKEN,
        profile_arn=PROFILE_ARN,
        region=REGION,
        api_region=API_REGION,
        creds_file=KIRO_CREDS_FILE if KIRO_CREDS_FILE else None,
        sqlite_db=KIRO_CLI_DB_FILE if KIRO_CLI_DB_FILE else None,
    )
    
    # Create model cache
    app.state.model_cache = ModelInfoCache()
    
    # BLOCKING: Load models from Kiro API at startup
    # This ensures the cache is populated BEFORE accepting any requests.
    # No race conditions - requests only start after yield.
    logger.info("Loading models from Kiro API...")
    try:
        token = await app.state.auth_manager.get_access_token()
        from kiro.utils import get_kiro_headers
        from kiro.auth import AuthType
        headers = get_kiro_headers(app.state.auth_manager, token)
        
        # Build params - profileArn is only needed for Kiro Desktop auth
        params = {"origin": "AI_EDITOR"}
        if app.state.auth_manager.auth_type == AuthType.KIRO_DESKTOP and app.state.auth_manager.profile_arn:
            params["profileArn"] = app.state.auth_manager.profile_arn
        
        list_models_url = f"{app.state.auth_manager.q_host}/ListAvailableModels"
        logger.debug(f"Fetching models from: {list_models_url}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                list_models_url,
                headers=headers,
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                models_list = data.get("models", [])
                await app.state.model_cache.update(models_list)
                logger.debug(f"Successfully loaded {len(models_list)} models from Kiro API")
            else:
                raise Exception(f"HTTP {response.status_code}")
    except Exception as e:
        # FALLBACK: Use built-in model list
        logger.error(f"Failed to fetch models from Kiro API: {e}")
        logger.error("Using pre-configured fallback models. Not all models may be available on your plan, or the list may be outdated.")
        
        # Populate cache with fallback models
        await app.state.model_cache.update(FALLBACK_MODELS)
        logger.debug(f"Loaded {len(FALLBACK_MODELS)} fallback models")
    
    # Add hidden models to cache (they appear in /v1/models but not in Kiro API)
    # Hidden models are added ALWAYS, regardless of API success/failure
    for display_name, internal_id in HIDDEN_MODELS.items():
        app.state.model_cache.add_hidden_model(display_name, internal_id)
    
    if HIDDEN_MODELS:
        logger.debug(f"Added {len(HIDDEN_MODELS)} hidden models to cache")
    
    # Log final cache state
    all_models = app.state.model_cache.get_all_model_ids()
    logger.info(f"Model cache ready: {len(all_models)} models total")
    
    # Create model resolver (uses cache + hidden models + aliases for resolution)
    app.state.model_resolver = ModelResolver(
        cache=app.state.model_cache,
        hidden_models=HIDDEN_MODELS,
        aliases=MODEL_ALIASES,
        hidden_from_list=HIDDEN_FROM_LIST
    )
    logger.info("Model resolver initialized")
    
    # Log alias configuration if any
    if MODEL_ALIASES:
        logger.debug(f"Model aliases configured: {list(MODEL_ALIASES.keys())}")
    if HIDDEN_FROM_LIST:
        logger.debug(f"Models hidden from list: {HIDDEN_FROM_LIST}")
    
    yield
    
    # Graceful shutdown
    logger.info("Shutting down application...")
    try:
        await app.state.http_client.aclose()
        logger.info("Shared HTTP client closed")
    except Exception as e:
        logger.warning(f"Error closing shared HTTP client: {e}")


# --- FastAPI Application ---
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan
)


# --- CORS Middleware ---
# Allow CORS for all origins to support browser clients
# and tools that send preflight OPTIONS requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],  # Allow all headers
)


# --- Debug Logger Middleware ---
# Initializes debug logging BEFORE Pydantic validation
# This allows capturing validation errors (422) in debug logs
app.add_middleware(DebugLoggerMiddleware)


# --- Validation Error Handler Registration ---
app.add_exception_handler(RequestValidationError, validation_exception_handler)


# --- Route Registration ---
# OpenAI-compatible API: /v1/models, /v1/chat/completions
app.include_router(openai_router)

# Anthropic-compatible API: /v1/messages
app.include_router(anthropic_router)


# --- Uvicorn log config ---
# Minimal configuration for redirecting uvicorn logs to loguru.
# Uses InterceptHandler which intercepts logs and passes them to loguru.
UVICORN_LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "default": {
            "class": "main.InterceptHandler",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["default"], "level": "INFO", "propagate": False},
    },
}


def parse_cli_args() -> argparse.Namespace:
    """
    Parse command-line arguments for server configuration.
    
    CLI arguments have the highest priority, overriding both
    environment variables and default values.
    
    Returns:
        Parsed arguments namespace with host and port values
    """
    parser = argparse.ArgumentParser(
        description=f"{APP_TITLE} - {APP_DESCRIPTION}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration Priority (highest to lowest):
  1. CLI arguments (--host, --port)
  2. Environment variables (SERVER_HOST, SERVER_PORT)
  3. Default values (0.0.0.0:8000)

Examples:
  python main.py                          # Use defaults or env vars
  python main.py --port 9000              # Override port only
  python main.py --host 127.0.0.1         # Local connections only
  python main.py -H 0.0.0.0 -p 8080       # Short form
  
  SERVER_PORT=9000 python main.py         # Via environment
  uvicorn main:app --port 9000            # Via uvicorn directly
        """
    )
    
    parser.add_argument(
        "-H", "--host",
        type=str,
        default=None,  # None means "use env or default"
        metavar="HOST",
        help=f"Server host address (default: {DEFAULT_SERVER_HOST}, env: SERVER_HOST)"
    )
    
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=None,  # None means "use env or default"
        metavar="PORT",
        help=f"Server port (default: {DEFAULT_SERVER_PORT}, env: SERVER_PORT)"
    )
    
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"%(prog)s {APP_VERSION}"
    )
    
    return parser.parse_args()


def resolve_server_config(args: argparse.Namespace) -> tuple[str, int]:
    """
    Resolve final server configuration using priority hierarchy.
    
    Priority (highest to lowest):
    1. CLI arguments (--host, --port)
    2. Environment variables (SERVER_HOST, SERVER_PORT)
    3. Default values (0.0.0.0:8000)
    
    Args:
        args: Parsed CLI arguments
        
    Returns:
        Tuple of (host, port) with resolved values
    """
    # Host resolution: CLI > ENV > Default
    if args.host is not None:
        final_host = args.host
        host_source = "CLI argument"
    elif SERVER_HOST != DEFAULT_SERVER_HOST:
        final_host = SERVER_HOST
        host_source = "environment variable"
    else:
        final_host = DEFAULT_SERVER_HOST
        host_source = "default"
    
    # Port resolution: CLI > ENV > Default
    if args.port is not None:
        final_port = args.port
        port_source = "CLI argument"
    elif SERVER_PORT != DEFAULT_SERVER_PORT:
        final_port = SERVER_PORT
        port_source = "environment variable"
    else:
        final_port = DEFAULT_SERVER_PORT
        port_source = "default"
    
    # Log configuration sources for transparency
    logger.debug(f"Host: {final_host} (from {host_source})")
    logger.debug(f"Port: {final_port} (from {port_source})")
    
    return final_host, final_port


def print_startup_banner(host: str, port: int) -> None:
    """
    Print a startup banner with server information.
    
    Args:
        host: Server host address
        port: Server port
    """
    # ANSI color codes
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"
    
    # Determine display URL
    display_host = "localhost" if host == "0.0.0.0" else host
    url = f"http://{display_host}:{port}"
    
    print()
    print(f"  {WHITE}{BOLD}👻 {APP_TITLE} v{APP_VERSION}{RESET}")
    print()
    print(f"  {WHITE}Server running at:{RESET}")
    print(f"  {GREEN}{BOLD}➜  {url}{RESET}")
    print()
    print(f"  {DIM}API Docs:      {url}/docs{RESET}")
    print(f"  {DIM}Health Check:  {url}/health{RESET}")
    print()
    print(f"  {DIM}{'─' * 48}{RESET}")
    print(f"  {WHITE}💬 Found a bug? Need help? Have questions?{RESET}")
    print(f"  {YELLOW}➜  https://github.com/jwadow/kiro-gateway/issues{RESET}")
    print(f"  {DIM}{'─' * 48}{RESET}")
    print()


# --- Entry Point ---
if __name__ == "__main__":
    import uvicorn
    
    # Run configuration validation before starting server
    validate_configuration()
    
    # Warn about suboptimal timeout configuration
    _warn_timeout_configuration()
    
    # Parse CLI arguments
    args = parse_cli_args()
    
    # Resolve final configuration with priority hierarchy
    final_host, final_port = resolve_server_config(args)
    
    # Print startup banner
    print_startup_banner(final_host, final_port)
    
    logger.info(f"Starting Uvicorn server on {final_host}:{final_port}...")
    
    # Use string reference to avoid double module import
    uvicorn.run(
        "main:app",
        host=final_host,
        port=final_port,
        log_config=UVICORN_LOG_CONFIG,
    )
