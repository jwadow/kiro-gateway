# -*- coding: utf-8 -*-

"""
Tests for kiro/account_manager.py - Unified Account System.

Tests the AccountManager class that manages multiple Kiro accounts with:
- Lazy initialization
- Sticky behavior (prefer successful account)
- Circuit breaker with exponential backoff
- TTL-based model cache refresh
- State persistence
"""

import asyncio
import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from kiro.account_manager import (
    Account,
    AccountStats,
    ModelAccountList,
    AccountManager,
    _format_duration
)
from kiro.account_errors import ErrorType
from kiro.auth import KiroAuthManager, AuthType
from kiro.cache import ModelInfoCache
from kiro.model_resolver import ModelResolver


class TestAccountDataclass:
    """
    Tests for Account and AccountStats dataclasses.
    """
    
    def test_account_creation_with_defaults(self):
        """
        Test Account creation with default values.
        
        What it does: Verifies Account dataclass initialization
        Purpose: Ensure default values are set correctly
        """
        print("\n=== Test: Account creation with defaults ===")
        
        # Act
        account = Account(id="/test/path.json")
        
        # Assert
        print(f"Account ID: {account.id}")
        print(f"Auth manager: {account.auth_manager}")
        print(f"Failures: {account.failures}")
        print(f"Last failure time: {account.last_failure_time}")
        
        assert account.id == "/test/path.json"
        assert account.auth_manager is None
        assert account.model_cache is None
        assert account.model_resolver is None
        assert account.failures == 0
        assert account.last_failure_time == 0.0
        assert account.models_cached_at == 0.0
        assert isinstance(account.stats, AccountStats)
    
    def test_account_stats_initialization(self):
        """
        Test AccountStats initialization with zeros.
        
        What it does: Verifies AccountStats default values
        Purpose: Ensure statistics start at zero
        """
        print("\n=== Test: AccountStats initialization ===")
        
        # Act
        stats = AccountStats()
        
        # Assert
        print(f"Total requests: {stats.total_requests}")
        print(f"Successful requests: {stats.successful_requests}")
        print(f"Failed requests: {stats.failed_requests}")
        
        assert stats.total_requests == 0
        assert stats.successful_requests == 0
        assert stats.failed_requests == 0


class TestAccountManagerLoadCredentials:
    """
    Tests for AccountManager.load_credentials() method.
    """
    
    @pytest.mark.asyncio
    async def test_load_credentials_json_type(self, tmp_path):
        """
        Test loading credentials with type=json.
        
        What it does: Loads single JSON credential file
        Purpose: Verify JSON type credential loading
        """
        print("\n=== Test: load_credentials with type=json ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        credentials = [
            {
                "type": "json",
                "path": str(test_json),
                "enabled": True
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        print(f"Account IDs: {list(manager._accounts.keys())}")
        
        assert len(manager._accounts) == 1
        assert str(test_json.resolve()) in manager._accounts
    
    @pytest.mark.asyncio
    async def test_load_credentials_sqlite_type(self, tmp_path, temp_sqlite_db):
        """
        Test loading credentials with type=sqlite.
        
        What it does: Loads SQLite database credential
        Purpose: Verify SQLite type credential loading
        """
        print("\n=== Test: load_credentials with type=sqlite ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "sqlite",
                "path": temp_sqlite_db,
                "enabled": True
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 1
        assert str(Path(temp_sqlite_db).resolve()) in manager._accounts
    
    @pytest.mark.asyncio
    async def test_load_credentials_refresh_token_type(self, tmp_path):
        """
        Test loading credentials with type=refresh_token.
        
        What it does: Loads refresh token credential
        Purpose: Verify refresh_token type credential loading
        """
        print("\n=== Test: load_credentials with type=refresh_token ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "refresh_token",
                "refresh_token": "test_refresh_token_abc123",
                "profile_arn": "arn:aws:codewhisperer:us-east-1:123456789:profile/test",
                "region": "us-east-1",
                "enabled": True
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        # Create state file to avoid errors
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps({"current_account_index": 0, "model_to_accounts": {}, "accounts": {}}))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(state_file)
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        print(f"Account IDs: {list(manager._accounts.keys())}")
        
        assert len(manager._accounts) == 1
        # refresh_token type uses deterministic hash as ID
        account_id = list(manager._accounts.keys())[0]
        assert account_id.startswith("refresh_token_")
    
    @pytest.mark.asyncio
    async def test_load_credentials_folder_scanning(self, tmp_path):
        """
        Test folder scanning for credential files.
        
        What it does: Scans folder and loads all valid credential files
        Purpose: Verify folder scanning functionality
        """
        print("\n=== Test: load_credentials with folder scanning ===")
        
        # Arrange
        folder = tmp_path / "accounts"
        folder.mkdir()
        
        # Create valid files
        file1 = folder / "account1.json"
        file1.write_text(json.dumps({
            "refreshToken": "token1",
            "accessToken": "access1",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        file2 = folder / "account2.json"
        file2.write_text(json.dumps({
            "refreshToken": "token2",
            "accessToken": "access2",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "json",
                "path": str(folder),
                "enabled": True
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 2
    
    @pytest.mark.asyncio
    async def test_load_credentials_skip_invalid_files(self, tmp_path):
        """
        Test that invalid files are skipped with WARNING.
        
        What it does: Loads folder with invalid files
        Purpose: Verify invalid files are skipped gracefully
        """
        print("\n=== Test: load_credentials skips invalid files ===")
        
        # Arrange
        folder = tmp_path / "accounts"
        folder.mkdir()
        
        # Valid file
        valid_file = folder / "valid.json"
        valid_file.write_text(json.dumps({
            "refreshToken": "token",
            "accessToken": "access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        # Invalid JSON
        invalid_file = folder / "invalid.json"
        invalid_file.write_text("not a valid json {{{")
        
        # Non-JSON file
        text_file = folder / "readme.txt"
        text_file.write_text("This is not a credential file")
        
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "json",
                "path": str(folder),
                "enabled": True
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 1  # Only valid file loaded
    
    @pytest.mark.asyncio
    async def test_load_credentials_skip_disabled(self, tmp_path):
        """
        Test that entries with enabled=false are skipped.
        
        What it does: Loads credentials with disabled entry
        Purpose: Verify enabled flag is respected
        """
        print("\n=== Test: load_credentials skips disabled entries ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "token",
            "accessToken": "access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "json",
                "path": str(test_json),
                "enabled": False  # Disabled
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 0
    
    @pytest.mark.asyncio
    async def test_load_credentials_missing_type(self, tmp_path):
        """
        Test that entries without type are skipped.
        
        What it does: Loads credentials with missing type field
        Purpose: Verify type validation
        """
        print("\n=== Test: load_credentials skips entries without type ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "path": "/some/path.json",
                "enabled": True
                # Missing "type" field
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 0
    
    @pytest.mark.asyncio
    async def test_load_credentials_missing_path(self, tmp_path):
        """
        Test that json/sqlite entries without path are skipped.
        
        What it does: Loads credentials with missing path field
        Purpose: Verify path validation for json/sqlite types
        """
        print("\n=== Test: load_credentials skips json/sqlite without path ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "json",
                "enabled": True
                # Missing "path" field
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 0
    
    @pytest.mark.asyncio
    async def test_load_credentials_missing_refresh_token(self, tmp_path):
        """
        Test that refresh_token entries without refresh_token field are skipped.
        
        What it does: Loads credentials with missing refresh_token field
        Purpose: Verify refresh_token validation
        """
        print("\n=== Test: load_credentials skips refresh_token without token ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        credentials = [
            {
                "type": "refresh_token",
                "profile_arn": "arn:aws:codewhisperer:us-east-1:123456789:profile/test",
                "enabled": True
                # Missing "refresh_token" field
            }
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 0
    
    @pytest.mark.asyncio
    async def test_load_credentials_file_not_found(self, tmp_path):
        """
        Test handling of non-existent credentials.json.
        
        What it does: Attempts to load non-existent file
        Purpose: Verify graceful handling of missing file
        """
        print("\n=== Test: load_credentials with missing file ===")
        
        # Arrange
        manager = AccountManager(
            credentials_file=str(tmp_path / "nonexistent.json"),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act
        await manager.load_credentials()
        
        # Assert
        print(f"Loaded accounts: {len(manager._accounts)}")
        
        assert len(manager._accounts) == 0


class TestAccountManagerLoadState:
    """
    Tests for AccountManager.load_state() method.
    """
    
    @pytest.mark.asyncio
    async def test_load_state_success(self, tmp_path, sample_state_with_data):
        """
        Test loading existing state.json.
        
        What it does: Loads state from file
        Purpose: Verify state restoration
        """
        print("\n=== Test: load_state success ===")
        
        # Arrange
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(sample_state_with_data))
        
        # Create accounts first
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({"refreshToken": "token"}))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(state_file)
        )
        
        await manager.load_credentials()
        
        # Act
        await manager.load_state()
        
        # Assert
        print(f"Model mappings: {len(manager._model_to_accounts)}")
        print(f"Current account index: {manager._current_account_index}")
        
        assert len(manager._model_to_accounts) > 0
    
    @pytest.mark.asyncio
    async def test_load_state_restore_current_account_index(self, tmp_path):
        """
        Test restoration of global current_account_index.
        
        What it does: Restores sticky index from state
        Purpose: Verify global sticky behavior persistence
        """
        print("\n=== Test: load_state restores current_account_index ===")
        
        # Arrange
        state_data = {
            "current_account_index": 2,
            "model_to_accounts": {},
            "accounts": {}
        }
        
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state_data))
        
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(state_file)
        )
        
        # Act
        await manager.load_state()
        
        # Assert
        print(f"Current account index: {manager._current_account_index}")
        
        assert manager._current_account_index == 2
    
    @pytest.mark.asyncio
    async def test_load_state_restore_model_to_accounts(self, tmp_path):
        """
        Test restoration of model_to_accounts mapping.
        
        What it does: Restores model mappings from state
        Purpose: Verify model-to-account mapping persistence
        """
        print("\n=== Test: load_state restores model_to_accounts ===")
        
        # Arrange
        state_data = {
            "current_account_index": 0,
            "model_to_accounts": {
                "claude-opus-4.5": {
                    "accounts": ["/test/account1.json", "/test/account2.json"]
                }
            },
            "accounts": {}
        }
        
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state_data))
        
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(state_file)
        )
        
        # Act
        await manager.load_state()
        
        # Assert
        print(f"Model mappings: {manager._model_to_accounts}")
        
        assert "claude-opus-4.5" in manager._model_to_accounts
        assert len(manager._model_to_accounts["claude-opus-4.5"].accounts) == 2
    
    @pytest.mark.asyncio
    async def test_load_state_restore_account_runtime_state(self, tmp_path):
        """
        Test restoration of account runtime state (failures, stats, etc).
        
        What it does: Restores account state from file
        Purpose: Verify runtime state persistence
        """
        print("\n=== Test: load_state restores account runtime state ===")
        
        # Arrange
        # Create account first to get correct resolved path
        test_json = tmp_path / "account.json"
        test_json.write_text(json.dumps({"refreshToken": "token"}))
        account_id = str(test_json.resolve())
        
        state_data = {
            "current_account_index": 0,
            "model_to_accounts": {},
            "accounts": {
                account_id: {
                    "failures": 3,
                    "last_failure_time": 1704110400.0,
                    "models_cached_at": 1704106800.0,
                    "stats": {
                        "total_requests": 100,
                        "successful_requests": 97,
                        "failed_requests": 3
                    }
                }
            }
        }
        
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(state_data))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(state_file)
        )
        
        await manager.load_credentials()
        
        # Act
        await manager.load_state()
        
        # Assert
        account = manager._accounts[account_id]
        print(f"Account failures: {account.failures}")
        print(f"Account stats: {account.stats}")
        
        assert account.failures == 3
        assert account.last_failure_time == 1704110400.0
        assert account.models_cached_at == 1704106800.0
        assert account.stats.total_requests == 100
    
    @pytest.mark.asyncio
    async def test_load_state_file_not_found(self, tmp_path):
        """
        Test handling of non-existent state.json (empty state).
        
        What it does: Attempts to load non-existent state file
        Purpose: Verify graceful handling with empty state
        """
        print("\n=== Test: load_state with missing file ===")
        
        # Arrange
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(tmp_path / "nonexistent.json")
        )
        
        # Act
        await manager.load_state()
        
        # Assert
        print(f"Model mappings: {len(manager._model_to_accounts)}")
        print(f"Current account index: {manager._current_account_index}")
        
        assert len(manager._model_to_accounts) == 0
        assert manager._current_account_index == 0
    
    @pytest.mark.asyncio
    async def test_load_state_corrupted_json(self, tmp_path):
        """
        Test handling of corrupted state.json.
        
        What it does: Attempts to load invalid JSON
        Purpose: Verify error handling for corrupted state
        """
        print("\n=== Test: load_state with corrupted JSON ===")
        
        # Arrange
        state_file = tmp_path / "state.json"
        state_file.write_text("not a valid json {{{")
        
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(state_file)
        )
        
        # Act
        await manager.load_state()
        
        # Assert - should handle gracefully
        print(f"Model mappings: {len(manager._model_to_accounts)}")
        
        assert len(manager._model_to_accounts) == 0



class TestAccountManagerInitializeAccount:
    """
    Tests for AccountManager._initialize_account() method.
    """
    
    @pytest.mark.asyncio
    async def test_initialize_account_json_success(self, tmp_path, mock_list_models_response):
        """
        Test successful account initialization with type=json.
        
        What it does: Initializes account with JSON credentials
        Purpose: Verify complete initialization flow
        """
        print("\n=== Test: initialize_account with JSON ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z",
            "profileArn": "arn:aws:codewhisperer:us-east-1:123456789:profile/test",
            "region": "us-east-1"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Mock HTTP client for ListAvailableModels
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            # Act
            success = await manager._initialize_account(account_id)
        
        # Assert
        print(f"Initialization success: {success}")
        assert success is True
        assert manager._accounts[account_id].auth_manager is not None
        assert manager._accounts[account_id].model_cache is not None
        assert manager._accounts[account_id].model_resolver is not None
    
    @pytest.mark.asyncio
    async def test_initialize_account_fetch_models_fallback(self, tmp_path):
        """
        Test fallback to FALLBACK_MODELS when API fails.
        
        What it does: Initializes account when ListAvailableModels fails
        Purpose: Verify fallback mechanism
        """
        print("\n=== Test: initialize_account with fallback models ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Mock HTTP client to fail
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_client.request_with_retry = AsyncMock(side_effect=Exception("Network error"))
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            # Act
            success = await manager._initialize_account(account_id)
        
        # Assert
        print(f"Initialization success: {success}")
        assert success is True  # Should succeed with fallback
        assert manager._accounts[account_id].model_cache is not None


class TestAccountManagerGetNextAccount:
    """
    Tests for AccountManager.get_next_account() method.
    """
    
    @pytest.mark.asyncio
    async def test_get_next_account_single_bypass_circuit_breaker(self, tmp_path, mock_list_models_response):
        """
        Test that single account bypasses Circuit Breaker.
        
        What it does: Gets account when only one exists
        Purpose: Verify single account always returns (no cooldown)
        """
        print("\n=== Test: get_next_account single account bypasses Circuit Breaker ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Set failures (should be ignored for single account)
        manager._accounts[account_id].failures = 10
        manager._accounts[account_id].last_failure_time = time.time()
        
        # Act
        account = await manager.get_next_account("claude-opus-4.5")
        
        # Assert
        print(f"Got account: {account is not None}")
        assert account is not None  # Single account always returns


class TestAccountManagerReportSuccess:
    """
    Tests for AccountManager.report_success() method.
    """
    
    @pytest.mark.asyncio
    async def test_report_success_reset_failures(self, tmp_path, mock_list_models_response):
        """
        Test that report_success resets failures to 0.
        
        What it does: Reports success after failures
        Purpose: Verify failure counter reset
        """
        print("\n=== Test: report_success resets failures ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Set failures
        manager._accounts[account_id].failures = 5
        
        # Act
        await manager.report_success(account_id, "claude-opus-4.5")
        
        # Assert
        print(f"Failures after success: {manager._accounts[account_id].failures}")
        assert manager._accounts[account_id].failures == 0
    
    @pytest.mark.asyncio
    async def test_report_success_update_stats(self, tmp_path, mock_list_models_response):
        """
        Test that report_success updates statistics.
        
        What it does: Reports success and checks stats
        Purpose: Verify statistics tracking
        """
        print("\n=== Test: report_success updates stats ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Act
        await manager.report_success(account_id, "claude-opus-4.5")
        
        # Assert
        stats = manager._accounts[account_id].stats
        print(f"Stats: total={stats.total_requests}, successful={stats.successful_requests}")
        assert stats.total_requests == 1
        assert stats.successful_requests == 1


class TestAccountManagerReportFailure:
    """
    Tests for AccountManager.report_failure() method.
    """
    
    @pytest.mark.asyncio
    async def test_report_failure_recoverable_increment_failures(self, tmp_path, mock_list_models_response):
        """
        Test that RECOVERABLE errors increment failures.
        
        What it does: Reports RECOVERABLE failure
        Purpose: Verify failure counter increment
        """
        print("\n=== Test: report_failure RECOVERABLE increments failures ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Act
        await manager.report_failure(
            account_id, "claude-opus-4.5",
            ErrorType.RECOVERABLE, 429, None
        )
        
        # Assert
        print(f"Failures: {manager._accounts[account_id].failures}")
        assert manager._accounts[account_id].failures == 1
    
    @pytest.mark.asyncio
    async def test_report_failure_fatal_no_increment(self, tmp_path, mock_list_models_response):
        """
        Test that FATAL errors do NOT increment failures.
        
        What it does: Reports FATAL failure
        Purpose: Verify failures not incremented for request errors
        """
        print("\n=== Test: report_failure FATAL does not increment failures ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Act
        await manager.report_failure(
            account_id, "claude-opus-4.5",
            ErrorType.FATAL, 400, "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        )
        
        # Assert
        print(f"Failures: {manager._accounts[account_id].failures}")
        assert manager._accounts[account_id].failures == 0  # Not incremented


class TestAccountManagerSaveState:
    """
    Tests for AccountManager._save_state() and save_state_periodically().
    """
    
    @pytest.mark.asyncio
    async def test_save_state_atomic_write(self, tmp_path):
        """
        Test atomic state saving via tmp file.
        
        What it does: Saves state and checks tmp file usage
        Purpose: Verify atomic write pattern
        """
        print("\n=== Test: save_state atomic write ===")
        
        # Arrange
        state_file = tmp_path / "state.json"
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(state_file)
        )
        
        # Act
        await manager._save_state()
        
        # Assert
        print(f"State file exists: {state_file.exists()}")
        assert state_file.exists()
        
        # Verify tmp file was cleaned up
        tmp_file = tmp_path / "state.json.tmp"
        print(f"Tmp file exists: {tmp_file.exists()}")
        assert not tmp_file.exists()


class TestAccountManagerGetFirstAccount:
    """
    Tests for AccountManager.get_first_account() method.
    """
    
    @pytest.mark.asyncio
    async def test_get_first_account_success(self, tmp_path, mock_list_models_response):
        """
        Test getting first initialized account.
        
        What it does: Gets first account for legacy mode
        Purpose: Verify legacy mode support
        """
        print("\n=== Test: get_first_account success ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Act
        account = manager.get_first_account()
        
        # Assert
        print(f"Got account: {account is not None}")
        assert account is not None
        assert account.auth_manager is not None
    
    def test_get_first_account_no_initialized(self, tmp_path):
        """
        Test RuntimeError when no initialized accounts.
        
        What it does: Attempts to get account when none initialized
        Purpose: Verify error handling
        """
        print("\n=== Test: get_first_account with no initialized accounts ===")
        
        # Arrange
        manager = AccountManager(
            credentials_file=str(tmp_path / "creds.json"),
            state_file=str(tmp_path / "state.json")
        )
        
        # Act & Assert
        with pytest.raises(RuntimeError, match="No initialized accounts available"):
            manager.get_first_account()


class TestAccountManagerGetAllAvailableModels:
    """
    Tests for AccountManager.get_all_available_models() method.
    """
    
    @pytest.mark.asyncio
    async def test_get_all_available_models_collect_from_all(self, tmp_path, mock_list_models_response):
        """
        Test collecting unique models from all accounts.
        
        What it does: Gets models from multiple accounts
        Purpose: Verify model aggregation for /v1/models endpoint
        """
        print("\n=== Test: get_all_available_models collects from all ===")
        
        # Arrange
        test_json = tmp_path / "test.json"
        test_json.write_text(json.dumps({
            "refreshToken": "test_token",
            "accessToken": "test_access",
            "expiresAt": "2099-01-01T00:00:00.000Z"
        }))
        
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text(json.dumps([
            {"type": "json", "path": str(test_json), "enabled": True}
        ]))
        
        manager = AccountManager(
            credentials_file=str(creds_file),
            state_file=str(tmp_path / "state.json")
        )
        
        await manager.load_credentials()
        account_id = str(test_json.resolve())
        
        # Initialize account
        with patch('kiro.account_manager.AccountManager._schedule_refresh') as mock_http_class:
            mock_client = AsyncMock()
            mock_response = Mock()  # Response is not async
            mock_response.status_code = 200
            mock_response.json.return_value = mock_list_models_response
            mock_client.request_with_retry = AsyncMock(return_value=mock_response)
            mock_client.close = AsyncMock()
            mock_http_class.return_value = mock_client
            
            await manager._initialize_account(account_id)
        
        # Act
        models = manager.get_all_available_models()
        
        # Assert
        print(f"Available models: {len(models)}")
        assert len(models) > 0
        assert isinstance(models, list)
        assert all(isinstance(m, str) for m in models)


class TestFormatDuration:
    """
    Tests for _format_duration() helper function.
    """
    
    def test_format_duration_seconds(self):
        """Test formatting seconds."""
        assert _format_duration(30) == "30s"
        assert _format_duration(59) == "59s"
    
    def test_format_duration_minutes(self):
        """Test formatting minutes."""
        assert _format_duration(60) == "1m"
        assert _format_duration(300) == "5m"
        assert _format_duration(3599) == "59m"
    
    def test_format_duration_hours(self):
        """Test formatting hours."""
        assert _format_duration(3600) == "1h"
        assert _format_duration(7200) == "2h"
        assert _format_duration(86399) == "23h"
    
    def test_format_duration_days(self):
        """Test formatting days."""
        assert _format_duration(86400) == "1d"
        assert _format_duration(172800) == "2d"



# =============================================================================
# Hardening regression tests: single-flight init outside the global lock,
# cooldown after failed lazy init, half-open single trial, shared probe
# semaphore, credential redaction, off-loop state saving.
# =============================================================================

import threading as _threading

import kiro.account_manager as _am
from kiro.account_manager import (
    MODEL_PROBE_CONCURRENCY,
    _probe_candidate_models,
    _redact_entry,
)
from kiro.config import ACCOUNT_RECOVERY_TIMEOUT


async def _manager_with_accounts(tmp_path, count: int) -> AccountManager:
    """Build a manager with ``count`` json accounts (not yet initialized)."""
    entries = []
    for i in range(count):
        f = tmp_path / f"acc{i}.json"
        f.write_text(json.dumps({
            "refreshToken": f"t{i}",
            "accessToken": f"a{i}",
            "expiresAt": "2099-01-01T00:00:00.000Z",
        }))
        entries.append({"type": "json", "path": str(f), "enabled": True})
    creds = tmp_path / "credentials.json"
    creds.write_text(json.dumps(entries))
    manager = AccountManager(str(creds), str(tmp_path / "state.json"))
    await manager.load_credentials()
    return manager


class _FakeAuthFactory:
    """
    Stand-in for KiroAuthManager that counts constructions and token fetches.

    ``gate`` (if set) blocks get_access_token until released; ``fail`` makes
    token verification raise ValueError (bad credentials).
    """

    def __init__(self, fail: bool = False, gate: asyncio.Event = None):
        self.fail = fail
        self.gate = gate
        self.constructed = 0
        self.token_calls = 0
        self.started = asyncio.Event()

    def __call__(self, *args, **kwargs):
        self.constructed += 1
        factory = self
        auth = MagicMock()
        auth.api_host = "https://q.us-east-1.amazonaws.com"
        auth.q_host = auth.api_host
        auth.profile_arn = None

        async def get_access_token():
            factory.token_calls += 1
            factory.started.set()
            if factory.gate is not None:
                await factory.gate.wait()
            if factory.fail:
                raise ValueError("bad credentials")
            return "tok"

        auth.get_access_token = get_access_token
        return auth


class TestSingleFlightInitialization:
    """Concurrent init requests for one account share one in-flight task."""

    @pytest.mark.asyncio
    async def test_concurrent_initialize_refreshes_credentials_once(self, tmp_path):
        """
        What it does: 10 concurrent _initialize_account() calls for one account.
        Purpose: The same credentials must never be refreshed twice in parallel.
        """
        manager = await _manager_with_accounts(tmp_path, 1)
        account_id = next(iter(manager._accounts))
        gate = asyncio.Event()
        factory = _FakeAuthFactory(gate=gate)

        with patch.object(_am, "KiroAuthManager", factory):
            calls = [asyncio.create_task(manager._initialize_account(account_id)) for _ in range(10)]
            await asyncio.wait_for(factory.started.wait(), 1)
            await asyncio.sleep(0)
            gate.set()
            results = await asyncio.gather(*calls)

        assert results == [True] * 10
        assert factory.constructed == 1
        assert factory.token_calls == 1
        assert account_id not in manager._init_tasks  # cleaned up after completion

    @pytest.mark.asyncio
    async def test_background_and_lazy_init_share_one_task(self, tmp_path):
        """
        What it does: start_background_init() then get_next_account() for the same account.
        Purpose: Lazy init joins the background attempt instead of starting another.
        """
        manager = await _manager_with_accounts(tmp_path, 2)
        gate = asyncio.Event()
        factory = _FakeAuthFactory(gate=gate)

        with patch.object(_am, "KiroAuthManager", factory), \
                patch.object(manager, "_refresh_account_models", AsyncMock()):
            manager.start_background_init()
            await asyncio.wait_for(factory.started.wait(), 1)
            lazy = asyncio.create_task(manager.get_next_account("m"))
            await asyncio.sleep(0.01)
            gate.set()
            account = await asyncio.wait_for(lazy, 1)
            await asyncio.gather(*list(manager._tasks), return_exceptions=True)

        assert account is not None and account.auth_manager is not None
        assert factory.constructed == 2  # one per account, never two for the same one

    @pytest.mark.asyncio
    async def test_global_lock_not_held_during_initialization(self, tmp_path):
        """
        What it does: Blocks one account's token refresh, then reports on another account.
        Purpose: Slow init must not block report_success/report_failure or other selections.
        """
        manager = await _manager_with_accounts(tmp_path, 2)
        ids = list(manager._accounts)
        gate = asyncio.Event()
        factory = _FakeAuthFactory(gate=gate)

        with patch.object(_am, "KiroAuthManager", factory), \
                patch.object(manager, "_refresh_account_models", AsyncMock()):
            pending = asyncio.create_task(manager.get_next_account("m"))
            await asyncio.wait_for(factory.started.wait(), 1)

            assert not manager._lock.locked()
            await asyncio.wait_for(manager.report_success(ids[1], "m"), 0.5)
            await asyncio.wait_for(
                manager.report_failure(ids[1], "m", ErrorType.FATAL, 400, None), 0.5
            )

            gate.set()
            await asyncio.wait_for(pending, 1)
            await asyncio.gather(*list(manager._tasks), return_exceptions=True)

    @pytest.mark.asyncio
    async def test_cancelled_caller_does_not_cancel_shared_init(self, tmp_path):
        """
        What it does: Cancels one waiter while another waits on the same init.
        Purpose: A disconnected client must not abort initialization for everyone.
        """
        manager = await _manager_with_accounts(tmp_path, 1)
        account_id = next(iter(manager._accounts))
        gate = asyncio.Event()
        factory = _FakeAuthFactory(gate=gate)

        with patch.object(_am, "KiroAuthManager", factory):
            first = asyncio.create_task(manager._initialize_account(account_id))
            second = asyncio.create_task(manager._initialize_account(account_id))
            await asyncio.wait_for(factory.started.wait(), 1)
            first.cancel()
            await asyncio.sleep(0)
            gate.set()
            assert await asyncio.wait_for(second, 1) is True

        assert first.cancelled()
        assert manager._accounts[account_id].auth_manager is not None
        assert factory.constructed == 1

    @pytest.mark.asyncio
    async def test_failed_init_can_be_retried(self, tmp_path):
        """
        What it does: Init fails, then credentials are fixed and init is retried.
        Purpose: A failed in-flight task must not be cached forever.
        """
        manager = await _manager_with_accounts(tmp_path, 1)
        account_id = next(iter(manager._accounts))
        factory = _FakeAuthFactory(fail=True)

        with patch.object(_am, "KiroAuthManager", factory):
            assert await manager._initialize_account(account_id) is False
            assert account_id not in manager._init_tasks
            factory.fail = False
            assert await manager._initialize_account(account_id) is True

        assert factory.constructed == 2

    @pytest.mark.asyncio
    async def test_initialize_unknown_account_returns_false(self, tmp_path):
        """What it does: Unknown account id. Purpose: No task is created for it."""
        manager = await _manager_with_accounts(tmp_path, 1)
        assert await manager._initialize_account("does-not-exist") is False
        assert manager._init_tasks == {}


class TestLazyInitFailureCooldown:
    """A failed lazy init must start the circuit-breaker cooldown."""

    @pytest.mark.asyncio
    async def test_failed_lazy_init_sets_last_failure_time(self, tmp_path):
        """
        What it does: First account fails lazy init in multi-account mode.
        Purpose: Previously only failures was incremented, so the cooldown never
                 started and the dead account was retried on every request.
        """
        manager = await _manager_with_accounts(tmp_path, 2)
        ids = list(manager._accounts)
        dead_factory = _FakeAuthFactory(fail=True)

        before = time.time()
        with patch.object(_am, "KiroAuthManager", dead_factory), \
                patch.object(_am.random, "random", return_value=1.0):
            result = await manager.get_next_account("m")
        after = time.time()

        dead = manager._accounts[ids[0]]
        assert result is None  # both accounts use the failing factory
        assert dead.failures == 1
        assert before <= dead.last_failure_time <= after
        assert manager._dirty is True

    @pytest.mark.asyncio
    async def test_dead_account_not_retried_during_cooldown(self, tmp_path):
        """
        What it does: After a failed init, issues 5 more requests.
        Purpose: The dead account's credentials are not refreshed again during cooldown.
        """
        manager = await _manager_with_accounts(tmp_path, 2)
        ids = list(manager._accounts)
        calls_per_account = {i: 0 for i in ids}

        async def fake_init(account_id):
            calls_per_account[account_id] += 1
            if account_id == ids[0]:
                return False
            manager._accounts[account_id].auth_manager = MagicMock()
            return True

        with patch.object(manager, "_do_initialize_account", fake_init), \
                patch.object(manager, "_schedule_refresh", Mock()), \
                patch.object(_am.random, "random", return_value=1.0):
            for _ in range(6):
                account = await manager.get_next_account("m")
                assert account.id == ids[1]

        assert calls_per_account[ids[0]] == 1
        assert manager._accounts[ids[0]].failures == 1

    @pytest.mark.asyncio
    async def test_failed_lazy_init_does_not_mutate_caller_exclude_set(self, tmp_path):
        """What it does: Passes an exclude set. Purpose: Internal skip tracking stays local."""
        manager = await _manager_with_accounts(tmp_path, 3)
        ids = list(manager._accounts)
        exclude = {ids[2]}
        with patch.object(_am, "KiroAuthManager", _FakeAuthFactory(fail=True)), \
                patch.object(_am.random, "random", return_value=1.0):
            assert await manager.get_next_account("m", exclude_accounts=exclude) is None
        assert exclude == {ids[2]}
        assert manager._accounts[ids[2]].failures == 0  # excluded account never touched

    @pytest.mark.asyncio
    async def test_single_account_failed_init_returns_none_without_penalty(self, tmp_path):
        """
        What it does: Single account whose init fails.
        Purpose: Single-account mode bypasses the circuit breaker (unchanged behavior).
        """
        manager = await _manager_with_accounts(tmp_path, 1)
        account_id = next(iter(manager._accounts))
        with patch.object(_am, "KiroAuthManager", _FakeAuthFactory(fail=True)):
            assert await manager.get_next_account("m") is None
        assert manager._accounts[account_id].failures == 0


class TestHalfOpenSingleTrial:
    """After cooldown, only one request at a time may try a recovering account."""

    async def _ready_manager(self, tmp_path, count: int = 2) -> AccountManager:
        manager = await _manager_with_accounts(tmp_path, count)
        for account in manager._accounts.values():
            account.auth_manager = MagicMock()
            account.models_cached_at = time.time()
        return manager

    @pytest.mark.asyncio
    async def test_only_first_request_gets_half_open_account(self, tmp_path):
        """
        What it does: Account 0 is past its cooldown; 5 requests select concurrently.
        Purpose: Previously every concurrent request was sent to the recovering account.
        """
        manager = await self._ready_manager(tmp_path)
        ids = list(manager._accounts)
        recovering = manager._accounts[ids[0]]
        recovering.failures = 1
        recovering.last_failure_time = time.time() - ACCOUNT_RECOVERY_TIMEOUT - 1

        with patch.object(_am.random, "random", return_value=1.0):
            selected = await asyncio.gather(*(manager.get_next_account("m") for _ in range(5)))

        picked = [a.id for a in selected]
        assert picked.count(ids[0]) == 1
        assert picked.count(ids[1]) == 4
        assert time.time() - recovering.last_failure_time < 5  # cooldown restarted

    @pytest.mark.asyncio
    async def test_trial_success_reopens_account(self, tmp_path):
        """What it does: Trial request succeeds. Purpose: Account is fully usable again."""
        manager = await self._ready_manager(tmp_path)
        ids = list(manager._accounts)
        recovering = manager._accounts[ids[0]]
        recovering.failures = 1
        recovering.last_failure_time = time.time() - ACCOUNT_RECOVERY_TIMEOUT - 1

        with patch.object(_am.random, "random", return_value=1.0):
            trial = await manager.get_next_account("m")
            assert trial.id == ids[0]
            await manager.report_success(ids[0], "m")
            again = [await manager.get_next_account("m") for _ in range(3)]

        assert recovering.failures == 0
        assert all(a.id == ids[0] for a in again)

    @pytest.mark.asyncio
    async def test_trial_failure_extends_cooldown(self, tmp_path):
        """What it does: Trial request fails. Purpose: Backoff grows and account stays closed."""
        manager = await self._ready_manager(tmp_path)
        ids = list(manager._accounts)
        recovering = manager._accounts[ids[0]]
        recovering.failures = 1
        recovering.last_failure_time = time.time() - ACCOUNT_RECOVERY_TIMEOUT - 1

        with patch.object(_am.random, "random", return_value=1.0):
            assert (await manager.get_next_account("m")).id == ids[0]
            await manager.report_failure(ids[0], "m", ErrorType.RECOVERABLE, 429, None)
            following = [await manager.get_next_account("m") for _ in range(3)]

        assert recovering.failures == 2
        assert all(a.id == ids[1] for a in following)

    @pytest.mark.asyncio
    async def test_unreported_trial_reopens_after_next_window(self, tmp_path):
        """
        What it does: Trial request never reports back (e.g. crashed).
        Purpose: The account must not be blocked forever; it reopens after one window.
        """
        manager = await self._ready_manager(tmp_path)
        ids = list(manager._accounts)
        recovering = manager._accounts[ids[0]]
        recovering.failures = 1
        recovering.last_failure_time = time.time() - ACCOUNT_RECOVERY_TIMEOUT - 1

        with patch.object(_am.random, "random", return_value=1.0):
            assert (await manager.get_next_account("m")).id == ids[0]
            assert (await manager.get_next_account("m")).id == ids[1]
            recovering.last_failure_time -= ACCOUNT_RECOVERY_TIMEOUT + 1  # simulate time passing
            assert (await manager.get_next_account("m")).id == ids[0]

    @pytest.mark.asyncio
    async def test_account_in_cooldown_is_skipped_without_probabilistic_retry(self, tmp_path):
        """What it does: Account still cooling down. Purpose: Regression guard for normal skip."""
        manager = await self._ready_manager(tmp_path)
        ids = list(manager._accounts)
        manager._accounts[ids[0]].failures = 1
        manager._accounts[ids[0]].last_failure_time = time.time()
        with patch.object(_am.random, "random", return_value=1.0):
            assert (await manager.get_next_account("m")).id == ids[1]


class TestSharedProbeSemaphore:
    """Model probes are limited across all accounts by one shared semaphore."""

    @staticmethod
    def _tracking_probe():
        state = {"active": 0, "peak": 0}

        async def fake_probe(client, auth, token, model_id, arn):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.005)
            state["active"] -= 1
            return True

        return state, fake_probe

    @staticmethod
    def _auth():
        auth = MagicMock()
        auth.get_access_token = AsyncMock(return_value="tok")
        return auth

    def test_limit_constant(self):
        """What it does: Checks the named constant. Purpose: Limit is 4 as specified."""
        assert MODEL_PROBE_CONCURRENCY == 4

    @pytest.mark.asyncio
    async def test_default_semaphore_limits_single_call(self):
        """
        What it does: Probes 20 candidates without passing a semaphore.
        Purpose: Previously the semaphore equaled len(candidates), i.e. no limit.
        """
        state, fake_probe = self._tracking_probe()
        candidates = [f"m{i}" for i in range(20)]
        with patch.object(_am, "_probe_model", fake_probe):
            out = await _probe_candidate_models(MagicMock(), self._auth(), candidates, "")
        assert state["peak"] <= MODEL_PROBE_CONCURRENCY
        assert len(out) == 21  # all probed, "auto" included

    @pytest.mark.asyncio
    async def test_shared_semaphore_limits_across_accounts(self):
        """
        What it does: Three accounts probe 10 candidates each at the same time.
        Purpose: The limit is global, not per account.
        """
        state, fake_probe = self._tracking_probe()
        shared = asyncio.Semaphore(MODEL_PROBE_CONCURRENCY)
        candidates = [f"m{i}" for i in range(10)]
        with patch.object(_am, "_probe_model", fake_probe):
            await asyncio.gather(*(
                _probe_candidate_models(MagicMock(), self._auth(), candidates, "", semaphore=shared)
                for _ in range(3)
            ))
        assert state["peak"] == MODEL_PROBE_CONCURRENCY

    @pytest.mark.asyncio
    async def test_manager_passes_its_shared_semaphore(self, tmp_path):
        """What it does: Runs _discover_models with probing on. Purpose: Manager semaphore is used."""
        manager = await _manager_with_accounts(tmp_path, 2)
        account = next(iter(manager._accounts.values()))
        account.auth_manager = MagicMock()
        account.auth_manager.api_host = "https://runtime.us-east-1.kiro.dev"
        account.auth_manager.profile_arn = None
        account.model_cache = None
        probe = AsyncMock(return_value=[{"modelId": "auto"}])
        with patch.object(_am, "MODEL_PROBING_ENABLED", True), \
                patch.object(_am, "_probe_candidate_models", probe):
            await manager._discover_models(account)
            await manager.shutdown()
        assert probe.await_args.kwargs["semaphore"] is manager._probe_semaphore


class TestCredentialEntryRedaction:
    """Credential entries must never be logged with secrets."""

    def test_redacts_sensitive_keys(self):
        """What it does: Redacts token/secret/password/key fields. Purpose: Core rule."""
        entry = {
            "type": "refresh_token",
            "refresh_token": "RT",
            "client_secret": "CS",
            "password": "PW",
            "api_key": "AK",
            "region": "us-east-1",
            "enabled": True,
        }
        redacted = _redact_entry(entry)
        for value in ("RT", "CS", "PW", "AK"):
            assert value not in str(redacted)
        assert redacted["region"] == "us-east-1"
        assert redacted["type"] == "refresh_token"
        assert redacted["enabled"] is True
        assert entry["refresh_token"] == "RT"  # original untouched

    def test_case_insensitive_and_camel_case(self):
        """What it does: Uses camelCase/upper keys. Purpose: Kiro JSON uses refreshToken."""
        redacted = _redact_entry({"refreshToken": "A", "ClientSecret": "B", "ACCESS_TOKEN": "C", "KeyId": "D"})
        assert set(redacted.values()) == {"***REDACTED***"}

    def test_nested_dicts_redacted(self):
        """What it does: Nested credential blob. Purpose: Secrets can hide one level down."""
        redacted = _redact_entry({"type": "x", "extra": {"accessToken": "SECRET", "note": "ok"}})
        assert "SECRET" not in str(redacted)
        assert redacted["extra"]["note"] == "ok"

    @pytest.mark.parametrize("entry", ["raw-refresh-token-string", 42, None, ["tok"]])
    def test_non_dict_entries_reduced_to_type(self, entry):
        """What it does: Malformed entries. Purpose: Unknown content is never echoed."""
        result = _redact_entry(entry)
        assert result == f"<{type(entry).__name__}>"

    @pytest.mark.asyncio
    async def test_load_credentials_warnings_do_not_leak_secrets(self, tmp_path):
        """
        What it does: Loads invalid entries that contain secrets.
        Purpose: Warnings for invalid entries must show redacted entries only.
        """
        creds = tmp_path / "credentials.json"
        creds.write_text(json.dumps([
            {"refresh_token": "LEAK_1", "enabled": True},                        # missing type
            {"type": "json", "client_secret": "LEAK_2"},                          # missing path
            {"type": "refresh_token", "refresh_token": "", "api_key": "LEAK_3"},  # empty token
        ]))
        manager = AccountManager(str(creds), str(tmp_path / "state.json"))
        with patch.object(_am.logger, "warning") as warning:
            await manager.load_credentials()
        logged = " ".join(str(c) for c in warning.call_args_list)
        assert warning.call_count == 3
        for secret in ("LEAK_1", "LEAK_2", "LEAK_3"):
            assert secret not in logged
        assert "***REDACTED***" in logged


class TestSaveStateOffLoop:
    """State is snapshotted synchronously and written in a worker thread."""

    @pytest.mark.asyncio
    async def test_write_runs_in_worker_thread_without_global_lock(self, tmp_path):
        """What it does: Records thread + lock state during the write. Purpose: No loop/lock blocking."""
        manager = await _manager_with_accounts(tmp_path, 1)
        loop_thread = _threading.get_ident()
        seen = {}
        original = manager._write_state_file

        def recording_write(data):
            seen["thread"] = _threading.get_ident()
            seen["locked"] = manager._lock.locked()
            return original(data)

        manager._write_state_file = recording_write
        assert await manager._save_state() is True
        assert seen["thread"] != loop_thread
        assert seen["locked"] is False
        saved = json.loads((tmp_path / "state.json").read_text())
        assert set(saved) == {"current_account_index", "accounts", "model_to_accounts"}

    @pytest.mark.asyncio
    async def test_snapshot_is_detached_from_live_state(self, tmp_path):
        """What it does: Mutates state after snapshot. Purpose: Writer never sees half-updated lists."""
        manager = await _manager_with_accounts(tmp_path, 1)
        manager._model_to_accounts["m"] = ModelAccountList(accounts=["a"])
        snapshot = manager._snapshot_state()
        manager._model_to_accounts["m"].accounts.append("b")
        assert snapshot["model_to_accounts"]["m"]["accounts"] == ["a"]

    @pytest.mark.asyncio
    async def test_write_failure_returns_false_and_cleans_tmp(self, tmp_path):
        """What it does: State path points into a missing directory. Purpose: No crash, False result."""
        manager = await _manager_with_accounts(tmp_path, 1)
        manager._state_file = str(tmp_path / "missing_dir" / "state.json")
        assert await manager._save_state() is False
        assert not (tmp_path / "missing_dir").exists()

    @pytest.mark.asyncio
    async def test_periodic_save_restores_dirty_flag_on_failure(self, tmp_path):
        """What it does: Periodic save fails. Purpose: Data is retried on the next cycle."""
        manager = await _manager_with_accounts(tmp_path, 1)
        manager._dirty = True
        attempts = []

        async def failing_save():
            attempts.append(1)
            return False

        manager._save_state = failing_save
        with patch.object(_am, "STATE_SAVE_INTERVAL_SECONDS", 0.001):
            task = asyncio.create_task(manager.save_state_periodically())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert len(attempts) >= 2  # retried because dirty was restored
        assert manager._dirty is True

    @pytest.mark.asyncio
    async def test_periodic_save_clears_dirty_on_success(self, tmp_path):
        """What it does: Periodic save succeeds once. Purpose: No redundant rewrites."""
        manager = await _manager_with_accounts(tmp_path, 1)
        manager._dirty = True
        with patch.object(_am, "STATE_SAVE_INTERVAL_SECONDS", 0.001):
            task = asyncio.create_task(manager.save_state_periodically())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert manager._dirty is False
        assert (tmp_path / "state.json").exists()
