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
Small authenticated web panel for multi-account management.

The panel intentionally exposes only three capabilities:
- Login/logout with PROXY_API_KEY
- Add/delete credentials.json account entries when multi-account mode is enabled
- View sanitized account health and request statistics
"""

import hashlib
import hmac
import html
import json
import time
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any, Dict, List
from urllib.parse import parse_qs, quote, unquote

from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from loguru import logger

from kiro.config import ACCOUNT_SYSTEM, PROXY_API_KEY


SESSION_COOKIE_NAME = "kiro_admin_session"
SESSION_COOKIE_SALT = b"kiro-gateway-admin-session"

router = APIRouter(prefix="/admin", tags=["admin"])


def _session_signature() -> str:
    """
    Build a stable HMAC session signature from PROXY_API_KEY.

    Returns:
        Hex-encoded session signature.
    """
    return hmac.new(
        PROXY_API_KEY.encode("utf-8"),
        SESSION_COOKIE_SALT,
        hashlib.sha256,
    ).hexdigest()


def _is_authenticated(request: Request) -> bool:
    """
    Check whether the request carries a valid admin session cookie.

    Args:
        request: FastAPI request.

    Returns:
        True when the session cookie matches the configured token signature.
    """
    session_cookie = request.cookies.get(SESSION_COOKIE_NAME, "")
    expected_signature = _session_signature()
    return bool(session_cookie) and hmac.compare_digest(session_cookie, expected_signature)


def _is_account_system_enabled(request: Request) -> bool:
    """
    Determine whether multi-account management is enabled for this app.

    Args:
        request: FastAPI request.

    Returns:
        True when ACCOUNT_SYSTEM is enabled.
    """
    return bool(getattr(request.app.state, "account_system", ACCOUNT_SYSTEM))


def _redirect(location: str, message: str = "", error: str = "") -> RedirectResponse:
    """
    Create a 303 redirect with optional status query parameters.

    Args:
        location: Target path.
        message: Success message.
        error: Error message.

    Returns:
        Redirect response.
    """
    params = []
    if message:
        params.append(f"message={quote(message)}")
    if error:
        params.append(f"error={quote(error)}")
    separator = "&" if "?" in location else "?"
    target = f"{location}{separator}{'&'.join(params)}" if params else location
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


def _parse_account_entries(raw_payload: str) -> List[Dict[str, Any]]:
    """
    Parse account JSON from the add-account form.

    Args:
        raw_payload: JSON object or JSON array string.

    Returns:
        List of credential entries.

    Raises:
        ValueError: If JSON is empty or not an object/array of objects.
        JSONDecodeError: If the JSON is malformed.
    """
    if not raw_payload.strip():
        raise ValueError("Account JSON cannot be empty")

    parsed = json.loads(raw_payload)
    if isinstance(parsed, dict):
        return [parsed]

    if isinstance(parsed, list) and all(isinstance(entry, dict) for entry in parsed):
        return parsed

    raise ValueError("Account JSON must be an object or an array of objects")


def _format_timestamp(timestamp: float) -> str:
    """
    Format a Unix timestamp for HTML rendering.

    Args:
        timestamp: Unix timestamp. Zero means missing value.

    Returns:
        Human-readable UTC timestamp or a dash.
    """
    if timestamp <= 0:
        return "-"
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _format_age(timestamp: float) -> str:
    """
    Format age from timestamp to now.

    Args:
        timestamp: Unix timestamp. Zero means missing value.

    Returns:
        Short age string or a dash.
    """
    if timestamp <= 0:
        return "-"
    age_seconds = max(0, int(time.time() - timestamp))
    if age_seconds < 60:
        return f"{age_seconds}s ago"
    if age_seconds < 3600:
        return f"{age_seconds // 60}m ago"
    if age_seconds < 86400:
        return f"{age_seconds // 3600}h ago"
    return f"{age_seconds // 86400}d ago"


def _format_credits(value: Any) -> str:
    """
    Format an accumulated credits value for HTML rendering.

    Kiro returns credit consumption as a numeric value per response. We
    accumulate it as a float; this helper renders it with three significant
    decimals and a dash for missing/zero values to keep the table compact.

    Args:
        value: Accumulated credit value (int/float). None or non-numeric
            inputs render as a dash.

    Returns:
        Formatted credit string.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "-"
    if amount <= 0:
        return "-"
    if amount >= 100:
        return f"{amount:.0f}"
    if amount >= 1:
        return f"{amount:.2f}"
    return f"{amount:.3f}"


def _escape_json(data: Dict[str, Any]) -> str:
    """
    Render sanitized JSON for HTML.

    Args:
        data: JSON-compatible dictionary.

    Returns:
        Escaped pretty JSON string.
    """
    return html.escape(json.dumps(data, indent=2, ensure_ascii=False))


def _render_login(error: str = "") -> HTMLResponse:
    """
    Render the login page.

    Args:
        error: Optional authentication error.

    Returns:
        HTML response.
    """
    error_html = f"<div class='error'>{html.escape(error)}</div>" if error else ""
    return HTMLResponse(f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiro Gateway Admin</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #111827; color: #f9fafb; margin: 0; }}
    main {{ max-width: 420px; margin: 12vh auto; background: #1f2937; border: 1px solid #374151; border-radius: 16px; padding: 28px; box-shadow: 0 20px 80px rgba(0,0,0,.35); }}
    h1 {{ margin-top: 0; }}
    label {{ display: block; margin-bottom: 8px; color: #d1d5db; }}
    input {{ width: 100%; box-sizing: border-box; padding: 12px; border-radius: 10px; border: 1px solid #4b5563; background: #030712; color: #f9fafb; }}
    button {{ margin-top: 16px; width: 100%; padding: 12px; border: 0; border-radius: 10px; background: #38bdf8; color: #082f49; font-weight: 700; cursor: pointer; }}
    .error {{ background: #7f1d1d; color: #fecaca; padding: 10px; border-radius: 10px; margin-bottom: 16px; }}
    p {{ color: #9ca3af; }}
  </style>
</head>
<body>
  <main>
    <h1>Kiro Gateway Admin</h1>
    <p>Use the configured PROXY_API_KEY to sign in.</p>
    {error_html}
    <form method="post" action="/admin/login">
      <label for="token">Token</label>
      <input id="token" name="token" type="password" autocomplete="current-password" autofocus>
      <button type="submit">Sign in</button>
    </form>
  </main>
</body>
</html>
""")


def _render_panel(request: Request, snapshot: Dict[str, Any]) -> HTMLResponse:
    """
    Render the management panel.

    Args:
        request: FastAPI request with query messages.
        snapshot: Account manager snapshot.

    Returns:
        HTML response.
    """
    message = unquote(request.query_params.get("message", ""))
    error = unquote(request.query_params.get("error", ""))
    message_html = f"<div class='message'>{html.escape(message)}</div>" if message else ""
    error_html = f"<div class='error'>{html.escape(error)}</div>" if error else ""
    account_system_enabled = _is_account_system_enabled(request)
    disabled_attribute = "" if account_system_enabled else "disabled"
    mode_badge = "enabled" if account_system_enabled else "disabled"
    mode_class = "ok" if account_system_enabled else "warn"

    totals = snapshot.get("totals", {})
    credentials = snapshot.get("credentials", [])
    accounts = snapshot.get("accounts", [])

    credential_rows = "".join(
        f"""
        <article class="entry">
          <div class="entry-head">
            <strong>Entry #{credential['index']}</strong>
            <form method="post" action="/admin/accounts/delete" onsubmit="return confirm('Delete this credential entry?');">
              <input type="hidden" name="index" value="{credential['index']}">
              <button class="danger" type="submit" {disabled_attribute}>Delete</button>
            </form>
          </div>
          <pre>{_escape_json(credential['entry'])}</pre>
        </article>
        """
        for credential in credentials
    ) or "<p class='muted'>No credential entries configured.</p>"

    account_rows = "".join(
        f"""
        <tr>
          <td><code>{html.escape(account['id'])}</code></td>
          <td>{'yes' if account['initialized'] else 'no'}</td>
          <td>{account['failures']}</td>
          <td>{account['available_model_count']}</td>
          <td>{account['stats']['total_requests']}</td>
          <td>{account['stats']['successful_requests']}</td>
          <td>{account['stats']['failed_requests']}</td>
          <td>{_format_credits(account['stats'].get('credits_used_total', 0.0))}</td>
          <td>{_format_age(account['last_failure_time'])}</td>
          <td>{_format_timestamp(account['models_cached_at'])}</td>
        </tr>
        """
        for account in accounts
    ) or "<tr><td colspan='10' class='muted'>No runtime accounts loaded.</td></tr>"

    disabled_notice = "" if account_system_enabled else """
      <div class="error">
        Multi-account mode is disabled. Set <code>ACCOUNT_SYSTEM=true</code> to add or delete accounts from this panel.
      </div>
    """

    return HTMLResponse(f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kiro Gateway Admin</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #0f172a; color: #e5e7eb; }}
    header {{ padding: 22px 28px; background: #111827; border-bottom: 1px solid #374151; display: flex; justify-content: space-between; align-items: center; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1, h2 {{ margin-top: 0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .card, section, .entry {{ background: #1f2937; border: 1px solid #374151; border-radius: 14px; padding: 18px; }}
    .card strong {{ display: block; font-size: 26px; margin-bottom: 4px; }}
    .muted {{ color: #9ca3af; }}
    .badge {{ border-radius: 999px; padding: 4px 10px; font-size: 13px; }}
    .badge.ok {{ background: #064e3b; color: #a7f3d0; }}
    .badge.warn {{ background: #78350f; color: #fde68a; }}
    textarea {{ width: 100%; min-height: 220px; box-sizing: border-box; background: #030712; color: #e5e7eb; border: 1px solid #4b5563; border-radius: 12px; padding: 14px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    button {{ padding: 10px 14px; border: 0; border-radius: 10px; background: #38bdf8; color: #082f49; font-weight: 700; cursor: pointer; }}
    button:disabled {{ opacity: .5; cursor: not-allowed; }}
    button.danger {{ background: #f87171; color: #450a0a; }}
    button.secondary {{ background: #374151; color: #e5e7eb; }}
    pre {{ overflow-x: auto; background: #030712; padding: 12px; border-radius: 10px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid #374151; padding: 10px; text-align: left; vertical-align: top; }}
    code {{ color: #bae6fd; }}
    .entry {{ margin-bottom: 12px; }}
    .entry-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; }}
    .message {{ background: #064e3b; color: #a7f3d0; padding: 12px; border-radius: 12px; margin-bottom: 16px; }}
    .error {{ background: #7f1d1d; color: #fecaca; padding: 12px; border-radius: 12px; margin-bottom: 16px; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Kiro Gateway Admin</h1>
      <span class="badge {mode_class}">ACCOUNT_SYSTEM {mode_badge}</span>
    </div>
    <form method="post" action="/admin/logout"><button class="secondary" type="submit">Logout</button></form>
  </header>
  <main>
    {message_html}
    {error_html}
    {disabled_notice}

    <div class="grid">
      <div class="card"><strong>{totals.get('configured_entries', 0)}</strong><span class="muted">credential entries</span></div>
      <div class="card"><strong>{totals.get('loaded_accounts', 0)}</strong><span class="muted">loaded accounts</span></div>
      <div class="card"><strong>{totals.get('initialized_accounts', 0)}</strong><span class="muted">initialized accounts</span></div>
      <div class="card"><strong>{totals.get('total_requests', 0)}</strong><span class="muted">total requests</span></div>
      <div class="card"><strong>{totals.get('successful_requests', 0)}</strong><span class="muted">successful requests</span></div>
      <div class="card"><strong>{totals.get('failed_requests', 0)}</strong><span class="muted">failed requests</span></div>
      <div class="card"><strong>{_format_credits(totals.get('credits_used_total', 0.0))}</strong><span class="muted">credits used (gateway-tracked)</span></div>
      <div class="card"><strong>{snapshot.get('model_mapping_count', 0)}</strong><span class="muted">model mappings</span></div>
    </div>

    <section>
      <h2>Add account JSON</h2>
      <p class="muted">Paste a raw kiro-auth-token.json object, a credentials.json entry, or an array of either format. Raw token objects are saved as managed JSON files and registered automatically.</p>
      <form method="post" action="/admin/accounts">
        <textarea name="account_json" spellcheck="false" {disabled_attribute}>{{
  "accessToken": "...",
  "refreshToken": "...",
  "profileArn": "arn:aws:codewhisperer:us-east-1:123456789012:profile/example",
  "expiresAt": "2026-05-16T09:45:03.903Z",
  "authMethod": "social",
  "provider": "Google"
}}</textarea>
        <p><button type="submit" {disabled_attribute}>Add account</button></p>
      </form>
    </section>

    <section>
      <h2>Configured credential entries</h2>
      {credential_rows}
    </section>

    <section>
      <h2>Runtime statistics</h2>
      <table>
        <thead>
          <tr><th>Account</th><th>Initialized</th><th>Failures</th><th>Models</th><th>Total</th><th>OK</th><th>Failed</th><th>Credits</th><th>Last failure</th><th>Models cached at</th></tr>
        </thead>
        <tbody>{account_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
""")


@router.get("", response_class=HTMLResponse)
async def admin_panel(request: Request) -> HTMLResponse:
    """
    Render the authenticated management panel.

    Args:
        request: FastAPI request.

    Returns:
        HTML response or redirect to login.
    """
    if not _is_authenticated(request):
        return _redirect("/admin/login")

    snapshot = request.app.state.account_manager.get_management_snapshot()
    return _render_panel(request, snapshot)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """
    Render login page or redirect authenticated users to the panel.

    Args:
        request: FastAPI request.

    Returns:
        HTML response or redirect.
    """
    if _is_authenticated(request):
        return _redirect("/admin")
    error = unquote(request.query_params.get("error", ""))
    return _render_login(error=error)


@router.post("/login")
async def login(request: Request) -> RedirectResponse:
    """
    Authenticate with the configured PROXY_API_KEY.

    Args:
        request: FastAPI request containing application/x-www-form-urlencoded body.

    Returns:
        Redirect response with or without session cookie.
    """
    body = (await request.body()).decode("utf-8")
    form_data = parse_qs(body)
    provided_token = form_data.get("token", [""])[0]

    if not hmac.compare_digest(provided_token, PROXY_API_KEY):
        logger.warning("Admin panel login attempt with invalid token")
        return _redirect("/admin/login", error="Invalid token")

    response = _redirect("/admin", message="Signed in")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        _session_signature(),
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    """
    Clear the admin session cookie.

    Returns:
        Redirect response to login page.
    """
    response = _redirect("/admin/login")
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.post("/accounts")
async def add_account(request: Request) -> RedirectResponse:
    """
    Add one or more account entries from JSON form data.

    Args:
        request: FastAPI request.

    Returns:
        Redirect back to the panel with a status message.
    """
    if not _is_authenticated(request):
        return _redirect("/admin/login")

    if not _is_account_system_enabled(request):
        return _redirect("/admin", error="ACCOUNT_SYSTEM=true is required to manage accounts")

    body = (await request.body()).decode("utf-8")
    form_data = parse_qs(body)
    raw_payload = form_data.get("account_json", [""])[0]

    try:
        entries = _parse_account_entries(raw_payload)
        await request.app.state.account_manager.add_credentials_entries(entries)
    except JSONDecodeError as error:
        return _redirect("/admin", error=f"Invalid JSON: {error.msg}")
    except ValueError as error:
        return _redirect("/admin", error=str(error))
    except OSError as error:
        logger.error(f"Failed to add account credentials: {error}")
        return _redirect("/admin", error="Could not write credentials file")

    return _redirect("/admin", message=f"Added {len(entries)} account entry(s)")


@router.post("/accounts/delete")
async def delete_account(request: Request) -> RedirectResponse:
    """
    Delete one account credential entry by index.

    Args:
        request: FastAPI request.

    Returns:
        Redirect back to the panel with a status message.
    """
    if not _is_authenticated(request):
        return _redirect("/admin/login")

    if not _is_account_system_enabled(request):
        return _redirect("/admin", error="ACCOUNT_SYSTEM=true is required to manage accounts")

    body = (await request.body()).decode("utf-8")
    form_data = parse_qs(body)
    raw_index = form_data.get("index", [""])[0]

    try:
        index = int(raw_index)
        await request.app.state.account_manager.delete_credentials_entry(index)
    except JSONDecodeError as error:
        return _redirect("/admin", error=f"Invalid credentials file JSON: {error.msg}")
    except ValueError as error:
        return _redirect("/admin", error=str(error))
    except OSError as error:
        logger.error(f"Failed to delete account credentials: {error}")
        return _redirect("/admin", error="Could not write credentials file")

    return _redirect("/admin", message=f"Deleted account entry #{index}")
