# Kiro Gateway + Kanban Setup Notes

Reference notes for the kiro-gateway + kanban-cmd setup. Last updated: 2026-05-30.

## TL;DR

Two separate problems were solved:

1. **`role="system"` 422 error** — fixed by applying PR #191 to the gateway, which lets
   newer Claude Code clients work without pinning the version.
2. **`400 profileArn is required` error** — fixed by giving the gateway the CodeWhisperer
   profile ARN, which the new `runtime.kiro.dev` endpoint requires.

After config changes, the gateway MUST be restarted to pick them up (see "Restarting" below).

---

## Change 1: PR #191 — accept non-standard message roles

**Why:** Newer Claude Code (2.1.143+) inlines a message with `role="system"` inside the
`messages` array. The gateway's `AnthropicMessage.role` field was `Literal["user","assistant"]`,
so it rejected those payloads with a 422 ValidationError. This was the reason Claude Code
auto-updates had been disabled/pinned.

**What changed:**
- `kiro/models_anthropic.py` — `AnthropicMessage.role` changed from
  `Literal["user", "assistant"]` to a free-form `str`. Unknown roles (`system`, `developer`)
  are normalized to `user` downstream by `converters_core.normalize_message_roles()`,
  which already existed.
- `tests/unit/test_models_anthropic.py` — added `TestAnthropicMessageInlineRoles` (4 tests).

**Verification:** `py -m pytest tests/unit/test_models_anthropic.py tests/unit/test_converters_core.py -q`
→ all tests passed (350).

**Related change in kanban-cmd:** `start.bat` previously had `set DISABLE_AUTOUPDATER=1`
to pin Claude Code below 2.1.143. That pin was removed since the gateway now handles the
newer payloads. Auto-updates are enabled again.

---

## Change 2: profileArn required by runtime.kiro.dev

**Why it broke:** The gateway migrated its upstream endpoint from
`q.{region}.amazonaws.com` to `https://runtime.{region}.kiro.dev` (commits 07d24fc / 90d0509,
pulled into this clone). The new runtime endpoint **requires `profileArn` on every request**
for all auth types. The old endpoint did not enforce it for Enterprise tokens, so requests
that used to work started failing with:

```
HTTP 400 - POST /v1/messages - profileArn is required for this request.
```

**Root cause:** This setup uses an Enterprise (AWS SSO / IdC) token at
`C:\Users\admin\.aws\sso\cache\kiro-auth-token.json`. That file has NO `profileArn` field,
and there is no kiro-cli SQLite DB to auto-detect one from. So the gateway resolved an empty
ARN: `auth_manager.profile_arn or PROFILE_ARN or ""` → `""`.

Note: the gateway auto-detects the *auth type* (correctly: AWS SSO OIDC via clientIdHash),
but it does NOT auto-detect the *profile ARN* unless it's in the token file or SQLite state.

**The ARN** (sourced from Kiro IDE's own config at
`%APPDATA%\kiro\User\globalStorage\kiro.kiroagent\profile.json`):

```
arn:aws:codewhisperer:us-east-1:425090349675:profile/AEP9939EUKHX
```

**What changed (ARN set in TWO places for robustness):**

1. `credentials.json` (used by the account system, which is active here) — added
   `profile_arn` to the entry:
   ```json
   [
     {
       "type": "json",
       "path": "C:\\Users\\admin\\.aws\\sso\\cache\\kiro-auth-token.json",
       "profile_arn": "arn:aws:codewhisperer:us-east-1:425090349675:profile/AEP9939EUKHX"
     }
   ]
   ```

2. `.env` — set `PROFILE_ARN` as a global fallback (covers the single-auth path too):
   ```
   PROFILE_ARN="arn:aws:codewhisperer:us-east-1:425090349675:profile/AEP9939EUKHX"
   ```

The route logic `auth_manager.profile_arn or PROFILE_ARN or ""` means either location works.

---

## Restarting the gateway (IMPORTANT)

Config (`credentials.json`, `.env`) is read ONCE at startup. Editing it does nothing until
the gateway process is restarted.

Gotcha: `start.bat` checks if port 8000 is already in use and SKIPS launching the gateway if
so. So re-running `start.bat` will NOT restart a stale gateway. You must kill it first:

```powershell
# Find the PID listening on 8000
netstat -ano | findstr ":8000" | findstr "LISTENING"

# Kill it (replace <PID>)
taskkill /PID <PID> /F

# Start a fresh one (uses the same Python 3.12 as start.bat)
C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe main.py
```

A healthy startup log shows: "Loaded 1 account(s)", "Successfully initialized account",
and "Uvicorn running on http://0.0.0.0:8000". If you then send a request and do NOT see
"profileArn is required", the ARN is being sent correctly.

---

## Environment gotchas

- The `python` on PATH points to a broken venv (`C:\Users\admin\tiktok1\.venv`, missing
  `pyvenv.cfg`). Use the Python launcher `py` for tests, or the explicit Python 3.12 path
  (`C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe`) for the gateway,
  which is what `start.bat` uses.

- kanban-cmd launches Claude Code with `--dangerously-skip-permissions` (in `pty-server.js`).
  Combined with auto-updates now enabled, sessions auto-run the newest CLI without permission
  prompts. This is intentional for this setup.

## Key files

- `kiro/models_anthropic.py` — AnthropicMessage.role (PR #191)
- `kiro/routes_anthropic.py` ~line 688 — `profile_arn_for_payload` resolution
- `kiro/account_manager.py` ~line 475 — reads `profile_arn` from credentials.json entry
- `kiro/auth.py` ~line 146 — stores profile_arn; ~line 421 — overwrites only if token file has it
- `credentials.json` — account-system config (ARN added here)
- `.env` — `PROFILE_ARN` global fallback
- `C:\Users\admin\Desktop\kanban-cmd\start.bat` — launcher; auto-updater pin removed
