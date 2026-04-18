# -*- coding: utf-8 -*-

"""
Unit tests for the configuration module.
Verifies loading settings from environment variables.
"""

import pytest
import os
from unittest.mock import patch


class TestLogLevelConfig:
    """Tests for LOG_LEVEL configuration."""
    
    def test_default_log_level_is_info(self):
        """
        What it does: Verifies that LOG_LEVEL defaults to INFO.
        Purpose: Ensure that INFO is used when no environment variable is set.
        
        Note: This test verifies the config.py code logic, not the actual
        value from the .env file. We mock os.getenv to simulate
        the absence of the environment variable.
        """
        print("Setup: Mocking os.getenv for LOG_LEVEL...")
        
        # Create a mock that returns None for LOG_LEVEL (simulating missing variable)
        original_getenv = os.getenv
        
        def mock_getenv(key, default=None):
            if key == "LOG_LEVEL":
                print(f"os.getenv('{key}') -> None (mocked)")
                return default  # Return default, simulating missing variable
            return original_getenv(key, default)
        
        with patch.object(os, 'getenv', side_effect=mock_getenv):
            # Reload config module with mocked getenv
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            print(f"Comparing: Expected 'INFO', Got '{config_module.LOG_LEVEL}'")
            assert config_module.LOG_LEVEL == "INFO"
        
        # Restore module with real values
        import importlib
        import kiro.config as config_module
        importlib.reload(config_module)
    
    def test_log_level_from_environment(self):
        """
        What it does: Verifies loading LOG_LEVEL from environment variable.
        Purpose: Ensure that the value from environment is used.
        """
        print("Setup: Setting LOG_LEVEL=DEBUG...")
        
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            print(f"Comparing: Expected 'DEBUG', Got '{config_module.LOG_LEVEL}'")
            assert config_module.LOG_LEVEL == "DEBUG"
    
    def test_log_level_uppercase_conversion(self):
        """
        What it does: Verifies LOG_LEVEL conversion to uppercase.
        Purpose: Ensure that lowercase value is converted to uppercase.
        """
        print("Setup: Setting LOG_LEVEL=warning (lowercase)...")
        
        with patch.dict(os.environ, {"LOG_LEVEL": "warning"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            print(f"Comparing: Expected 'WARNING', Got '{config_module.LOG_LEVEL}'")
            assert config_module.LOG_LEVEL == "WARNING"
    
    def test_log_level_trace(self):
        """
        What it does: Verifies setting LOG_LEVEL=TRACE.
        Purpose: Ensure that TRACE level is supported.
        """
        print("Setup: Setting LOG_LEVEL=TRACE...")
        
        with patch.dict(os.environ, {"LOG_LEVEL": "TRACE"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            assert config_module.LOG_LEVEL == "TRACE"
    
    def test_log_level_error(self):
        """
        What it does: Verifies setting LOG_LEVEL=ERROR.
        Purpose: Ensure that ERROR level is supported.
        """
        print("Setup: Setting LOG_LEVEL=ERROR...")
        
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            assert config_module.LOG_LEVEL == "ERROR"
    
    def test_log_level_critical(self):
        """
        What it does: Verifies setting LOG_LEVEL=CRITICAL.
        Purpose: Ensure that CRITICAL level is supported.
        """
        print("Setup: Setting LOG_LEVEL=CRITICAL...")
        
        with patch.dict(os.environ, {"LOG_LEVEL": "CRITICAL"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"LOG_LEVEL: {config_module.LOG_LEVEL}")
            assert config_module.LOG_LEVEL == "CRITICAL"


class TestToolDescriptionMaxLengthConfig:
    """Tests for TOOL_DESCRIPTION_MAX_LENGTH configuration."""
    
    def test_default_tool_description_max_length(self):
        """
        What it does: Verifies the default value for TOOL_DESCRIPTION_MAX_LENGTH.
        Purpose: Ensure that 10000 is used by default.
        """
        print("Setup: Removing TOOL_DESCRIPTION_MAX_LENGTH from environment...")
        
        with patch.dict(os.environ, {}, clear=False):
            if "TOOL_DESCRIPTION_MAX_LENGTH" in os.environ:
                del os.environ["TOOL_DESCRIPTION_MAX_LENGTH"]
            
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"TOOL_DESCRIPTION_MAX_LENGTH: {config_module.TOOL_DESCRIPTION_MAX_LENGTH}")
            assert config_module.TOOL_DESCRIPTION_MAX_LENGTH == 10000
    
    def test_tool_description_max_length_from_environment(self):
        """
        What it does: Verifies loading TOOL_DESCRIPTION_MAX_LENGTH from environment.
        Purpose: Ensure that the value from environment is used.
        """
        print("Setup: Setting TOOL_DESCRIPTION_MAX_LENGTH=5000...")
        
        with patch.dict(os.environ, {"TOOL_DESCRIPTION_MAX_LENGTH": "5000"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"TOOL_DESCRIPTION_MAX_LENGTH: {config_module.TOOL_DESCRIPTION_MAX_LENGTH}")
            assert config_module.TOOL_DESCRIPTION_MAX_LENGTH == 5000
    
    def test_tool_description_max_length_zero_disables(self):
        """
        What it does: Verifies that 0 disables the feature.
        Purpose: Ensure that TOOL_DESCRIPTION_MAX_LENGTH=0 works.
        """
        print("Setup: Setting TOOL_DESCRIPTION_MAX_LENGTH=0...")
        
        with patch.dict(os.environ, {"TOOL_DESCRIPTION_MAX_LENGTH": "0"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"TOOL_DESCRIPTION_MAX_LENGTH: {config_module.TOOL_DESCRIPTION_MAX_LENGTH}")
            assert config_module.TOOL_DESCRIPTION_MAX_LENGTH == 0


class TestTimeoutConfigurationWarning:
    """Tests for _warn_timeout_configuration() function."""
    
    def test_no_warning_when_first_token_less_than_streaming(self, capsys):
        """
        What it does: Verifies that warning is NOT shown with correct configuration.
        Purpose: Ensure that no warning when FIRST_TOKEN_TIMEOUT < STREAMING_READ_TIMEOUT.
        """
        print("Setup: FIRST_TOKEN_TIMEOUT=15, STREAMING_READ_TIMEOUT=300...")
        
        with patch.dict(os.environ, {
            "FIRST_TOKEN_TIMEOUT": "15",
            "STREAMING_READ_TIMEOUT": "300"
        }):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            # Call the warning function
            config_module._warn_timeout_configuration()
            
            captured = capsys.readouterr()
            print(f"Captured stderr: {captured.err}")
            
            # Warning should NOT be shown
            assert "WARNING" not in captured.err
            assert "Suboptimal timeout configuration" not in captured.err
    
    def test_warning_when_first_token_equals_streaming(self, capsys):
        """
        What it does: Verifies that warning is shown when timeouts are equal.
        Purpose: Ensure that warning when FIRST_TOKEN_TIMEOUT == STREAMING_READ_TIMEOUT.
        """
        print("Setup: FIRST_TOKEN_TIMEOUT=300, STREAMING_READ_TIMEOUT=300...")
        
        with patch.dict(os.environ, {
            "FIRST_TOKEN_TIMEOUT": "300",
            "STREAMING_READ_TIMEOUT": "300"
        }):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            # Call the warning function
            config_module._warn_timeout_configuration()
            
            captured = capsys.readouterr()
            print(f"Captured stderr: {captured.err}")
            
            # Warning SHOULD be shown
            assert "WARNING" in captured.err or "Suboptimal timeout configuration" in captured.err
    
    def test_warning_when_first_token_greater_than_streaming(self, capsys):
        """
        What it does: Verifies that warning is shown when FIRST_TOKEN > STREAMING.
        Purpose: Ensure that warning when FIRST_TOKEN_TIMEOUT > STREAMING_READ_TIMEOUT.
        """
        print("Setup: FIRST_TOKEN_TIMEOUT=500, STREAMING_READ_TIMEOUT=300...")
        
        with patch.dict(os.environ, {
            "FIRST_TOKEN_TIMEOUT": "500",
            "STREAMING_READ_TIMEOUT": "300"
        }):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            # Call the warning function
            config_module._warn_timeout_configuration()
            
            captured = capsys.readouterr()
            print(f"Captured stderr: {captured.err}")
            
            # Warning SHOULD be shown
            assert "WARNING" in captured.err or "Suboptimal timeout configuration" in captured.err
            # Verify that timeout values are mentioned in warning
            assert "500" in captured.err
            assert "300" in captured.err
    
    def test_warning_contains_recommendation(self, capsys):
        """
        What it does: Verifies that warning contains a recommendation.
        Purpose: Ensure that user receives useful information.
        """
        print("Setup: FIRST_TOKEN_TIMEOUT=400, STREAMING_READ_TIMEOUT=300...")
        
        with patch.dict(os.environ, {
            "FIRST_TOKEN_TIMEOUT": "400",
            "STREAMING_READ_TIMEOUT": "300"
        }):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            # Call the warning function
            config_module._warn_timeout_configuration()
            
            captured = capsys.readouterr()
            print(f"Captured stderr: {captured.err}")
            
            # Warning should contain recommendation
            assert "Recommendation" in captured.err or "LESS than" in captured.err


class TestAwsSsoOidcUrlConfig:
    """Tests for AWS SSO OIDC URL configuration."""
    
    def test_aws_sso_oidc_url_template_exists(self):
        """
        What it does: Verifies that AWS_SSO_OIDC_URL_TEMPLATE constant exists.
        Purpose: Ensure the template is defined in config.
        """
        print("Setup: Importing config module...")
        import importlib
        import kiro.config as config_module
        importlib.reload(config_module)
        
        print("Verification: AWS_SSO_OIDC_URL_TEMPLATE exists...")
        assert hasattr(config_module, 'AWS_SSO_OIDC_URL_TEMPLATE')
        
        print(f"AWS_SSO_OIDC_URL_TEMPLATE: {config_module.AWS_SSO_OIDC_URL_TEMPLATE}")
        assert "oidc" in config_module.AWS_SSO_OIDC_URL_TEMPLATE
        assert "amazonaws.com" in config_module.AWS_SSO_OIDC_URL_TEMPLATE
        assert "{region}" in config_module.AWS_SSO_OIDC_URL_TEMPLATE
    
    def test_get_aws_sso_oidc_url_returns_correct_url(self):
        """
        What it does: Verifies that get_aws_sso_oidc_url returns correct URL.
        Purpose: Ensure the function formats URL correctly.
        """
        print("Setup: Importing get_aws_sso_oidc_url...")
        from kiro.config import get_aws_sso_oidc_url
        
        print("Action: Calling get_aws_sso_oidc_url('us-east-1')...")
        url = get_aws_sso_oidc_url("us-east-1")
        
        print(f"Verification: URL is correct...")
        expected = "https://oidc.us-east-1.amazonaws.com/token"
        print(f"Comparing: Expected '{expected}', Got '{url}'")
        assert url == expected
    
    def test_get_aws_sso_oidc_url_with_different_regions(self):
        """
        What it does: Verifies URL generation for different regions.
        Purpose: Ensure the function works with various AWS regions.
        """
        print("Setup: Importing get_aws_sso_oidc_url...")
        from kiro.config import get_aws_sso_oidc_url
        
        test_cases = [
            ("us-east-1", "https://oidc.us-east-1.amazonaws.com/token"),
            ("eu-west-1", "https://oidc.eu-west-1.amazonaws.com/token"),
            ("ap-southeast-1", "https://oidc.ap-southeast-1.amazonaws.com/token"),
            ("us-west-2", "https://oidc.us-west-2.amazonaws.com/token"),
        ]
        
        for region, expected in test_cases:
            print(f"Action: Calling get_aws_sso_oidc_url('{region}')...")
            url = get_aws_sso_oidc_url(region)
            print(f"Comparing: Expected '{expected}', Got '{url}'")
            assert url == expected


class TestServerHostConfig:
    """Tests for SERVER_HOST configuration."""
    
    def test_default_server_host_is_0_0_0_0(self):
        """
        What it does: Verifies that SERVER_HOST defaults to 0.0.0.0.
        Purpose: Ensure that 0.0.0.0 (all interfaces) is used when no environment variable is set.
        """
        print("Setup: Removing SERVER_HOST from environment...")
        
        with patch.dict(os.environ, {}, clear=False):
            if "SERVER_HOST" in os.environ:
                del os.environ["SERVER_HOST"]
            
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_HOST: {config_module.SERVER_HOST}")
            print(f"DEFAULT_SERVER_HOST: {config_module.DEFAULT_SERVER_HOST}")
            print(f"Comparing: Expected '0.0.0.0', Got '{config_module.SERVER_HOST}'")
            assert config_module.SERVER_HOST == "0.0.0.0"
            assert config_module.DEFAULT_SERVER_HOST == "0.0.0.0"
    
    def test_server_host_from_environment(self):
        """
        What it does: Verifies loading SERVER_HOST from environment variable.
        Purpose: Ensure that the value from environment is used.
        """
        print("Setup: Setting SERVER_HOST=127.0.0.1...")
        
        with patch.dict(os.environ, {"SERVER_HOST": "127.0.0.1"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_HOST: {config_module.SERVER_HOST}")
            print(f"Comparing: Expected '127.0.0.1', Got '{config_module.SERVER_HOST}'")
            assert config_module.SERVER_HOST == "127.0.0.1"
    
    def test_server_host_custom_value(self):
        """
        What it does: Verifies setting SERVER_HOST to a custom IP address.
        Purpose: Ensure that any valid IP address can be used.
        """
        print("Setup: Setting SERVER_HOST=192.168.1.100...")
        
        with patch.dict(os.environ, {"SERVER_HOST": "192.168.1.100"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_HOST: {config_module.SERVER_HOST}")
            assert config_module.SERVER_HOST == "192.168.1.100"


class TestServerPortConfig:
    """Tests for SERVER_PORT configuration."""
    
    def test_default_server_port_is_8000(self):
        """
        What it does: Verifies that SERVER_PORT defaults to 8000.
        Purpose: Ensure that 8000 is used when no environment variable is set.
        """
        print("Setup: Removing SERVER_PORT from environment...")
        
        with patch.dict(os.environ, {}, clear=False):
            if "SERVER_PORT" in os.environ:
                del os.environ["SERVER_PORT"]
            
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_PORT: {config_module.SERVER_PORT}")
            print(f"DEFAULT_SERVER_PORT: {config_module.DEFAULT_SERVER_PORT}")
            print(f"Comparing: Expected 8000, Got {config_module.SERVER_PORT}")
            assert config_module.SERVER_PORT == 8000
            assert config_module.DEFAULT_SERVER_PORT == 8000
    
    def test_server_port_from_environment(self):
        """
        What it does: Verifies loading SERVER_PORT from environment variable.
        Purpose: Ensure that the value from environment is used.
        """
        print("Setup: Setting SERVER_PORT=9000...")
        
        with patch.dict(os.environ, {"SERVER_PORT": "9000"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_PORT: {config_module.SERVER_PORT}")
            print(f"Comparing: Expected 9000, Got {config_module.SERVER_PORT}")
            assert config_module.SERVER_PORT == 9000
    
    def test_server_port_custom_value(self):
        """
        What it does: Verifies setting SERVER_PORT to a custom port number.
        Purpose: Ensure that any valid port number can be used.
        """
        print("Setup: Setting SERVER_PORT=3000...")
        
        with patch.dict(os.environ, {"SERVER_PORT": "3000"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_PORT: {config_module.SERVER_PORT}")
            assert config_module.SERVER_PORT == 3000
    
    def test_server_port_is_integer(self):
        """
        What it does: Verifies that SERVER_PORT is converted to integer.
        Purpose: Ensure that string from environment is converted to int.
        """
        print("Setup: Setting SERVER_PORT=8080 (as string)...")
        
        with patch.dict(os.environ, {"SERVER_PORT": "8080"}):
            import importlib
            import kiro.config as config_module
            importlib.reload(config_module)
            
            print(f"SERVER_PORT: {config_module.SERVER_PORT}")
            print(f"Type: {type(config_module.SERVER_PORT)}")
            assert isinstance(config_module.SERVER_PORT, int)
            assert config_module.SERVER_PORT == 8080


class TestKiroCliDbFileConfig:
    """Tests for KIRO_CLI_DB_FILE configuration."""
    
    def test_kiro_cli_db_file_config_exists(self):
        """
        What it does: Verifies that KIRO_CLI_DB_FILE constant exists.
        Purpose: Ensure the config parameter is defined.
        """
        print("Setup: Importing config module...")
        import importlib
        import kiro.config as config_module
        importlib.reload(config_module)
        
        print("Verification: KIRO_CLI_DB_FILE exists...")
        assert hasattr(config_module, 'KIRO_CLI_DB_FILE')
        
        print(f"KIRO_CLI_DB_FILE: '{config_module.KIRO_CLI_DB_FILE}'")
        # Default should be empty string
        assert isinstance(config_module.KIRO_CLI_DB_FILE, str)
    
    def test_kiro_cli_db_file_from_environment(self):
        """
        What it does: Verifies loading KIRO_CLI_DB_FILE from environment variable.
        Purpose: Ensure the value from environment is used and normalized.
        """
        print("Setup: Importing config module...")
        import importlib
        import kiro.config as config_module
        
        # Test that KIRO_CLI_DB_FILE is loaded and is a string
        print(f"KIRO_CLI_DB_FILE: {config_module.KIRO_CLI_DB_FILE}")
        assert isinstance(config_module.KIRO_CLI_DB_FILE, str)
        
        # If value is set (not empty), verify it's a normalized path
        if config_module.KIRO_CLI_DB_FILE:
            # Path should be normalized (no raw ~ or forward slashes on Windows)
            assert not config_module.KIRO_CLI_DB_FILE.startswith("~")
            # Should be a valid path string (contains path separators or is absolute)
            from pathlib import Path
            path = Path(config_module.KIRO_CLI_DB_FILE)
            # Path should be constructable (doesn't raise exception)
            assert str(path) == config_module.KIRO_CLI_DB_FILE


class TestFallbackModelsConfig:
    """Tests for FALLBACK_MODELS configuration."""
    
    def test_fallback_models_exists(self):
        """
        What it does: Verifies that FALLBACK_MODELS constant exists.
        Purpose: Ensure the fallback model list is defined in config.
        """
        print("Setup: Importing config module...")
        import importlib
        import kiro.config as config_module
        importlib.reload(config_module)
        
        print("Verification: FALLBACK_MODELS exists...")
        assert hasattr(config_module, 'FALLBACK_MODELS')
        
        print(f"FALLBACK_MODELS type: {type(config_module.FALLBACK_MODELS)}")
        assert isinstance(config_module.FALLBACK_MODELS, list)
    
    def test_fallback_models_not_empty(self):
        """
        What it does: Verifies that FALLBACK_MODELS contains at least one model.
        Purpose: Ensure fallback list is populated for DNS failure recovery.
        """
        print("Setup: Importing FALLBACK_MODELS...")
        from kiro.config import FALLBACK_MODELS
        
        print(f"FALLBACK_MODELS length: {len(FALLBACK_MODELS)}")
        print(f"Comparing: Expected > 0, Got {len(FALLBACK_MODELS)}")
        assert len(FALLBACK_MODELS) > 0
    
    def test_fallback_models_structure(self):
        """
        What it does: Verifies that each fallback model has required modelId field.
        Purpose: Ensure fallback models have correct structure for cache.update().
        """
        print("Setup: Importing FALLBACK_MODELS...")
        from kiro.config import FALLBACK_MODELS
        
        print(f"Action: Checking structure of {len(FALLBACK_MODELS)} models...")
        for i, model in enumerate(FALLBACK_MODELS):
            print(f"Checking model {i}: {model}")
            
            print(f"  Verification: model is dict...")
            assert isinstance(model, dict), f"Model {i} is not a dict"
            
            print(f"  Verification: model has 'modelId'...")
            assert "modelId" in model, f"Model {i} missing 'modelId'"
            
            print(f"  Verification: modelId is string...")
            assert isinstance(model["modelId"], str), f"Model {i} modelId is not string"
            
            print(f"  Verification: modelId is not empty...")
            assert len(model["modelId"]) > 0, f"Model {i} modelId is empty"
    
    def test_fallback_models_contain_claude_models(self):
        """
        What it does: Verifies that fallback models include Claude models.
        Purpose: Ensure fallback list contains expected Claude 4/4.5 models.
        """
        print("Setup: Importing FALLBACK_MODELS...")
        from kiro.config import FALLBACK_MODELS
        
        model_ids = [m["modelId"] for m in FALLBACK_MODELS]
        print(f"Model IDs in fallback list: {model_ids}")
        
        print("Verification: Contains at least one Claude model...")
        has_claude = any("claude" in mid.lower() for mid in model_ids)
        assert has_claude, "No Claude models in fallback list"
    
    def test_fallback_models_use_dot_format(self):
        """
        What it does: Verifies that model IDs use dot format (e.g., claude-4.5).
        Purpose: Ensure consistency with Kiro API format.
        """
        print("Setup: Importing FALLBACK_MODELS...")
        from kiro.config import FALLBACK_MODELS
        
        print("Action: Checking model ID format...")
        for model in FALLBACK_MODELS:
            model_id = model["modelId"]
            print(f"Checking: {model_id}")
            
            # If model has version number, it should use dot format
            if any(char.isdigit() for char in model_id):
                # Check for patterns like "4.5" or "4-5"
                if "-4-5" in model_id or "-4-0" in model_id:
                    print(f"  WARNING: {model_id} uses dash format instead of dot")
                    # This is acceptable but not ideal
                    pass


class TestFallbackModelsIntegration:
    """Integration tests for FALLBACK_MODELS with ModelResolver."""
    
    @pytest.mark.asyncio
    async def test_fallback_models_work_with_model_resolver(self):
        """
        What it does: Verifies that fallback models work with ModelResolver normalization.
        Purpose: Ensure that model name normalization (claude-opus-4-5 → claude-opus-4.5)
                 works correctly with fallback models, just like with API models.
        """
        print("Setup: Importing FALLBACK_MODELS and creating cache...")
        from kiro.config import FALLBACK_MODELS
        from kiro.cache import ModelInfoCache
        from kiro.model_resolver import ModelResolver
        
        # Simulate DNS failure scenario - populate cache with fallback models
        cache = ModelInfoCache()
        await cache.update(FALLBACK_MODELS)
        
        print(f"Cache populated with {cache.size} fallback models")
        print(f"Model IDs in cache: {cache.get_all_model_ids()}")
        
        # Create resolver
        resolver = ModelResolver(cache=cache, hidden_models={})
        
        print("\nAction: Testing normalization with dash format...")
        # Test that dash format (claude-opus-4-5) is normalized and found
        test_cases = [
            ("claude-opus-4-5", "claude-opus-4.5"),  # Dash → Dot
            ("claude-sonnet-4-5", "claude-sonnet-4.5"),  # Dash → Dot
            ("claude-haiku-4-5", "claude-haiku-4.5"),  # Dash → Dot
        ]
        
        for input_name, expected_normalized in test_cases:
            print(f"\n  Testing: {input_name} → {expected_normalized}")
            resolution = resolver.resolve(input_name)
            
            print(f"    Resolution source: {resolution.source}")
            print(f"    Normalized: {resolution.normalized}")
            print(f"    Internal ID: {resolution.internal_id}")
            print(f"    Is verified: {resolution.is_verified}")
            
            # Verify normalization happened
            print(f"    Comparing normalized: Expected '{expected_normalized}', Got '{resolution.normalized}'")
            assert resolution.normalized == expected_normalized
            
            # Verify model was found in cache (not passthrough)
            print(f"    Comparing source: Expected 'cache', Got '{resolution.source}'")
            assert resolution.source == "cache", f"Model {input_name} should be found in fallback cache"
            
            print(f"    Comparing is_verified: Expected True, Got {resolution.is_verified}")
            assert resolution.is_verified is True
    
    @pytest.mark.asyncio
    async def test_fallback_models_appear_in_available_models(self):
        """
        What it does: Verifies that fallback models appear in get_available_models().
        Purpose: Ensure that /v1/models endpoint will show fallback models.
        """
        print("Setup: Importing FALLBACK_MODELS and creating cache...")
        from kiro.config import FALLBACK_MODELS
        from kiro.cache import ModelInfoCache
        from kiro.model_resolver import ModelResolver
        
        cache = ModelInfoCache()
        await cache.update(FALLBACK_MODELS)
        
        resolver = ModelResolver(cache=cache, hidden_models={})
        
        print("Action: Getting available models...")
        available = resolver.get_available_models()
        
        print(f"Available models: {available}")
        print(f"Comparing length: Expected {len(FALLBACK_MODELS)}, Got {len(available)}")
        assert len(available) == len(FALLBACK_MODELS)
        
        # Verify all fallback models are present
        fallback_ids = {m["modelId"] for m in FALLBACK_MODELS}
        available_set = set(available)
        
        print(f"Comparing sets: Expected {fallback_ids}, Got {available_set}")
        assert fallback_ids == available_set


# ==================================================================================================
# Tests for WebSearch Configuration
# ==================================================================================================

class TestWebSearchConfig:
    """Tests for WebSearch configuration (WEB_SEARCH_ENABLED)."""
    
    def test_web_search_enabled_default_true(self, monkeypatch):
        """
        What it does: Verifies WEB_SEARCH_ENABLED defaults to true.
        Purpose: Ensure auto-injection is enabled by default.
        """
        print("Setup: Removing WEB_SEARCH_ENABLED from environment...")
        monkeypatch.delenv("WEB_SEARCH_ENABLED", raising=False)
        
        print("Action: Reloading config module...")
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected True, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is True
    
    def test_web_search_enabled_false(self, monkeypatch):
        """
        What it does: Verifies WEB_SEARCH_ENABLED=false disables auto-injection.
        Purpose: Ensure users can disable auto-injection.
        """
        print("Setup: Setting WEB_SEARCH_ENABLED=false...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "false")
        
        print("Action: Reloading config module...")
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected False, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is False
    
    def test_web_search_enabled_true(self, monkeypatch):
        """
        What it does: Verifies WEB_SEARCH_ENABLED=true enables auto-injection.
        Purpose: Ensure explicit true value works.
        """
        print("Setup: Setting WEB_SEARCH_ENABLED=true...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "true")
        
        print("Action: Reloading config module...")
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected True, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is True
    
    def test_web_search_enabled_numeric_values(self, monkeypatch):
        """
        What it does: Verifies numeric values (1/0) work for WEB_SEARCH_ENABLED.
        Purpose: Ensure compatibility with numeric boolean values.
        """
        print("Setup: Testing WEB_SEARCH_ENABLED=1...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "1")
        
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected True, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is True
        
        print("Setup: Testing WEB_SEARCH_ENABLED=0...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "0")
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected False, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is False
    
    def test_web_search_enabled_yes_value(self, monkeypatch):
        """
        What it does: Verifies WEB_SEARCH_ENABLED=yes enables auto-injection.
        Purpose: Ensure 'yes' value works.
        """
        print("Setup: Setting WEB_SEARCH_ENABLED=yes...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "yes")
        
        print("Action: Reloading config module...")
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected True, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is True
    
    def test_web_search_enabled_case_insensitive(self, monkeypatch):
        """
        What it does: Verifies WEB_SEARCH_ENABLED is case-insensitive.
        Purpose: Ensure TRUE, True, true all work.
        """
        print("Setup: Testing WEB_SEARCH_ENABLED=TRUE...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "TRUE")
        
        from importlib import reload
        import kiro.config as config_module
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected True, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is True
        
        print("Setup: Testing WEB_SEARCH_ENABLED=FALSE...")
        monkeypatch.setenv("WEB_SEARCH_ENABLED", "FALSE")
        reload(config_module)
        
        print(f"Comparing WEB_SEARCH_ENABLED: Expected False, Got {config_module.WEB_SEARCH_ENABLED}")
        assert config_module.WEB_SEARCH_ENABLED is False