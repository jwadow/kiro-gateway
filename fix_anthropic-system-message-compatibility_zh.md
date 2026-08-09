Branch: `fix/anthropic-system-message-compatibility`
Title: `Fix: Kiro Gateway Anthropic system message compatibility`

# Description

- 修正 Claude Code 將 `system` message 放在 Anthropic `messages` 陣列內的請求格式。
- 將 inline system instructions 提升為 Kiro system prompt，不再拒絕或誤當成 user input。
- 保留既有 user/assistant 對話歷史，並新增 regression coverage。

# Root Cause

Claude Code 傳送了 `messages[1].role = "system"`。Gateway 原本的 schema 只接受 `user` 與 `assistant`，因此請求在轉換前就被 Pydantic 以 HTTP 422 拒絕。

## Old Logic

- `AnthropicMessage.role` 只允許 `user` 與 `assistant`。
- Converter 嘗試將每個 message 都當成對話歷史處理。
- Inline system message 無法通過 validation，也無法進入 Kiro adapter。

## New Logic

- 在 `AnthropicMessage` 中允許相容性用的 `system` role。
- 在轉換對話前，先抽出所有 inline system messages。
- 依照原始順序合併 system text，並與 Anthropic 頂層 `system` 欄位合併。
- 只有 user 與 assistant messages 會轉換為 Kiro 對話歷史。

## Why it works

- Claude Code 的實際請求格式可以通過 API model validation。
- System instructions 保留 system 語意，不會被靜默轉成 user message。
- 原有對話順序不受影響。
- 新增測試涵蓋 extraction、排序、content blocks，以及完整 Anthropic-to-Kiro payload。

# DoD

- [x] 接受 Anthropic inline system messages。
- [x] 在 Kiro conversion 中保留 system 語意。
- [x] 新增原始 HTTP 422 問題的 regression tests。
- [x] 執行 gateway targeted test suite。
- [x] 驗證 direct gateway request 與 Claude Code smoke request。

# Code Changes

- `kiro/models_anthropic.py`
  - 允許 `AnthropicMessage` 使用相容性的 `system` role。
- `kiro/converters_anthropic.py`
  - 新增 inline system-message extraction，並與頂層 system prompt 合併。
  - 將 system messages 排除在 user/assistant conversation history 外。
- `tests/unit/test_converters_anthropic.py`
  - 新增 extraction、排序、content blocks 與最終 payload conversion 的 regression coverage。
- `.gitignore`
  - 忽略本地 Python virtual environment，並補齊檔案結尾換行。

# Validate Results

```bash
./.venv/bin/pytest -q \
  tests/unit/test_models_anthropic.py \
  tests/unit/test_converters_anthropic.py \
  tests/unit/test_routes_anthropic.py
```

結果：`249 passed, 1 warning`。

其他 smoke checks：

- Direct Anthropic-compatible gateway request：HTTP 200。
- 經由 gateway 的 Claude Code request：成功回覆。
- Claude Code 實際使用模型：`claude-opus-5`。
- `git diff --check`：通過。

# Commit Messages

- `Fix: Kiro Gateway Anthropic system message compatibility`
  - 接受 Claude Code 的 inline system-message 格式。
  - 保留 system prompt 語意並新增 regression tests。
