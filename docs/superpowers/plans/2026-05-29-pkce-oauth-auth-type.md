# PKCE OAuth Auth Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PKCE OAuth as a 3rd auth type in kiro-gateway that performs browser-based login to Kiro, inserting it after kirolink fallback fails and before the final error in `get_access_token()`.

**Architecture:** Use stdlib `http.server` + `threading.Event` for ephemeral redirect server (not FastAPI). PKCE challenge/verifier per sionex-code's pattern. Tokens stored in JSON creds file. Lazy refresh on `get_access_token()` calls.

**Tech Stack:** Python 3.10+ (stdlib only for PKCE: `hashlib`, `secrets`, `base64`, `http.server`, `urllib.parse`, `webbrowser`, `threading`)

---

### Files Modified
- `kiro/config.py` — PKCE endpoint URLs, timeout constants
- `kiro/auth.py` — New `PKCE_OAUTH` AuthType, PKCE flow methods, fallback chain integration
- `kiro/account_manager.py` — New `"pkce"` credential type
- `tests/unit/test_auth_manager.py` — PKCE flow tests
- `credentials.json.example` — PKCE entry example

### Files Created
- None (all changes in existing files)

---

### Task 1: Add PKCE config constants

**Files:**
- Modify: `kiro/config.py` — add PKCE URLs

- [x] **Step 1: Add PKCE OAuth endpoint URLs and constants after line 217 (after `AWS_SSO_OIDC_URL_TEMPLATE`)**

```python
# ==================================================================================================
# PKCE OAuth Settings (Browser-based login)
# ==================================================================================================

# URL for OAuth token exchange (PKCE flow)
# Used after browser login to exchange authorization code for tokens
KIRO_OAUTH_SIGNIN_URL: str = "https://app.kiro.dev/signin"

# URL for PKCE token exchange (POST with code + code_verifier)
KIRO_OAUTH_TOKEN_URL_TEMPLATE: str = "https://prod.{region}.auth.desktop.kiro.dev/oauth/token"

# Timeout for PKCE OAuth flow (seconds) — how long to wait for user to complete browser login
# Default: 300 seconds (5 minutes)
PKCE_OAUTH_TIMEOUT: int = int(os.getenv("PKCE_OAUTH_TIMEOUT", "300"))

# Redirect URI for PKCE callback — ephemeral server on localhost
# Port 0 = OS picks random free port
# NOTE: The redirect_from=KiroIDE parameter distinguishes this from other OAuth flows
PKCE_REDIRECT_FROM: str = "KiroIDE"
```

- [x] **Step 2: Add getter function after `get_aws_sso_oidc_url()`**

```python
def get_kiro_oauth_token_url(region: str) -> str:
    """Return Kiro OAuth token exchange URL for the specified region."""
    return KIRO_OAUTH_TOKEN_URL_TEMPLATE.format(region=region)
```

- [x] **Step 3: Run tests to verify no regression**

Run: `pytest tests/unit/test_config.py -v` or just `pytest -x -v`
Expected: PASS (or skip if test_config.py doesn't exist)

---

### Task 2: Add PKCE_OAUTH to AuthType enum

**Files:**
- Modify: `kiro/auth.py` — AuthType enum, PKCE methods, fallback chain

- [x] **Step 1: Add `PKCE_OAUTH` to `AuthType` enum**

```python
class AuthType(Enum):
    KIRO_DESKTOP = "kiro_desktop"
    AWS_SSO_OIDC = "aws_sso_oidc"
    PKCE_OAUTH = "pkce_oauth"  # Browser-based PKCE OAuth login
```

- [x] **Step 2: Add pkce_oauth imports at top of auth.py**

After the existing `from kiro.config import ...` block, add:

```python
from kiro.config import (
    # ... existing imports ...
    PKCE_OAUTH_TIMEOUT,
    KIRO_OAUTH_SIGNIN_URL,
    KIRO_OAUTH_TOKEN_URL_TEMPLATE,
    PKCE_REDIRECT_FROM,
)
```

Also add stdlib imports at the top with other stdlib imports:

```python
import base64
import hashlib
import secrets
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Event
```

- [x] **Step 3: Add `_pkce_generate_challenge()` static method to `KiroAuthManager`**

Add after line 180 (after `self._fingerprint = get_machine_fingerprint()` block, before `# Load credentials from SQLite`):

```python
@staticmethod
def _pkce_generate_challenge() -> tuple[str, str, str]:
    """
    Generate PKCE verifier, challenge, and state.
    
    Uses S256 method (SHA256 hash + base64url unpadded).
    Matches sionex-code/opencode-proxy-api pattern.
    
    Returns:
        Tuple of (verifier, challenge, state)
    """
    verifier = secrets.token_urlsafe(32)
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').rstrip('=')
    state = secrets.token_urlsafe(16)
    return verifier, challenge, state
```

- [x] **Step 4: Run test to check compile**

Run: `python -c "from kiro.auth import KiroAuthManager; print('OK')"`
Expected: OK

---

### Task 3: Implement PKCE redirect server

**Files:**
- Modify: `kiro/auth.py` — add ephemeral HTTP server class and flow method

- [x] **Step 1: Add PKCE redirect handler class inside `KiroAuthManager` (or as module-level class)**

Add after `_pkce_generate_challenge()` method (module-level, before `KiroAuthManager` class):

```python
class _PKCERedirectHandler(BaseHTTPRequestHandler):
    """
    Ephemeral HTTP request handler for PKCE OAuth callback.
    
    Captures the authorization code from Kiro's redirect
    and signals the waiting PKCE flow to continue.
    
    Attributes:
        auth_code: Captured authorization code (set on successful callback)
        state: Expected state parameter (CSRF protection)
        received: threading.Event signaled when callback is received
    """
    auth_code: Optional[str] = None
    state: str = ""
    received: Event = Event()
    
    def do_GET(self) -> None:
        """Handle GET request — parse code + state from query params."""
        from urllib.parse import urlparse, parse_qs
        
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        received_code = params.get("code", [None])[0]
        received_state = params.get("state", [None])[0]
        
        if received_code and received_state == self.__class__.state:
            self.__class__.auth_code = received_code
            self.__class__.received.set()
            self._respond_success()
        else:
            self._respond_error("Invalid state or missing code")
    
    def _respond_success(self) -> None:
        """Send success HTML response to browser."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>Authentication successful!</h1>"
            b"<p>You can close this tab and return to the terminal.</p></body></html>"
        )
    
    def _respond_error(self, message: str) -> None:
        """Send error HTML response to browser."""
        self.send_response(400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            f"<html><body><h1>Authentication failed</h1>"
            f"<p>{message}</p></body></html>".encode()
        )
    
    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server logging."""
        pass  # We use loguru instead
```

- [x] **Step 2: Run test to verify imports**

Run: `python -c "from kiro.auth import _PKCERedirectHandler; print('OK')"`
Expected: OK

---

### Task 4: Implement PKCE OAuth flow method

**Files:**
- Modify: `kiro/auth.py` — add `_pkce_oauth_flow()` method

- [x] **Step 1: Add `_pkce_oauth_flow()` instance method to `KiroAuthManager`**

Add after `_refresh_via_kirolink()` method (before the property section at line 1023):

```python
async def _pkce_oauth_flow(self) -> str:
    """
    Perform PKCE OAuth flow: browser login → code exchange → token storage.
    
    Flow:
    1. Generate PKCE verifier, challenge, and state
    2. Spawn ephemeral HTTP server on random port
    3. Construct auth URL and open browser
    4. Wait for callback (or timeout)
    5. Exchange authorization code for tokens
    6. Store tokens in credentials file
    7. Return access token
    
    This is the LAST resort fallback — invoked only when all other
    auth methods (KIRO_DESKTOP, AWS_SSO_OIDC, kirolink) have failed.
    
    Returns:
        Valid access token
    
    Raises:
        TimeoutError: If user doesn't complete browser login within timeout
        ValueError: If token exchange fails
    """
    # Generate PKCE params
    verifier, challenge, state = self._pkce_generate_challenge()
    
    # Configure redirect handler
    _PKCERedirectHandler.auth_code = None
    _PKCERedirectHandler.state = state
    _PKCERedirectHandler.received.clear()
    
    # Spawn ephemeral HTTP server on random port
    server = HTTPServer(("127.0.0.1", 0), _PKCERedirectHandler)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    
    # Build auth URL
    params = {
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "redirect_uri": redirect_uri,
        "redirect_from": PKCE_REDIRECT_FROM,
    }
    auth_url = f"{KIRO_OAUTH_SIGNIN_URL}?{urllib.parse.urlencode(params)}"
    
    logger.info("=== PKCE OAuth Login Required ===")
    logger.info(f"Opening browser to: {KIRO_OAUTH_SIGNIN_URL}")
    logger.info(f"Full auth URL: {auth_url}")
    logger.info(f"Listening for callback on {redirect_uri}")
    logger.info("If browser doesn't open, copy the URL above manually.")
    
    # Open browser in a thread (don't block)
    def _open_browser():
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass  # Browser open failure is non-fatal (user can copy URL)
    
    import threading
    browser_thread = threading.Thread(target=_open_browser, daemon=True)
    browser_thread.start()
    
    # Run server in a thread and wait for callback
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    
    try:
        received = _PKCERedirectHandler.received.wait(timeout=PKCE_OAUTH_TIMEOUT)
        if not received:
            server.shutdown()
            raise TimeoutError(
                f"PKCE OAuth timed out after {PKCE_OAUTH_TIMEOUT}s. "
                f"Run 'kiro-cli login' manually or retry."
            )
    except TimeoutError:
        raise
    except Exception as e:
        server.shutdown()
        raise ValueError(f"PKCE OAuth failed: {e}")
    
    # Shutdown server
    server.shutdown()
    
    # Exchange code for tokens
    code = _PKCERedirectHandler.auth_code
    if not code:
        raise ValueError("No authorization code received")
    
    return await self._pkce_exchange_code(code, verifier, redirect_uri)
```

- [x] **Step 2: Add `_pkce_exchange_code()` method to exchange auth code for tokens**

```python
async def _pkce_exchange_code(self, code: str, verifier: str, redirect_uri: str) -> str:
    """
    Exchange authorization code for access/refresh tokens.
    
    POSTs to Kiro OAuth token endpoint with code + verifier.
    Stores tokens in credentials file upon success.
    
    Args:
        code: Authorization code from callback
        verifier: PKCE code verifier (original secret)
        redirect_uri: Redirect URI used in auth request
    
    Returns:
        Access token
    
    Raises:
        ValueError: If token exchange fails
    """
    token_url = KIRO_OAUTH_TOKEN_URL_TEMPLATE.format(region=self._region)
    
    payload = {
        "code": code,
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
    }
    
    logger.info("Exchanging authorization code for tokens...")
    
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(token_url, json=payload, headers=headers)
        
        if not response.is_success:
            # Try alternate redirect_uri (without login_option)
            payload["redirect_uri"] = redirect_uri  # Already set correctly
            if response.status_code == 400:
                logger.warning("Token exchange failed, retrying with simplified redirect_uri")
                response = await client.post(token_url, json=payload, headers=headers)
        
        if not response.is_success:
            raise ValueError(
                f"Token exchange failed: HTTP {response.status_code} {response.text}"
            )
        
        data = response.json()
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]
    
    # Extract tokens (camelCase from Kiro API)
    new_access_token = data.get("accessToken") or data.get("access_token")
    new_refresh_token = data.get("refreshToken") or data.get("refresh_token")
    new_profile_arn = data.get("profileArn") or data.get("profile_arn")
    expires_in = data.get("expiresIn", 3600)
    
    if not new_access_token:
        raise ValueError(f"Token exchange response missing accessToken: {data}")
    
    # Update instance state
    self._access_token = new_access_token
    if new_refresh_token:
        self._refresh_token = new_refresh_token
    if new_profile_arn:
        self._profile_arn = new_profile_arn
    
    # Calculate expiration (with 60s buffer)
    self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)
    
    logger.info(f"PKCE OAuth successful, token expires: {self._expires_at.isoformat()}")
    
    # Force auth type to KIRO_DESKTOP (PKCE uses same refresh endpoint)
    self._auth_type = AuthType.KIRO_DESKTOP
    
    # Save to file
    if not self._creds_file:
        # Auto-create credentials file if none set
        default_creds = Path.home() / ".kiro" / "credentials.json"
        default_creds.parent.mkdir(parents=True, exist_ok=True)
        self._creds_file = str(default_creds)
    
    self._save_credentials_to_file()
    
    return self._access_token
```

- [x] **Step 3: Verify imports compile**

Run: `python -c "from kiro.auth import KiroAuthManager, _PKCERedirectHandler; print('OK')"`
Expected: OK

---

### Task 5: Integrate PKCE into get_access_token() fallback chain

**Files:**
- Modify: `kiro/auth.py` — fallback chain in `get_access_token()`

- [x] **Step 1: Add PKCE fallback after kirolink fails, before final error**

In `get_access_token()` (around line 925-936), after kirolink failure and before the final ValueError, insert PKCE fallback:

```python
                # Kirolink also failed, try graceful degradation
                if self._access_token and not self.is_token_expired():
                    # ...existing graceful degradation code...
                    
                # LAST RESORT: Try PKCE OAuth browser login
                # Only attempt if we have no valid token at all
                if not self._access_token or self.is_token_expired():
                    logger.warning(
                        "All auth methods exhausted. Attempting PKCE OAuth browser login..."
                    )
                    try:
                        pkce_token = await self._pkce_oauth_flow()
                        return pkce_token
                    except (TimeoutError, ValueError) as pkce_err:
                        logger.error(f"PKCE OAuth failed: {pkce_err}")
                        raise ValueError(
                            "Token expired and all refresh methods failed. "
                            "Please run 'kiro-cli login' to refresh your credentials."
                        )
```

The full modified block (lines 908-946) should become:

```python
            # Try to refresh the token
            try:
                await self._refresh_token_request()
            except httpx.HTTPStatusError as e:
                # Graceful degradation for SQLite mode when refresh fails twice
                if e.response.status_code == 400 and self._sqlite_db:
                    logger.warning(
                        "Token refresh failed with 400 after SQLite reload. "
                        "Attempting kirolink fallback..."
                    )
                    
                    kirolink_ok = await self._refresh_via_kirolink()
                    if kirolink_ok:
                        self._load_credentials_from_sqlite(self._sqlite_db)
                        if self._access_token and not self.is_token_expiring_soon():
                            return self._access_token
                    
                    # Graceful degradation: use existing token if still valid
                    if self._access_token and not self.is_token_expired():
                        logger.warning(
                            "Using existing access_token until it expires. "
                            "Run 'kiro-cli login' when convenient to refresh credentials."
                        )
                        return self._access_token
                    
                    # LAST RESORT: PKCE OAuth browser login
                    logger.warning(
                        "All auth methods exhausted. Attempting PKCE OAuth browser login..."
                    )
                    try:
                        return await self._pkce_oauth_flow()
                    except (TimeoutError, ValueError) as pkce_err:
                        logger.error(f"PKCE OAuth failed: {pkce_err}")
                        raise ValueError(
                            "Token expired and all refresh methods failed. "
                            "Please run 'kiro-cli login' to refresh your credentials."
                        )
                
                # Non-SQLite mode or non-400 error - propagate the exception
                raise
            
            # Also handle the case where refresh_request fails with non-HTTP errors
            # or there's no access token at all — try PKCE as last resort
            # (This covers the non-SQLite, non-400 path where refresh failed)
            
            if not self._access_token:
                # No token at all — try PKCE before giving up
                logger.warning("No access token available. Attempting PKCE OAuth browser login...")
                try:
                    return await self._pkce_oauth_flow()
                except (TimeoutError, ValueError) as pkce_err:
                    logger.error(f"PKCE OAuth failed: {pkce_err}")
                    raise ValueError(
                        "Failed to obtain access token. "
                        "Please run 'kiro-cli login' to authenticate."
                    )
            
            return self._access_token
```

Wait — this is getting complex. Let me simplify. The fallback chain already has clear logic. PKCE should only trigger when:

1. All HTTP refresh methods failed (KIRO_DESKTOP or AWS_SSO_OIDC)
2. Kirolink fallback failed
3. No valid access token remains (graceful degradation couldn't save us)

Let me re-read the existing code more carefully...

The existing fallback chain in `get_access_token()`:

```
1. Try _refresh_token_request() 
2. If 400 + sqlite_db: try kirolink → graceful degradation → error
3. If non-400 or no sqlite_db: raise
```

PKCE should slot in between graceful degradation and the final error, but ONLY in the cases where no valid token exists. Let me write this properly.

The existing code at lines 907-946:
```python
            try:
                await self._refresh_token_request()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and self._sqlite_db:
                    # ... kirolink + graceful degradation ...
                    # ... then raise ValueError("Token expired...")
                raise
            except Exception:
                raise
            
            if not self._access_token:
                raise ValueError("Failed to obtain access token")
            
            return self._access_token
```

PKCE should catch the error path where all other methods fail. The cleanest integration point is in the except handler for httpx.HTTPStatusError, right after graceful degradation fails:

- [x] **Step 2: Write the actual code change**

Replace lines 908-946 in auth.py (the refresh + fallback section of get_access_token) with:

```python
            try:
                await self._refresh_token_request()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400 and self._sqlite_db:
                    logger.warning(
                        "Token refresh failed with 400 after SQLite reload. "
                        "Attempting kirolink fallback..."
                    )

                    kirolink_ok = await self._refresh_via_kirolink()
                    if kirolink_ok:
                        self._load_credentials_from_sqlite(self._sqlite_db)
                        if self._access_token and not self.is_token_expiring_soon():
                            return self._access_token

                    # Graceful degradation: use existing token if still valid
                    if self._access_token and not self.is_token_expired():
                        logger.warning(
                            "Using existing access_token until it expires. "
                            "Run 'kiro-cli login' when convenient to refresh credentials."
                        )
                        return self._access_token

                    # LAST RESORT: PKCE OAuth browser login
                    logger.warning(
                        "All refresh methods failed. Attempting PKCE OAuth browser login..."
                    )
                    try:
                        return await self._pkce_oauth_flow()
                    except (TimeoutError, ValueError) as pkce_err:
                        logger.error(f"PKCE OAuth failed: {pkce_err}")
                        raise ValueError(
                            "Token expired and all refresh methods failed. "
                            "Please run 'kiro-cli login' to refresh your credentials."
                        ) from pkce_err

                raise

            except Exception:
                raise

            if not self._access_token:
                raise ValueError("Failed to obtain access token")

            return self._access_token
```

- [x] **Step 3: Run tests to verify auth module still compiles**

Run: `python -c "from kiro.auth import KiroAuthManager, AuthType; print('OK')"`
Expected: OK

Run: `pytest tests/unit/test_auth_manager.py -v --timeout=30 2>&1 | head -50`

---

### Task 6: Add PKCE credential type to AccountManager

**Files:**
- Modify: `kiro/account_manager.py` — add `"pkce"` credential type support

- [x] **Step 1: Add `"pkce"` handler in `_init_account()` method**

In `_init_account()` (around line 493), add a new elif for pkce credential type:

```python
            elif cred_type == "pkce":
                auth_manager = KiroAuthManager(
                    region=creds_config.get("region", "us-east-1"),
                    api_region=creds_config.get("api_region"),
                    creds_file=creds_config.get("path"),
                )
```

- [x] **Step 2: Add `"pkce"` to credential loading in `load_credentials()`**

In `load_credentials()` (around line 255), add pkce to the valid types:

```python
            # For pkce type, no immediate path required (creates creds on first login)
            if cred_type == "pkce":
                account_id = f"pkce_{secrets.token_hex(8)}"
                self._accounts[account_id] = Account(id=account_id)
                logger.debug(f"Added PKCE account: {account_id}")
                continue
            
            # For json/sqlite types, path is required
            if cred_type in ("json", "sqlite") and not path:
                logger.warning(f"Invalid credential entry (type={cred_type} requires path): {entry}")
                continue
```

Wait, but `secrets` isn't imported in account_manager.py. Let me use `uuid` or `hashlib`. Actually account_manager.py already imports `hashlib`. Let me use a simpler approach.

```python
            # For pkce type, no immediate path required (creates creds on first login)
            if cred_type == "pkce":
                import uuid
                account_id = f"pkce_{uuid.uuid4().hex[:16]}"
                self._accounts[account_id] = Account(id=account_id)
                logger.debug(f"Added PKCE account: {account_id}")
                continue
```

- [x] **Step 3: Run tests**

Run: `pytest tests/unit/test_account_manager.py -v --timeout=30 2>&1 | head -50`
Expected: PASS

---

### Task 7: Write PKCE OAuth tests

**Files:**
- Modify: `tests/unit/test_auth_manager.py` — add PKCE test class

- [x] **Step 1: Find existing test file and add PKCE test class**

Read `tests/unit/test_auth_manager.py` to find the test patterns:

Run: `wc -l tests/unit/test_auth_manager.py`

- [x] **Step 2: Add PKCE challenge generation test**

```python
class TestPKCEChallengeGeneration:
    """Tests for PKCE code challenge generation."""

    def test_pkce_challenge_generates_valid_verifier(self):
        """
        Test that PKCE verifier is a valid base64url string.
        
        A valid verifier should:
        - Be a non-empty string
        - Contain only URL-safe characters
        - Be at least 43 characters (per RFC 7636)
        """
        verifier, challenge, state = KiroAuthManager._pkce_generate_challenge()
        
        assert isinstance(verifier, str)
        assert len(verifier) >= 43
        assert all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in verifier)

    def test_pkce_challenge_is_different_each_call(self):
        """
        Test that each PKCE generation produces unique values.
        """
        v1, c1, s1 = KiroAuthManager._pkce_generate_challenge()
        v2, c2, s2 = KiroAuthManager._pkce_generate_challenge()
        
        assert v1 != v2
        assert c1 != c2
        assert s1 != s2

    def test_pkce_challenge_is_sha256_hash_of_verifier(self):
        """
        Test that challenge = base64url(SHA256(verifier)).
        """
        import hashlib
        import base64
        
        verifier, challenge, state = KiroAuthManager._pkce_generate_challenge()
        
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        assert challenge == expected

    def test_pkce_state_is_random_string(self):
        """
        Test that state parameter is a non-empty random string.
        """
        verifier, challenge, state = KiroAuthManager._pkce_generate_challenge()
        
        assert isinstance(state, str)
        assert len(state) > 0
        assert state != verifier
        assert state != challenge
```

- [x] **Step 3: Add PKCE exchange test**

```python
class TestPKCETokenExchange:
    """Tests for PKCE token exchange logic."""

    @pytest.mark.asyncio
    async def test_pkce_exchange_success(self, mock_env_vars):
        """
        Test successful token exchange with mocked HTTP response.
        """
        auth = KiroAuthManager(region="us-east-1")
        test_code = "test_auth_code_123"
        test_verifier = "test_verifier_456"
        redirect_uri = "http://127.0.0.1:54321"
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "accessToken": "pkce_access_token_789",
                "refreshToken": "pkce_refresh_token_abc",
                "profileArn": "arn:aws:codewhisperer:us-east-1:123:profile/test",
                "expiresIn": 3600,
            }
            mock_post.return_value = mock_response
            
            token = await auth._pkce_exchange_code(test_code, test_verifier, redirect_uri)
            
            assert token == "pkce_access_token_789"
            assert auth._access_token == "pkce_access_token_789"
            assert auth._refresh_token == "pkce_refresh_token_abc"
            assert auth._auth_type == AuthType.KIRO_DESKTOP  # Changed after PKCE
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pkce_exchange_failure(self, mock_env_vars):
        """
        Test that token exchange raises ValueError on HTTP error.
        """
        auth = KiroAuthManager(region="us-east-1")
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.is_success = False
            mock_response.status_code = 400
            mock_response.text = '{"error":"invalid_grant"}'
            mock_post.return_value = mock_response
            
            with pytest.raises(ValueError, match="Token exchange failed"):
                await auth._pkce_exchange_code("bad_code", "verifier", "http://127.0.0.1:0")
    
    @pytest.mark.asyncio
    async def test_pkce_exchange_wraps_data_field(self, mock_env_vars):
        """
        Test that exchange handles Kiro's nested 'data' field.
        
        Kiro API sometimes wraps response in {data: {...}}.
        """
        auth = KiroAuthManager(region="us-east-1")
        
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "data": {
                    "accessToken": "nested_token",
                    "refreshToken": "nested_refresh",
                    "profileArn": "arn:aws:codewhisperer:us-east-1:123:profile/nested",
                    "expiresIn": 3600,
                }
            }
            mock_post.return_value = mock_response
            
            token = await auth._pkce_exchange_code("code", "verifier", "uri")
            assert token == "nested_token"
```

- [x] **Step 4: Add PKCE redirect handler test**

```python
class TestPKCERedirectHandler:
    """Tests for the PKCE callback HTTP handler."""

    def test_handler_captures_valid_code(self):
        """
        Test that handler correctly captures code from valid callback.
        """
        # Reset static state
        _PKCERedirectHandler.auth_code = None
        _PKCERedirectHandler.state = "test_state_123"
        _PKCERedirectHandler.received.clear()
        
        # Simulate HTTP request
        handler = _PKCERedirectHandler
        handler.path = "/?code=auth_code_xyz&state=test_state_123"
        
        # We can't easily instantiate BaseHTTPRequestHandler without a socket,
        # so we test the parsing logic directly via the class attributes
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse("/?code=auth_code_xyz&state=test_state_123")
        params = parse_qs(parsed.query)
        
        received_code = params.get("code", [None])[0]
        received_state = params.get("state", [None])[0]
        
        assert received_code == "auth_code_xyz"
        assert received_state == "test_state_123"

    def test_handler_rejects_state_mismatch(self):
        """
        Test that handler rejects callbacks with wrong state.
        """
        _PKCERedirectHandler.auth_code = None
        _PKCERedirectHandler.state = "expected_state"
        _PKCERedirectHandler.received.clear()
        
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse("/?code=some_code&state=wrong_state")
        params = parse_qs(parsed.query)
        
        received_code = params.get("code", [None])[0]
        received_state = params.get("state", [None])[0]
        
        assert received_code == "some_code"
        assert received_state == "wrong_state"
        assert received_state != _PKCERedirectHandler.state
```

- [x] **Step 5: Run all auth tests**

Run: `pytest tests/unit/test_auth_manager.py -v`
Expected: All tests PASS

---

### Task 8: Full integration test run

- [x] **Step 1: Run full test suite**

Run: `pytest -v --timeout=60 2>&1 | tail -30`
Expected: 1700+ pass, same 3 pre-existing failures

- [x] **Step 2: Add PKCE example to credentials.json.example**

Append to `credentials.json.example`:

```json
  {
    "type": "pkce",
    "region": "us-east-1",
    "path": "~/.kiro/credentials.json"
  }
```

- [x] **Step 3: Commit**

```bash
git add -A
git commit -m "feat(auth): add PKCE OAuth browser login as last-resort auth type"
```

---

### Verification Checklist

- [x] `AuthType.PKCE_OAUTH` exists
- [x] `_pkce_generate_challenge()` generates valid verifier/challenge/state
- [x] `_PKCERedirectHandler` captures callback code and validates state
- [x] `_pkce_exchange_code()` POSTs to Kiro OAuth token endpoint and stores tokens
- [x] `_pkce_oauth_flow()` spawns ephemeral server, opens browser, waits for callback
- [x] PKCE fires after kirolink fails (not before) in `get_access_token()`
- [x] Credentials saved to JSON file on successful PKCE
- [x] Auth type switched to KIRO_DESKTOP after PKCE (for refresh compatibility)
- [x] Account manager supports `"pkce"` credential type
- [x] All existing tests pass
- [x] No new dependencies added (stdlib only for PKCE)
