# -*- coding: utf-8 -*-

"""
Tests for main.py lifespan() function - Account System initialization.

Tests cover:
- Legacy fallback: .env → credentials.json migration
- AccountManager initialization
- First working account initialization
- Background task management
"""

import asyncio
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch, call
from contextlib import asynccontextmanager


# =============================================================================
# Test Class: Legacy Fallback (Migration)
# =============================================================================

class TestLifespanLegacyFallback:
    """
    Tests for legacy .env → credentials.json migration.
    
    What it does: Verifies automatic migration from .env to credentials.json
    Purpose: Ensure backward compatibility with existing .env configurations
    """
    
    @pytest.mark.asyncio
    async def test_lifespan_legacy_mode_recreate_credentials(self, tmp_path, monkeypatch):
        """
        Test 92: ACCOUNT_SYSTEM=false всегда пересоздаёт credentials.json
        
        What it does: Verifies that legacy mode recreates credentials.json on every startup
        Purpose: Ensure .env changes are always reflected in legacy mode
        """
        print("\n=== Test 92: Legacy mode recreates credentials.json ===")
        
        # Arrange: Patch constants directly in main module (not os.environ)
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", False)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("main.PROFILE_ARN", "arn:aws:codewhisperer:us-east-1:123456789:profile/test")
        monkeypatch.setattr("main.REGION", "us-east-1")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        # Create old credentials.json
        old_creds = [{"type": "json", "path": "/old/path.json"}]
        creds_file.write_text(json.dumps(old_creds))
        print(f"Created old credentials.json: {old_creds}")
        
        # Mock config paths
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        # Mock AccountManager to prevent actual initialization
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                # Import and run lifespan
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: credentials.json was recreated
        assert creds_file.exists()
        new_creds = json.loads(creds_file.read_text())
        print(f"New credentials.json: {new_creds}")
        
        assert len(new_creds) == 1
        assert new_creds[0]["type"] == "refresh_token"
        assert new_creds[0]["refresh_token"] == "test_refresh_token"
        print("✓ credentials.json was recreated from .env in legacy mode")
    
    @pytest.mark.asyncio
    async def test_lifespan_account_system_one_time_migration(self, tmp_path, monkeypatch):
        """
        Test 93: ACCOUNT_SYSTEM=true создаёт credentials.json только раз
        
        What it does: Verifies one-time migration in account system mode
        Purpose: Ensure credentials.json is not overwritten after initial migration
        """
        print("\n=== Test 93: Account system one-time migration ===")
        
        # Arrange: Patch constants directly
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        # First run: no credentials.json
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                # First run
                async with lifespan(app):
                    pass
        
        assert creds_file.exists()
        first_content = creds_file.read_text()
        print(f"First run created: {first_content}")
        
        # Modify credentials.json manually
        manual_creds = [{"type": "json", "path": "/manual/path.json"}]
        creds_file.write_text(json.dumps(manual_creds))
        print(f"Manually modified to: {manual_creds}")
        
        # Second run: credentials.json exists
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                async with lifespan(app):
                    pass
        
        # Assert: credentials.json was NOT overwritten
        second_content = json.loads(creds_file.read_text())
        print(f"Second run kept: {second_content}")
        
        assert second_content == manual_creds
        print("✓ credentials.json was not overwritten on second run")
    
    @pytest.mark.asyncio
    async def test_lifespan_migration_priority_sqlite(self, tmp_path, monkeypatch):
        """
        Test 94: Приоритет SQLite > JSON > refresh_token
        
        What it does: Verifies credential source priority during migration
        Purpose: Ensure correct priority order matches KiroAuthManager
        """
        print("\n=== Test 94: Migration priority SQLite > JSON > refresh_token ===")
        
        # Arrange: all three sources present
        # Create SQLite DB
        import sqlite3
        sqlite_db = tmp_path / "data.sqlite3"
        conn = sqlite3.connect(str(sqlite_db))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE auth_kv (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute(
            "INSERT INTO auth_kv VALUES (?, ?)",
            ("codewhisperer:odic:token", json.dumps({"access_token": "sqlite_token"}))
        )
        conn.commit()
        conn.close()
        
        # Create JSON file
        json_file = tmp_path / "kiro-auth.json"
        json_file.write_text(json.dumps({"accessToken": "json_token"}))
        
        # Patch constants directly
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", str(sqlite_db))
        monkeypatch.setattr("main.KIRO_CREDS_FILE", str(json_file))
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: SQLite was chosen (highest priority)
        creds = json.loads(creds_file.read_text())
        print(f"Created credentials: {creds}")
        
        assert len(creds) == 1
        assert creds[0]["type"] == "sqlite"
        assert creds[0]["path"] == str(sqlite_db)
        print("✓ SQLite was chosen (highest priority)")
    
    @pytest.mark.asyncio
    async def test_lifespan_migration_add_env_overrides(self, tmp_path, monkeypatch):
        """
        Test 95: Добавление profile_arn, region, api_region из .env
        
        What it does: Verifies that env var overrides are added to migrated credentials
        Purpose: Ensure per-account parameters are preserved during migration
        """
        print("\n=== Test 95: Add env overrides during migration ===")
        
        # Arrange: Patch constants and also patch os.getenv for _add_env_overrides
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        # Patch os.getenv for the helper function
        monkeypatch.setenv("PROFILE_ARN", "arn:aws:codewhisperer:eu-central-1:123456789:profile/test")
        monkeypatch.setenv("KIRO_REGION", "eu-west-1")
        monkeypatch.setenv("KIRO_API_REGION", "eu-central-1")
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: overrides were added
        creds = json.loads(creds_file.read_text())
        print(f"Created credentials with overrides: {creds}")
        
        assert creds[0]["profile_arn"] == "arn:aws:codewhisperer:eu-central-1:123456789:profile/test"
        assert creds[0]["region"] == "eu-west-1"
        assert creds[0]["api_region"] == "eu-central-1"
        print("✓ Env overrides were added to credentials.json")
    
    @pytest.mark.asyncio
    async def test_lifespan_skip_migration_if_exists(self, tmp_path, monkeypatch):
        """
        Test 96: Пропуск миграции если credentials.json существует
        
        What it does: Verifies migration is skipped when credentials.json already exists
        Purpose: Prevent overwriting user-managed credentials
        """
        print("\n=== Test 96: Skip migration if credentials.json exists ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_refresh_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        # Pre-create credentials.json
        existing_creds = [{"type": "json", "path": "/existing/path.json"}]
        creds_file.write_text(json.dumps(existing_creds))
        print(f"Pre-existing credentials.json: {existing_creds}")
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: credentials.json was not modified
        final_creds = json.loads(creds_file.read_text())
        print(f"Final credentials.json: {final_creds}")
        
        assert final_creds == existing_creds
        print("✓ Migration was skipped, existing credentials.json preserved")


# =============================================================================
# Test Class: AccountManager Initialization
# =============================================================================

class TestLifespanAccountManagerInit:
    """
    Tests for AccountManager initialization and lifecycle.
    
    What it does: Verifies AccountManager creation, account initialization, and background tasks
    Purpose: Ensure proper startup and shutdown of Account System
    """
    
    @pytest.mark.asyncio
    async def test_lifespan_create_account_manager(self, tmp_path, monkeypatch):
        """
        Test 97: Создание AccountManager с правильными путями
        
        What it does: Verifies AccountManager is created with correct file paths
        Purpose: Ensure AccountManager receives proper configuration
        """
        print("\n=== Test 97: Create AccountManager with correct paths ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        # Track AccountManager creation
        manager_created_with = {}
        
        class MockAccountManager:
            def __init__(self, credentials_file, state_file):
                manager_created_with["credentials_file"] = credentials_file
                manager_created_with["state_file"] = state_file
                self._accounts = {"test": MagicMock()}
                self._current_account_index = 0
            
            async def load_credentials(self):
                pass
            
            async def load_state(self):
                pass
            
            async def _initialize_account(self, account_id):
                return True
            
            async def _save_state(self):
                pass
            
            async def save_state_periodically(self):
                await asyncio.sleep(1000)
        
        with patch("main.AccountManager", MockAccountManager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert
        print(f"AccountManager created with: {manager_created_with}")
        assert manager_created_with["credentials_file"] == str(creds_file)
        assert manager_created_with["state_file"] == str(state_file)
        print("✓ AccountManager created with correct paths")
    
    @pytest.mark.asyncio
    async def test_lifespan_load_credentials_and_state(self, tmp_path, monkeypatch):
        """
        Test 98: Вызов load_credentials() и load_state()
        
        What it does: Verifies that load methods are called during startup
        Purpose: Ensure credentials and state are loaded before initialization
        """
        print("\n=== Test 98: Call load_credentials() and load_state() ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        load_calls = {"credentials": False, "state": False}
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        
        async def track_load_credentials():
            load_calls["credentials"] = True
        
        async def track_load_state():
            load_calls["state"] = True
        
        mock_manager.load_credentials = track_load_credentials
        mock_manager.load_state = track_load_state
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert
        print(f"Load calls: {load_calls}")
        assert load_calls["credentials"] is True
        assert load_calls["state"] is True
        print("✓ load_credentials() and load_state() were called")
    
    @pytest.mark.asyncio
    async def test_lifespan_set_account_system_flag(self, tmp_path, monkeypatch):
        """
        Test 99: Установка app.state.account_system
        
        What it does: Verifies account_system flag is set in app.state
        Purpose: Ensure routes can check if account system is enabled
        """
        print("\n=== Test 99: Set app.state.account_system flag ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    # Check flag during lifespan
                    assert hasattr(app.state, "account_system")
                    assert app.state.account_system is True
                    print(f"✓ app.state.account_system = {app.state.account_system}")
    
    @pytest.mark.asyncio
    async def test_lifespan_initialize_first_working_account(self, tmp_path, monkeypatch):
        """
        Test 100: Инициализация первого рабочего аккаунта
        
        What it does: Verifies first working account is initialized at startup
        Purpose: Ensure at least one account is ready before accepting requests
        """
        print("\n=== Test 100: Initialize first working account ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        initialized_accounts = []
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {
            "account1": MagicMock(),
            "account2": MagicMock()
        }
        mock_manager._current_account_index = 0
        
        async def track_initialize(account_id):
            initialized_accounts.append(account_id)
            return True  # Success on first account
        
        mock_manager._initialize_account = track_initialize
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: only first account was initialized
        print(f"Initialized accounts: {initialized_accounts}")
        assert len(initialized_accounts) == 1
        assert initialized_accounts[0] == "account1"
        print("✓ First working account was initialized")
    
    @pytest.mark.asyncio
    async def test_lifespan_full_circle_initialization(self, tmp_path, monkeypatch):
        """
        Test 101: Попытка инициализации всех аккаунтов по кругу
        
        What it does: Verifies full circle attempt if first accounts fail
        Purpose: Ensure all accounts are tried before giving up
        """
        print("\n=== Test 101: Full circle initialization attempt ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        initialized_attempts = []
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {
            "account1": MagicMock(),
            "account2": MagicMock(),
            "account3": MagicMock()
        }
        mock_manager._current_account_index = 0
        
        async def track_initialize(account_id):
            initialized_attempts.append(account_id)
            # First two fail, third succeeds
            if account_id == "account3":
                return True
            return False
        
        mock_manager._initialize_account = track_initialize
        mock_manager._save_state = AsyncMock()
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: all three accounts were tried
        print(f"Initialization attempts: {initialized_attempts}")
        assert initialized_attempts == ["account1", "account2", "account3"]
        print("✓ Full circle initialization was attempted")
    
    @pytest.mark.asyncio
    async def test_lifespan_exit_if_no_accounts(self, tmp_path, monkeypatch):
        """
        Test 102: RuntimeError если нет аккаунтов в credentials.json
        
        What it does: Verifies application raises RuntimeError if no accounts configured
        Purpose: Prevent startup with empty configuration
        """
        print("\n=== Test 102: RuntimeError if no accounts configured ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {}  # Empty accounts dict
        mock_manager._current_account_index = 0
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                # Assert: RuntimeError is raised
                with pytest.raises(RuntimeError, match="No accounts configured"):
                    async with lifespan(app):
                        pass
                
                print("✓ RuntimeError was raised for empty accounts")
    
    @pytest.mark.asyncio
    async def test_lifespan_exit_if_all_failed(self, tmp_path, monkeypatch):
        """
        Test 103: RuntimeError если все аккаунты не инициализировались
        
        What it does: Verifies application raises RuntimeError if all accounts fail to initialize
        Purpose: Prevent startup without any working accounts
        """
        print("\n=== Test 103: RuntimeError if all accounts failed ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {
            "account1": MagicMock(),
            "account2": MagicMock()
        }
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=False)  # All fail
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                # Assert: RuntimeError is raised
                with pytest.raises(RuntimeError, match="Failed to initialize any account"):
                    async with lifespan(app):
                        pass
                
                print("✓ RuntimeError was raised when all accounts failed")
    
    @pytest.mark.asyncio
    async def test_lifespan_save_initial_state(self, tmp_path, monkeypatch):
        """
        Test 104: Сохранение начального state.json
        
        What it does: Verifies initial state is saved after first account initialization
        Purpose: Ensure state persistence starts immediately
        """
        print("\n=== Test 104: Save initial state ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        save_state_called = False
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        
        async def track_save_state():
            nonlocal save_state_called
            save_state_called = True
        
        mock_manager._save_state = track_save_state
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert
        print(f"_save_state called: {save_state_called}")
        assert save_state_called is True
        print("✓ Initial state was saved")
    
    @pytest.mark.asyncio
    async def test_lifespan_start_background_task(self, tmp_path, monkeypatch):
        """
        Test 105: Запуск save_state_periodically()
        
        What it does: Verifies background task is started for periodic state saving
        Purpose: Ensure state is saved periodically during runtime
        """
        print("\n=== Test 105: Start background task ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        periodic_task_started = False
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        
        async def track_periodic_save():
            nonlocal periodic_task_started
            periodic_task_started = True
            await asyncio.sleep(1000)  # Long sleep to keep task alive
        
        mock_manager.save_state_periodically = track_periodic_save
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    # Give task time to start
                    await asyncio.sleep(0.1)
                    assert periodic_task_started is True
                    print("✓ Background task was started")
    
    @pytest.mark.asyncio
    async def test_lifespan_shutdown_cancel_task(self, tmp_path, monkeypatch):
        """
        Test 106: Отмена background task при shutdown
        
        What it does: Verifies background task is cancelled during shutdown
        Purpose: Ensure clean shutdown without hanging tasks
        """
        print("\n=== Test 106: Cancel background task on shutdown ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        task_cancelled = False
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        mock_manager._save_state = AsyncMock()
        
        async def periodic_save_with_cancel_check():
            try:
                await asyncio.sleep(1000)
            except asyncio.CancelledError:
                nonlocal task_cancelled
                task_cancelled = True
                raise
        
        mock_manager.save_state_periodically = periodic_save_with_cancel_check
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    await asyncio.sleep(0.1)
                
                # After context exit, task should be cancelled
                await asyncio.sleep(0.1)
        
        # Assert
        print(f"Task cancelled: {task_cancelled}")
        assert task_cancelled is True
        print("✓ Background task was cancelled on shutdown")
    
    @pytest.mark.asyncio
    async def test_lifespan_shutdown_final_save(self, tmp_path, monkeypatch):
        """
        Test 107: Финальное сохранение state.json при shutdown
        
        What it does: Verifies final state save happens during shutdown
        Purpose: Ensure no state is lost on graceful shutdown
        """
        print("\n=== Test 107: Final save on shutdown ===")
        
        # Arrange: Patch constants
        monkeypatch.setattr("main.ACCOUNT_SYSTEM", True)
        monkeypatch.setattr("main.REFRESH_TOKEN", "test_token")
        monkeypatch.setattr("main.KIRO_CREDS_FILE", None)
        monkeypatch.setattr("main.KIRO_CLI_DB_FILE", None)
        
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        monkeypatch.setattr("main.ACCOUNTS_CONFIG_FILE", str(creds_file))
        monkeypatch.setattr("main.ACCOUNTS_STATE_FILE", str(state_file))
        
        save_calls = []
        
        mock_manager = AsyncMock()
        mock_manager._accounts = {"test": MagicMock()}
        mock_manager._current_account_index = 0
        mock_manager._initialize_account = AsyncMock(return_value=True)
        
        async def track_save_state():
            save_calls.append("save")
        
        mock_manager._save_state = track_save_state
        mock_manager.save_state_periodically = AsyncMock()
        
        with patch("main.AccountManager", return_value=mock_manager):
            with patch("main.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client
                
                from main import lifespan, app
                
                async with lifespan(app):
                    pass
        
        # Assert: at least 2 saves (initial + final)
        print(f"Save calls: {len(save_calls)}")
        assert len(save_calls) >= 2
        print("✓ Final state save was performed on shutdown")
