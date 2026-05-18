# -*- coding: utf-8 -*-

"""
Integration tests for Account System failover flow.

Tests cover:
- Full failover between multiple accounts
- Sticky behavior (global index)
- Circuit Breaker with exponential backoff
- Half-Open recovery
- State persistence across restarts
- TTL refresh on usage
"""

import asyncio
import json
import pytest
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

from kiro.account_manager import AccountManager, Account, AccountStats
from kiro.account_errors import ErrorType


# =============================================================================
# Integration Tests: Full Failover Flow
# =============================================================================

class TestAccountSystemFullFlow:
    """
    Integration tests for complete Account System flow.
    
    What it does: Tests end-to-end failover scenarios with multiple accounts
    Purpose: Verify Account System works correctly in realistic scenarios
    """
    
    @pytest.mark.asyncio
    async def test_full_failover_flow_two_accounts(
        self,
        tmp_path,
        temp_account_credentials_files,
        mock_list_models_response
    ):
        """
        Test 137: Полный failover между двумя аккаунтами
        
        What it does: Simulates complete failover from broken account to working one
        Purpose: Verify failover loop works end-to-end
        """
        print("\n=== Test 137: Full failover flow between two accounts ===")
        
        # Arrange: Create credentials.json with two accounts
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        account2_path = temp_account_credentials_files["account2"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True},
            {"type": "json", "path": account2_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        # Create AccountManager
        manager = AccountManager(str(creds_file), str(state_file))
        await manager.load_credentials()
        await manager.load_state()
        
        print(f"Loaded {len(manager._accounts)} accounts")
        
        # Mock initialization for both accounts
        with patch.object(manager, '_initialize_account') as mock_init:
            async def mock_initialize(account_id):
                # Create mock components
                from kiro.auth import KiroAuthManager
                from kiro.cache import ModelInfoCache
                from kiro.model_resolver import ModelResolver
                
                account = manager._accounts[account_id]
                
                # Mock auth_manager
                auth_manager = MagicMock(spec=KiroAuthManager)
                auth_manager._access_token = f"token_{account_id}"
                auth_manager.q_host = "https://api.example.com"
                auth_manager.api_host = "https://api.example.com"
                
                # Mock model_cache with models
                model_cache = ModelInfoCache()
                await model_cache.update(mock_list_models_response["models"])
                
                # Mock model_resolver
                model_resolver = ModelResolver(
                    cache=model_cache,
                    hidden_models={},
                    aliases={},
                    hidden_from_list=set()
                )
                
                account.auth_manager = auth_manager
                account.model_cache = model_cache
                account.model_resolver = model_resolver
                account.models_cached_at = time.time()
                
                # Update model_to_accounts
                for model in model_resolver.get_available_models():
                    if model not in manager._model_to_accounts:
                        from kiro.account_manager import ModelAccountList
                        manager._model_to_accounts[model] = ModelAccountList()
                    if account_id not in manager._model_to_accounts[model].accounts:
                        manager._model_to_accounts[model].accounts.append(account_id)
                
                return True
            
            mock_init.side_effect = mock_initialize
            
            # Initialize both accounts
            for account_id in list(manager._accounts.keys()):
                await manager._initialize_account(account_id)
        
        print(f"Initialized accounts: {list(manager._accounts.keys())}")
        
        # Act: Simulate failover scenario
        # 1. First account fails with RECOVERABLE error
        account1_id = list(manager._accounts.keys())[0]
        await manager.report_failure(
            account1_id,
            "claude-opus-4.5",
            ErrorType.RECOVERABLE,
            429,
            None
        )
        print(f"Account 1 failed: failures={manager._accounts[account1_id].failures}")
        
        # 2. Get next account (should return account2)
        # Mock random.random() to disable probabilistic retry (make test deterministic)
        with patch('random.random', return_value=0.5):  # > 0.1 = no probabilistic retry
            next_account = await manager.get_next_account("claude-opus-4.5")
        account2_id = list(manager._accounts.keys())[1]
        
        print(f"Next account: {next_account.id if next_account else None}")
        assert next_account is not None
        assert next_account.id == account2_id
        
        # 3. Second account succeeds
        await manager.report_success(account2_id, "claude-opus-4.5")
        print(f"Account 2 succeeded: failures={manager._accounts[account2_id].failures}")
        
        # 4. Verify sticky behavior - should prefer account2 now
        next_account_again = await manager.get_next_account("claude-opus-4.5")
        print(f"Next account (sticky): {next_account_again.id if next_account_again else None}")
        assert next_account_again.id == account2_id
        
        print("✓ Full failover flow completed successfully")
    
    @pytest.mark.asyncio
    async def test_sticky_behavior_success_updates_index(
        self,
        tmp_path,
        temp_account_credentials_files,
        mock_list_models_response
    ):
        """
        Test 138: Sticky behavior обновляет global index
        
        What it does: Verifies global current_account_index is updated on success
        Purpose: Ensure sticky behavior works across all models
        """
        print("\n=== Test 138: Sticky behavior updates global index ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        account2_path = temp_account_credentials_files["account2"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True},
            {"type": "json", "path": account2_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(str(creds_file), str(state_file))
        await manager.load_credentials()
        await manager.load_state()
        
        # Initialize accounts (simplified)
        for account_id in list(manager._accounts.keys()):
            account = manager._accounts[account_id]
            account.auth_manager = MagicMock()
            account.model_cache = MagicMock()
            account.model_resolver = MagicMock()
            account.model_resolver.get_available_models.return_value = ["claude-opus-4.5"]
            account.models_cached_at = time.time()
            
            from kiro.account_manager import ModelAccountList
            if "claude-opus-4.5" not in manager._model_to_accounts:
                manager._model_to_accounts["claude-opus-4.5"] = ModelAccountList()
            manager._model_to_accounts["claude-opus-4.5"].accounts.append(account_id)
        
        print(f"Initial global index: {manager._current_account_index}")
        assert manager._current_account_index == 0
        
        # Act: Report success on second account
        account2_id = list(manager._accounts.keys())[1]
        await manager.report_success(account2_id, "claude-opus-4.5")
        
        # Assert: Global index updated to 1
        print(f"Updated global index: {manager._current_account_index}")
        assert manager._current_account_index == 1
        print("✓ Global index was updated on success")
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_broken_account(
        self,
        tmp_path,
        temp_account_credentials_files,
        mock_time
    ):
        """
        Test 139: Circuit Breaker блокирует сломанный аккаунт
        
        What it does: Verifies broken account is skipped during cooldown
        Purpose: Ensure Circuit Breaker prevents using broken accounts
        """
        print("\n=== Test 139: Circuit Breaker blocks broken account ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        account2_path = temp_account_credentials_files["account2"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True},
            {"type": "json", "path": account2_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(str(creds_file), str(state_file))
        await manager.load_credentials()
        await manager.load_state()
        
        # Initialize accounts
        for account_id in list(manager._accounts.keys()):
            account = manager._accounts[account_id]
            account.auth_manager = MagicMock()
            account.model_cache = MagicMock()
            account.model_resolver = MagicMock()
            account.model_resolver.get_available_models.return_value = ["claude-opus-4.5"]
            account.models_cached_at = time.time()
            
            from kiro.account_manager import ModelAccountList
            if "claude-opus-4.5" not in manager._model_to_accounts:
                manager._model_to_accounts["claude-opus-4.5"] = ModelAccountList()
            manager._model_to_accounts["claude-opus-4.5"].accounts.append(account_id)
        
        # Act: Break first account (5 failures)
        account1_id = list(manager._accounts.keys())[0]
        for i in range(5):
            await manager.report_failure(
                account1_id,
                "claude-opus-4.5",
                ErrorType.RECOVERABLE,
                429,
                None
            )
        
        print(f"Account 1 failures: {manager._accounts[account1_id].failures}")
        print(f"Last failure time: {manager._accounts[account1_id].last_failure_time}")
        
        # Get next account - should skip account1 (in cooldown)
        with patch('random.random', return_value=0.5):  # Disable probabilistic retry
            next_account = await manager.get_next_account("claude-opus-4.5")
        
        account2_id = list(manager._accounts.keys())[1]
        print(f"Next account: {next_account.id if next_account else None}")
        assert next_account.id == account2_id
        print("✓ Broken account was skipped (Circuit Breaker)")
    
    @pytest.mark.asyncio
    async def test_half_open_recovery_after_timeout(
        self,
        tmp_path,
        temp_account_credentials_files
    ):
        """
        Test 140: Half-Open восстанавливает аккаунт после timeout
        
        What it does: Verifies broken account is retried after recovery timeout
        Purpose: Ensure accounts can recover from broken state
        """
        print("\n=== Test 140: Half-Open recovery after timeout ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(str(creds_file), str(state_file))
        await manager.load_credentials()
        await manager.load_state()
        
        # Initialize account
        account_id = list(manager._accounts.keys())[0]
        account = manager._accounts[account_id]
        account.auth_manager = MagicMock()
        account.model_cache = MagicMock()
        account.model_resolver = MagicMock()
        account.model_resolver.get_available_models.return_value = ["claude-opus-4.5"]
        account.models_cached_at = time.time()
        
        from kiro.account_manager import ModelAccountList
        manager._model_to_accounts["claude-opus-4.5"] = ModelAccountList()
        manager._model_to_accounts["claude-opus-4.5"].accounts.append(account_id)
        
        # Act: Break account
        for i in range(3):
            await manager.report_failure(
                account_id,
                "claude-opus-4.5",
                ErrorType.RECOVERABLE,
                429,
                None
            )
        
        print(f"Account failures: {account.failures}")
        print(f"Last failure time: {account.last_failure_time}")
        
        # Simulate time passing (recovery timeout)
        from kiro.config import ACCOUNT_RECOVERY_TIMEOUT, ACCOUNT_MAX_BACKOFF_MULTIPLIER
        backoff_multiplier = min(2 ** (account.failures - 1), ACCOUNT_MAX_BACKOFF_MULTIPLIER)
        effective_timeout = ACCOUNT_RECOVERY_TIMEOUT * backoff_multiplier
        
        account.last_failure_time = time.time() - effective_timeout - 1
        print(f"Simulated time passing: {effective_timeout + 1}s")
        
        # Get next account - should return account (Half-Open)
        next_account = await manager.get_next_account("claude-opus-4.5")
        
        print(f"Next account (Half-Open): {next_account.id if next_account else None}")
        assert next_account is not None
        assert next_account.id == account_id
        print("✓ Account recovered via Half-Open state")
    
    @pytest.mark.asyncio
    async def test_state_persistence_across_restarts(
        self,
        tmp_path,
        temp_account_credentials_files
    ):
        """
        Test 141: state.json сохраняется и восстанавливается
        
        What it does: Verifies state persists across manager restarts
        Purpose: Ensure runtime state survives restarts
        """
        print("\n=== Test 141: State persistence across restarts ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        # First manager instance
        manager1 = AccountManager(str(creds_file), str(state_file))
        await manager1.load_credentials()
        await manager1.load_state()
        
        # Initialize account
        account_id = list(manager1._accounts.keys())[0]
        account = manager1._accounts[account_id]
        account.auth_manager = MagicMock()
        account.model_cache = MagicMock()
        account.model_resolver = MagicMock()
        account.model_resolver.get_available_models.return_value = ["claude-opus-4.5"]
        account.models_cached_at = 1704110400.0
        
        from kiro.account_manager import ModelAccountList
        manager1._model_to_accounts["claude-opus-4.5"] = ModelAccountList()
        manager1._model_to_accounts["claude-opus-4.5"].accounts.append(account_id)
        
        # Modify state
        account.failures = 3
        account.last_failure_time = 1704114000.0
        account.stats.total_requests = 100
        account.stats.successful_requests = 97
        account.stats.failed_requests = 3
        manager1._current_account_index = 0
        
        # Save state
        await manager1._save_state()
        print(f"Saved state: failures={account.failures}, stats={account.stats.total_requests}")
        
        # Second manager instance (restart simulation)
        manager2 = AccountManager(str(creds_file), str(state_file))
        await manager2.load_credentials()
        await manager2.load_state()
        
        # Assert: State was restored
        account2 = manager2._accounts[account_id]
        print(f"Restored state: failures={account2.failures}, stats={account2.stats.total_requests}")
        
        assert account2.failures == 3
        assert account2.last_failure_time == 1704114000.0
        assert account2.models_cached_at == 1704110400.0
        assert account2.stats.total_requests == 100
        assert account2.stats.successful_requests == 97
        assert account2.stats.failed_requests == 3
        assert manager2._current_account_index == 0
        
        print("✓ State was persisted and restored correctly")
    
    @pytest.mark.asyncio
    async def test_ttl_refresh_on_usage(
        self,
        tmp_path,
        temp_account_credentials_files,
        mock_list_models_response
    ):
        """
        Test 142: TTL обновляется только при использовании аккаунта
        
        What it does: Verifies model cache is refreshed when TTL expires during usage
        Purpose: Ensure cache stays fresh without background tasks
        """
        print("\n=== Test 142: TTL refresh on usage ===")
        
        # Arrange
        creds_file = tmp_path / "credentials.json"
        state_file = tmp_path / "state.json"
        
        account1_path = temp_account_credentials_files["account1"]
        
        credentials = [
            {"type": "json", "path": account1_path, "enabled": True}
        ]
        creds_file.write_text(json.dumps(credentials))
        
        manager = AccountManager(str(creds_file), str(state_file))
        await manager.load_credentials()
        await manager.load_state()
        
        # Initialize account
        account_id = list(manager._accounts.keys())[0]
        account = manager._accounts[account_id]
        account.auth_manager = MagicMock()
        account.model_cache = MagicMock()
        account.model_resolver = MagicMock()
        account.model_resolver.get_available_models.return_value = ["claude-opus-4.5"]
        
        # Set old cache timestamp (expired TTL)
        from kiro.config import ACCOUNT_CACHE_TTL
        account.models_cached_at = time.time() - ACCOUNT_CACHE_TTL - 1
        print(f"Cache age: {time.time() - account.models_cached_at}s (TTL: {ACCOUNT_CACHE_TTL}s)")
        
        from kiro.account_manager import ModelAccountList
        manager._model_to_accounts["claude-opus-4.5"] = ModelAccountList()
        manager._model_to_accounts["claude-opus-4.5"].accounts.append(account_id)
        
        # Mock refresh method
        refresh_called = False
        original_cached_at = account.models_cached_at
        
        async def mock_refresh(acc_id):
            nonlocal refresh_called
            refresh_called = True
            manager._accounts[acc_id].models_cached_at = time.time()
        
        with patch.object(manager, '_refresh_account_models', side_effect=mock_refresh):
            # Act: Get account (should trigger TTL refresh)
            next_account = await manager.get_next_account("claude-opus-4.5")
        
        # Assert: Refresh was called and timestamp updated
        print(f"Refresh called: {refresh_called}")
        print(f"Old timestamp: {original_cached_at}")
        print(f"New timestamp: {account.models_cached_at}")
        
        assert refresh_called is True
        assert account.models_cached_at > original_cached_at
        print("✓ Cache was refreshed on usage when TTL expired")
