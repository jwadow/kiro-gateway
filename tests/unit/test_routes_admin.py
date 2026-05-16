# -*- coding: utf-8 -*-

"""
Tests for kiro/routes_admin.py - small web management panel.

The admin panel is intentionally narrow: login with PROXY_API_KEY, add/delete
multi-account credential entries, and render sanitized account statistics.
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kiro.routes_admin import SESSION_COOKIE_NAME, router


class FakeAccountManager:
    """
    Minimal account manager test double for admin route tests.
    """

    def __init__(self) -> None:
        """Initialize captured calls and a realistic panel snapshot."""
        self.added_entries: List[Dict[str, Any]] = []
        self.deleted_indexes: List[int] = []
        self.add_credentials_entries = AsyncMock(side_effect=self._add_credentials_entries)
        self.delete_credentials_entry = AsyncMock(side_effect=self._delete_credentials_entry)

    def get_management_snapshot(self) -> Dict[str, Any]:
        """
        Return a sanitized management snapshot for HTML rendering.

        Returns:
            Snapshot dictionary consumed by the admin panel renderer.
        """
        return {
            "credentials_file": "credentials.json",
            "state_file": "state.json",
            "credentials": [
                {
                    "index": 0,
                    "entry": {
                        "type": "refresh_token",
                        "refresh_token": "abcd...wxyz",
                        "enabled": True,
                    },
                }
            ],
            "accounts": [
                {
                    "id": "refresh_token_abc123",
                    "initialized": True,
                    "failures": 0,
                    "last_failure_time": 0.0,
                    "models_cached_at": 0.0,
                    "available_model_count": 3,
                    "stats": {
                        "total_requests": 5,
                        "successful_requests": 4,
                        "failed_requests": 1,
                    },
                }
            ],
            "model_mapping_count": 3,
            "current_account_index": 0,
            "totals": {
                "configured_entries": 1,
                "loaded_accounts": 1,
                "initialized_accounts": 1,
                "total_requests": 5,
                "successful_requests": 4,
                "failed_requests": 1,
            },
        }

    async def _add_credentials_entries(self, entries: List[Dict[str, Any]]) -> None:
        """
        Capture entries passed to the add-account endpoint.

        Args:
            entries: Parsed credential entries.
        """
        self.added_entries.extend(entries)

    async def _delete_credentials_entry(self, index: int) -> None:
        """
        Capture indexes passed to the delete-account endpoint.

        Args:
            index: Credential entry index.
        """
        self.deleted_indexes.append(index)


def create_admin_test_client(account_system: bool = True) -> TestClient:
    """
    Create an isolated FastAPI app with the admin router mounted.

    Args:
        account_system: Whether the app should allow account mutations.

    Returns:
        FastAPI TestClient with fake account manager state.
    """
    app = FastAPI()
    app.include_router(router)
    app.state.account_manager = FakeAccountManager()
    app.state.account_system = account_system
    return TestClient(app, follow_redirects=False)


def login(client: TestClient) -> None:
    """
    Authenticate a test client with the configured default PROXY_API_KEY.

    Args:
        client: Test client to authenticate.
    """
    response = client.post("/admin/login", data={"token": "my-super-secret-password-123"})
    assert response.status_code == 303
    assert SESSION_COOKIE_NAME in client.cookies


class TestAdminAuthentication:
    """
    Tests for admin panel authentication behavior.
    """

    def test_login_page_renders_without_session(self) -> None:
        """
        Test login page is shown to anonymous users.

        What it does: Requests /admin/login without a session
        Purpose: Verify the panel exposes a login form before authentication
        """
        client = create_admin_test_client()

        response = client.get("/admin/login")

        assert response.status_code == 200
        assert "Use the configured PROXY_API_KEY" in response.text
        assert "Sign in" in response.text

    def test_admin_redirects_without_session(self) -> None:
        """
        Test anonymous panel access redirects to login.

        What it does: Requests /admin without a valid session
        Purpose: Prevent unauthenticated access to account data
        """
        client = create_admin_test_client()

        response = client.get("/admin")

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"

    def test_login_rejects_invalid_proxy_api_key(self) -> None:
        """
        Test invalid PROXY_API_KEY is rejected.

        What it does: Posts a wrong token to /admin/login
        Purpose: Ensure only the configured proxy key opens the panel
        """
        client = create_admin_test_client()

        response = client.post("/admin/login", data={"token": "wrong-token"})

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin/login?error=")
        assert SESSION_COOKIE_NAME not in client.cookies

    def test_login_accepts_proxy_api_key_and_sets_session(self) -> None:
        """
        Test PROXY_API_KEY grants access to the panel.

        What it does: Logs in with the configured default proxy key
        Purpose: Verify the panel uses PROXY_API_KEY as requested
        """
        client = create_admin_test_client()

        login(client)
        response = client.get("/admin")

        assert response.status_code == 200
        assert "Kiro Gateway Admin" in response.text
        assert "Runtime statistics" in response.text
        assert "refresh_token_abc123" in response.text


class TestAdminAccountMutations:
    """
    Tests for add/delete account management endpoints.
    """

    def test_add_account_accepts_single_json_object(self) -> None:
        """
        Test adding one credential object.

        What it does: Posts a JSON object to /admin/accounts
        Purpose: Verify common paste-one-account workflow
        """
        client = create_admin_test_client(account_system=True)
        login(client)

        response = client.post(
            "/admin/accounts",
            data={"account_json": '{"type":"json","path":"~/account.json","enabled":true}'},
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin?message=")
        manager = client.app.state.account_manager
        assert manager.add_credentials_entries.await_count == 1
        assert manager.added_entries == [{"type": "json", "path": "~/account.json", "enabled": True}]

    def test_add_account_accepts_raw_kiro_auth_token_json(self) -> None:
        """
        Test adding a raw kiro-auth-token.json object.

        What it does: Posts Kiro IDE token JSON to /admin/accounts
        Purpose: Verify the web panel accepts the format users copy from kiro-auth-token.json
        """
        client = create_admin_test_client(account_system=True)
        login(client)

        response = client.post(
            "/admin/accounts",
            data={
                "account_json": (
                    '{"accessToken":"access-token","refreshToken":"refresh-token",'
                    '"profileArn":"arn:aws:codewhisperer:us-east-1:123456789012:profile/test",'
                    '"expiresAt":"2026-05-16T09:45:03.903Z",'
                    '"authMethod":"social","provider":"Google"}'
                )
            },
        )

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin?message=")
        manager = client.app.state.account_manager
        assert manager.add_credentials_entries.await_count == 1
        assert manager.added_entries == [
            {
                "accessToken": "access-token",
                "refreshToken": "refresh-token",
                "profileArn": "arn:aws:codewhisperer:us-east-1:123456789012:profile/test",
                "expiresAt": "2026-05-16T09:45:03.903Z",
                "authMethod": "social",
                "provider": "Google",
            }
        ]

    def test_admin_panel_mentions_raw_kiro_auth_token_json(self) -> None:
        """
        Test panel UI explains raw token JSON upload.

        What it does: Renders /admin after login
        Purpose: Ensure users can discover the supported kiro-auth-token.json format
        """
        client = create_admin_test_client(account_system=True)
        login(client)

        response = client.get("/admin")

        assert response.status_code == 200
        assert "raw kiro-auth-token.json" in response.text
        assert "refreshToken" in response.text
        assert "profileArn" in response.text

    def test_add_account_rejects_invalid_json(self) -> None:
        """
        Test malformed account JSON is rejected.

        What it does: Posts broken JSON to /admin/accounts
        Purpose: Ensure invalid user input does not reach persistence layer
        """
        client = create_admin_test_client(account_system=True)
        login(client)

        response = client.post("/admin/accounts", data={"account_json": "{"})

        assert response.status_code == 303
        assert "error=" in response.headers["location"]
        manager = client.app.state.account_manager
        assert manager.add_credentials_entries.await_count == 0

    def test_add_account_requires_multi_account_mode(self) -> None:
        """
        Test add endpoint is disabled outside multi-account mode.

        What it does: Posts valid JSON when account_system is false
        Purpose: Keep panel mutations aligned with ACCOUNT_SYSTEM=true
        """
        client = create_admin_test_client(account_system=False)
        login(client)

        response = client.post(
            "/admin/accounts",
            data={"account_json": '{"type":"json","path":"~/account.json"}'},
        )

        assert response.status_code == 303
        assert "ACCOUNT_SYSTEM" in response.headers["location"]
        manager = client.app.state.account_manager
        assert manager.add_credentials_entries.await_count == 0

    def test_delete_account_calls_manager_with_index(self) -> None:
        """
        Test deleting a credential entry.

        What it does: Posts a credential index to /admin/accounts/delete
        Purpose: Verify delete requests are delegated to AccountManager
        """
        client = create_admin_test_client(account_system=True)
        login(client)

        response = client.post("/admin/accounts/delete", data={"index": "0"})

        assert response.status_code == 303
        assert response.headers["location"].startswith("/admin?message=")
        manager = client.app.state.account_manager
        assert manager.delete_credentials_entry.await_count == 1
        assert manager.deleted_indexes == [0]

    def test_delete_account_requires_authentication(self) -> None:
        """
        Test delete endpoint redirects anonymous users.

        What it does: Posts a delete request without logging in
        Purpose: Prevent cross-site or anonymous credential deletion
        """
        client = create_admin_test_client(account_system=True)

        response = client.post("/admin/accounts/delete", data={"index": "0"})

        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        manager = client.app.state.account_manager
        assert manager.delete_credentials_entry.await_count == 0
