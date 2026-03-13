<div align="center">

# 👻 Kiro Gateway

**Kiro API (Amazon Q Developer / AWS CodeWhisperer) 用プロキシゲートウェイ**

[🇬🇧 English](../../README.md) • [🇷🇺 Русский](../ru/README.md) • [🇨🇳 中文](../zh/README.md) • [🇪🇸 Español](../es/README.md) • [🇮🇩 Indonesia](../id/README.md) • [🇧🇷 Português](../pt/README.md) • [🇰🇷 한국어](../ko/README.md)

[@Jwadow](https://github.com/jwadow) が ❤️ を込めて作成

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-開発を支援-ff69b4)](#-プロジェクトを支援)

*Kiro の Claude モデルを Claude Code、OpenCode、Codex app、Cursor、Cline、Roo Code、Kilo Code、Obsidian、OpenAI SDK、LangChain、Continue などの OpenAI または Anthropic 互換ツールで使用*

[モデル](#-対応モデル) • [機能](#-機能) • [クイックスタート](#-クイックスタート) • [設定](#%EF%B8%8F-設定) • [💖 サポート](#-プロジェクトを支援)

</div>

---

## 🤖 利用可能なモデル

> ⚠️ **重要：** モデルの利用可能性は Kiro プラン（無料/有料）によって異なります。ゲートウェイは、サブスクリプションに基づいて IDE または CLI で利用可能なモデルへのアクセスを提供します。以下のリストは**無料プラン**で一般的に利用可能なモデルを示しています。

> 🔒 **Claude Opus 4.5** は 2026年1月17日に無料プランから削除されました。有料プランで利用可能な場合があります — IDE/CLI のモデルリストを確認してください。

🚀 **Claude Sonnet 4.5** — バランスの取れたパフォーマンス。コーディング、ライティング、汎用タスクに最適。

⚡ **Claude Haiku 4.5** — 超高速。クイックレスポンス、シンプルなタスク、チャットに最適。

📦 **Claude Sonnet 4** — 前世代モデル。ほとんどのユースケースで依然として強力で信頼性が高い。

📦 **Claude 3.7 Sonnet** — レガシーモデル。後方互換性のために利用可能。

🐋 **DeepSeek-V3.2** — オープンMoEモデル（685Bパラメータ、37B活性）。コーディング、推論、一般的なタスクのバランスの取れたパフォーマンス。

🧩 **MiniMax M2.1** — オープンMoEモデル（230Bパラメータ、10B活性）。複雑なタスク、計画、マルチステップワークフローに最適。

🤖 **Qwen3-Coder-Next** — オープンMoEモデル（80Bパラメータ、3B活性）。コーディング重視。開発と大規模プロジェクトに最適。

> 💡 **スマートモデル解決:** どんなモデル名形式でも使用可能 — `claude-sonnet-4-5`、`claude-sonnet-4.5`、または `claude-sonnet-4-5-20250929` のようなバージョン付き名前も。ゲートウェイが自動的に正規化します。

---

## ✨ 機能

| 機能 | 説明 |
|------|------|
| 🔌 **OpenAI 互換 API** | OpenAI 互換のあらゆるツールで動作 |
| 🔌 **Anthropic 互換 API** | ネイティブ `/v1/messages` エンドポイント |
| 🌐 **VPN/プロキシサポート** | 制限されたネットワーク向けの HTTP/SOCKS5 プロキシ |
| 🧠 **拡張思考** | 推論機能は本プロジェクト独自の機能 |
| 👁️ **ビジョンサポート** | モデルに画像を送信 |
| 🛠️ **ツール呼び出し** | 関数呼び出しをサポート |
| 💬 **完全なメッセージ履歴** | 完全な会話コンテキストを渡す |
| 📡 **ストリーミング** | 完全な SSE ストリーミングサポート |
| 🔄 **リトライロジック** | エラー時の自動リトライ（403、429、5xx） |
| 📋 **拡張モデルリスト** | バージョン付きモデルを含む |
| 🔐 **スマートトークン管理** | 有効期限前に自動更新 |

---

## 🚀 クイックスタート

**デプロイ方法を選択してください:**
- 🐍 **ネイティブ Python** - 完全な制御、簡単なデバッグ
- 🐳 **Docker** - 隔離された環境、簡単なデプロイ → [Docker へジャンプ](#-docker-deployment)

### 前提条件

- Python 3.10+
- 以下のいずれか：
  - ログイン済みアカウントの [Kiro IDE](https://kiro.dev/)、または
  - AWS SSO (AWS IAM Identity Center, OIDC) を使用した [Kiro CLI](https://kiro.dev/cli/) - 無料の Builder ID または企業アカウント

### インストール

```bash
# リポジトリをクローン（Git が必要）
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# または ZIP をダウンロード：Code → Download ZIP → 解凍 → kiro-gateway フォルダを開く

# 依存関係をインストール
pip install -r requirements.txt

# 設定（設定セクションを参照）
cp .env.example .env
# .env をコピーして認証情報を編集

# サーバーを起動
python main.py

# またはカスタムポートで（8000 が使用中の場合）
python main.py --port 9000
```

サーバーは `http://localhost:8000` で利用可能になります

---

## ⚙️ 設定

### オプション 1：JSON 認証情報ファイル (Kiro IDE / Enterprise)

認証情報ファイルへのパスを指定：

対応環境：
- **Kiro IDE**（標準）- 個人アカウント用
- **Enterprise** - SSO を使用した企業アカウント用

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# プロキシサーバーを保護するパスワード（任意の安全な文字列を設定）
# ゲートウェイに接続する際に api_key として使用します
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 JSON ファイル形式</summary>

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "profileArn": "arn:aws:codewhisperer:us-east-1:...",
  "region": "us-east-1",
  "clientIdHash": "abc123..."  // Optional: for corporate SSO setups
}
```

> **注意：** `~/.aws/sso/cache/` に 2 つの JSON ファイルがある場合（例：`kiro-auth-token.json` とハッシュ名のファイル）、`KIRO_CREDS_FILE` で `kiro-auth-token.json` を使用してください。ゲートウェイが他のファイルを自動的に読み込みます。

</details>

### オプション 2：環境変数（.env ファイル）

プロジェクトルートに `.env` ファイルを作成：

```env
# 必須
REFRESH_TOKEN="your_kiro_refresh_token"

# プロキシサーバーを保護するパスワード（任意の安全な文字列を設定）
PROXY_API_KEY="my-super-secret-password-123"

# オプション
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### オプション 3：AWS SSO 認証情報 (kiro-cli / Enterprise)

AWS SSO (AWS IAM Identity Center) で `kiro-cli` または Kiro IDE を使用している場合、ゲートウェイは自動的に適切な認証を検出して使用します。

無料の Builder ID アカウントと企業アカウントの両方で動作します。

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# プロキシサーバーを保護するパスワード
PROXY_API_KEY="my-super-secret-password-123"

# 注意：AWS SSO (Builder ID および企業アカウント) ユーザーは PROFILE_ARN 不要
# ゲートウェイはそれなしで動作します
```

<details>
<summary>📄 AWS SSO JSON ファイル形式</summary>

AWS SSO 認証情報ファイル（`~/.aws/sso/cache/` から）には以下が含まれます：

```json
{
  "accessToken": "eyJ...",
  "refreshToken": "eyJ...",
  "expiresAt": "2025-01-12T23:00:00.000Z",
  "region": "us-east-1",
  "clientId": "...",
  "clientSecret": "..."
}
```

**注意：** AWS SSO (Builder ID および企業アカウント) ユーザーは `profileArn` 不要。ゲートウェイはそれなしで動作します（指定された場合は無視されます）。

</details>

<details>
<summary>🔍 仕組み</summary>

ゲートウェイは認証情報ファイルに基づいて認証タイプを自動検出します：

- **Kiro Desktop Auth**（デフォルト）：`clientId` と `clientSecret` が存在しない場合に使用
  - エンドポイント：`https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**：`clientId` と `clientSecret` が存在する場合に使用
  - エンドポイント：`https://oidc.{region}.amazonaws.com/token`

追加設定は不要 — 認証情報ファイルを指定するだけ！

</details>

### オプション 4：kiro-cli SQLite データベース

`kiro-cli` を使用していて、その SQLite データベースを直接使用したい場合：

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# プロキシサーバーを保護するパスワード
PROXY_API_KEY="my-super-secret-password-123"

# 注意：AWS SSO (Builder ID および企業アカウント) ユーザーは PROFILE_ARN 不要
# ゲートウェイはそれなしで動作します
```

<details>
<summary>📄 データベースの場所</summary>

| CLI ツール | データベースパス |
|-----------|-----------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

ゲートウェイは `auth_kv` テーブルから認証情報を読み取ります：
- `kirocli:odic:token` または `codewhisperer:odic:token` — アクセストークン、リフレッシュトークン、有効期限
- `kirocli:odic:device-registration` または `codewhisperer:odic:device-registration` — クライアント ID とシークレット

異なる kiro-cli バージョンとの互換性のため、両方のキー形式がサポートされています。

</details>

### 認証情報の取得

**Kiro IDE ユーザー向け：**
- Kiro IDE にログインして上記のオプション 1（JSON 認証情報ファイル）を使用
- 認証情報ファイルはログイン後に自動作成されます

**Kiro CLI ユーザー向け：**
- `kiro-cli login` でログインして上記のオプション 3 または 4 を使用
- 手動でのトークン抽出は不要！

<details>
<summary>🔧 上級者向け：手動トークン抽出</summary>

リフレッシュトークンを手動で抽出する必要がある場合（例：デバッグ用）、Kiro IDE のトラフィックをインターセプトできます：
- 以下へのリクエストを探す：`prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🐳 Docker Deployment

> **Docker ベースのデプロイ。** ネイティブ Python を希望しますか？ 上記の [クイックスタート](#-クイックスタート) を参照してください。

### クイックスタート

```bash
# 1. クローンと設定
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# .env を認証情報で編集

# 2. docker-compose で実行
docker-compose up -d

# 3. ステータスを確認
docker-compose logs -f
curl http://localhost:8000/health
```

### Docker Run (Compose なし)

<details>
<summary>🔹 環境変数を使用</summary>

```bash
docker run -d \
  -p 8000:8000 \
  -e PROXY_API_KEY="my-super-secret-password-123" \
  -e REFRESH_TOKEN="your_refresh_token" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest
```

</details>

<details>
<summary>🔹 認証情報ファイルを使用</summary>

**Linux/macOS:**
```bash
docker run -d \
  -p 8000:8000 \
  -v ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro \
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json \
  -e PROXY_API_KEY="my-super-secret-password-123" \
  --name kiro-gateway \
  ghcr.io/jwadow/kiro-gateway:latest
```

**Windows (PowerShell):**
```powershell
docker run -d `
  -p 8000:8000 `
  -v ${HOME}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro `
  -e KIRO_CREDS_FILE=/home/kiro/.aws/sso/cache/kiro-auth-token.json `
  -e PROXY_API_KEY="my-super-secret-password-123" `
  --name kiro-gateway `
  ghcr.io/jwadow/kiro-gateway:latest
```

</details>

<details>
<summary>🔹 .env ファイルを使用</summary>

```bash
docker run -d -p 8000:8000 --env-file .env --name kiro-gateway ghcr.io/jwadow/kiro-gateway:latest
```

</details>

### Docker Compose 設定

`docker-compose.yml` を編集し、お使いの OS のボリュームマウントをコメント解除します：

```yaml
volumes:
  # Kiro IDE 認証情報（OS を選択）
  - ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro              # Linux/macOS
  # - ${USERPROFILE}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro  # Windows
  
  # kiro-cli データベース（OS を選択）
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Linux/macOS
  # - ${USERPROFILE}/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Windows
  
  # デバッグログ（オプション）
  - ./debug_logs:/app/debug_logs
```

### 管理コマンド

```bash
docker-compose logs -f      # ログを表示
docker-compose restart      # 再起動
docker-compose down         # 停止
docker-compose pull && docker-compose up -d  # 更新
```

<details>
<summary>🔧 ソースからビルド</summary>

```bash
docker build -t kiro-gateway .
docker run -d -p 8000:8000 --env-file .env kiro-gateway
```

</details>

---

## 🌐 VPN/プロキシサポート

**中国、企業ネットワーク、または AWS サービスへの接続に問題がある地域のユーザー向け。**

ゲートウェイは、すべての Kiro API リクエストを VPN またはプロキシサーバーでルーティングすることをサポートしています。AWS エンドポイントへの接続に問題が発生した場合、または企業プロキシを使用する必要がある場合に必須です。

### 設定

`.env` ファイルに追加：

```env
# HTTP プロキシ
VPN_PROXY_URL=http://127.0.0.1:7890

# SOCKS5 プロキシ
VPN_PROXY_URL=socks5://127.0.0.1:1080

# 認証付き（企業プロキシ）
VPN_PROXY_URL=http://username:password@proxy.company.com:8080

# プロトコルなし（デフォルトは http://）
VPN_PROXY_URL=192.168.1.100:8080
```

### サポートされるプロトコル

- ✅ **HTTP** — 標準プロキシプロトコル
- ✅ **HTTPS** — セキュアプロキシ接続
- ✅ **SOCKS5** — 高度なプロキシプロトコル（VPN ソフトウェアで一般的）
- ✅ **認証** — URL に埋め込まれたユーザー名/パスワード

### 必要な場合

| 状況 | 解決策 |
|------|--------|
| AWS への接続タイムアウト | VPN/プロキシを使用してトラフィックをルーティング |
| 企業ネットワーク制限 | 企業のプロキシを設定 |
| 地域的な接続問題 | プロキシサポート付き VPN サービスを使用 |
| プライバシー要件 | 独自のプロキシサーバーでルーティング |

### プロキシサポート付きの人気 VPN ソフトウェア

ほとんどの VPN クライアントはローカルプロキシサーバーを提供します：
- **Sing-box** — HTTP/SOCKS5 プロキシサポート付きの最新 VPN クライアント
- **Clash** — 通常 `http://127.0.0.1:7890` で実行
- **V2Ray** — 設定可能な SOCKS5/HTTP プロキシ
- **Shadowsocks** — SOCKS5 プロキシサポート
- **企業 VPN** — プロキシ設定について IT 部門に確認

プロキシサポートが不要な場合は、`VPN_PROXY_URL` を空のままにしてください（デフォルト）。

---

## 📡 API リファレンス

### エンドポイント

| エンドポイント | メソッド | 説明 |
|---------------|---------|------|
| `/` | GET | ヘルスチェック |
| `/health` | GET | 詳細ヘルスチェック |
| `/v1/models` | GET | 利用可能なモデル一覧 |
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/messages` | POST | Anthropic Messages API |

---

## 💡 使用例

### OpenAI API

<details>
<summary>🔹 シンプルな cURL リクエスト</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "こんにちは！"}],
    "stream": true
  }'
```

> **注意：** `my-super-secret-password-123` を `.env` ファイルで設定した `PROXY_API_KEY` に置き換えてください。

</details>

<details>
<summary>🔹 ストリーミングリクエスト</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "system", "content": "あなたは親切なアシスタントです。"},
      {"role": "user", "content": "2+2 は何ですか？"}
    ],
    "stream": true
  }'
```

</details>

<details>
<summary>🛠️ ツール呼び出し付き</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "ロンドンの天気は？"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "場所の天気を取得",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "都市名"}
          },
          "required": ["location"]
        }
      }
    }]
  }'
```

</details>

<details>
<summary>🐍 Python OpenAI SDK</summary>

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="my-super-secret-password-123"  # .env の PROXY_API_KEY
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[
        {"role": "system", "content": "あなたは親切なアシスタントです。"},
        {"role": "user", "content": "こんにちは！"}
    ],
    stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

</details>

<details>
<summary>🦜 LangChain</summary>

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://localhost:8000/v1",
    api_key="my-super-secret-password-123",  # .env の PROXY_API_KEY
    model="claude-sonnet-4-5"
)

response = llm.invoke("こんにちは、お元気ですか？")
print(response.content)
```

</details>

### Anthropic API

<details>
<summary>🔹 シンプルな cURL リクエスト</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "こんにちは！"}]
  }'
```

> **注意：** Anthropic API は `Authorization: Bearer` の代わりに `x-api-key` ヘッダーを使用します。両方サポートされています。

</details>

<details>
<summary>🔹 システムプロンプト付き</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "system": "あなたは親切なアシスタントです。",
    "messages": [{"role": "user", "content": "こんにちは！"}]
  }'
```

> **注意：** Anthropic API では `system` はメッセージではなく別のフィールドです。

</details>

<details>
<summary>📡 ストリーミング</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "こんにちは！"}]
  }'
```

</details>

<details>
<summary>🐍 Python Anthropic SDK</summary>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="my-super-secret-password-123",  # .env の PROXY_API_KEY
    base_url="http://localhost:8000"
)

# 非ストリーミング
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "こんにちは！"}]
)
print(response.content[0].text)

# ストリーミング
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "こんにちは！"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

</details>

---

## 🔧 デバッグ

デバッグログは**デフォルトで無効**です。有効にするには `.env` に追加：

```env
# デバッグログモード：
# - off：無効（デフォルト）
# - errors：失敗したリクエストのみログを保存（4xx、5xx）- トラブルシューティングに推奨
# - all：すべてのリクエストのログを保存（リクエストごとに上書き）
DEBUG_MODE=errors
```

### デバッグモード

| モード | 説明 | 用途 |
|--------|------|------|
| `off` | 無効（デフォルト） | 本番環境 |
| `errors` | 失敗したリクエストのみログを保存（4xx、5xx） | **トラブルシューティングに推奨** |
| `all` | すべてのリクエストのログを保存 | 開発/デバッグ |

### デバッグファイル

有効にすると、リクエストは `debug_logs/` フォルダにログされます：

| ファイル | 説明 |
|---------|------|
| `request_body.json` | クライアントからの受信リクエスト（OpenAI 形式） |
| `kiro_request_body.json` | Kiro API に送信されたリクエスト |
| `response_stream_raw.txt` | Kiro からの生ストリーム |
| `response_stream_modified.txt` | 変換されたストリーム（OpenAI 形式） |
| `app_logs.txt` | リクエストのアプリケーションログ |
| `error_info.json` | エラー詳細（エラー時のみ） |

---

## 📜 ライセンス

このプロジェクトは **GNU Affero General Public License v3.0 (AGPL-3.0)** でライセンスされています。

これは以下を意味します：
- ✅ このソフトウェアを使用、変更、配布できます
- ✅ 商用目的で使用できます
- ⚠️ ソフトウェアを配布する際は**ソースコードを公開する必要があります**
- ⚠️ **ネットワーク使用は配布です** — 変更したバージョンをサーバーで実行し、他者がそれと対話できるようにする場合、ソースコードを彼らに提供する必要があります
- ⚠️ 変更は同じライセンスでリリースする必要があります

完全なライセンステキストは [LICENSE](../../LICENSE) ファイルを参照してください。

### なぜ AGPL-3.0？

AGPL-3.0 は、このソフトウェアへの改善がコミュニティ全体に利益をもたらすことを保証します。このゲートウェイを変更してサービスとしてデプロイする場合、改善をユーザーと共有する必要があります。

### コントリビューターライセンス契約 (CLA)

このプロジェクトへの貢献を提出することで、[コントリビューターライセンス契約 (CLA)](../../CLA.md) の条件に同意したことになります。これにより以下が保証されます：
- 貢献を提出する権利があること
- メンテナーに貢献を使用および再ライセンスする権利を付与すること
- プロジェクトが法的に保護されること

---

## 💖 プロジェクトを支援

<div align="center">

<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Smilies/Smiling%20Face%20with%20Hearts.png" alt="Love" width="80" />

**このプロジェクトが時間やお金を節約したなら、支援をご検討ください！**

すべての貢献がこのプロジェクトの維持と成長に役立ちます

<br>

### 🤑 寄付

[**☕ 一回限りの寄付**](https://app.lava.top/jwadow?tabId=donate) &nbsp;•&nbsp; [**💎 月額サポート**](https://app.lava.top/jwadow?tabId=subscriptions)

<br>

### 🪙 または暗号通貨を送信

| 通貨 | ネットワーク | アドレス |
|:----:|:----------:|:--------|
| **USDT** | TRC20 | `TSVtgRc9pkC1UgcbVeijBHjFmpkYHDRu26` |
| **BTC** | Bitcoin | `12GZqxqpcBsqJ4Vf1YreLqwoMGvzBPgJq6` |
| **ETH** | Ethereum | `0xc86eab3bba3bbaf4eb5b5fff8586f1460f1fd395` |
| **SOL** | Solana | `9amykF7KibZmdaw66a1oqYJyi75fRqgdsqnG66AK3jvh` |
| **TON** | TON | `UQBVh8T1H3GI7gd7b-_PPNnxHYYxptrcCVf3qQk5v41h3QTM` |

</div>

---

## ⚠️ 免責事項

このプロジェクトは Amazon Web Services (AWS)、Anthropic、または Kiro IDE と提携、承認、またはスポンサーされていません。自己責任で使用し、基盤となる API の利用規約に従ってください。

---

<div align="center">

**[⬆ トップに戻る](#-kiro-gateway)**

</div>
