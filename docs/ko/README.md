<div align="center">

# 👻 Kiro Gateway

**Kiro API (Amazon Q Developer / AWS CodeWhisperer) 프록시 게이트웨이**

[🇬🇧 English](../../README.md) • [🇷🇺 Русский](../ru/README.md) • [🇨🇳 中文](../zh/README.md) • [🇪🇸 Español](../es/README.md) • [🇮🇩 Indonesia](../id/README.md) • [🇧🇷 Português](../pt/README.md) • [🇯🇵 日本語](../ja/README.md) • 🇰🇷 한국어

[@Jwadow](https://github.com/jwadow)가 ❤️를 담아 제작

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-개발_지원-ff69b4)](#-프로젝트-후원)

*Kiro의 Claude 모델을 Claude Code, OpenCode, OpenClaw, Claw Code, Codex app, Cursor, Cline, Roo Code, Kilo Code, Obsidian, OpenAI SDK, LangChain, Continue 및 기타 OpenAI 또는 Anthropic 호환 도구와 함께 사용*

[모델](#-지원-모델) • [기능](#-기능) • [빠른-시작](#-빠른-시작) • [설정](#%EF%B8%8F-설정) • [💖 후원](#-프로젝트-후원)

</div>

---

## 🤖 사용 가능한 모델 (무료 목록)

> ⚠️ **중요:** 모델 가용성은 Kiro 플랜(무료/유료)에 따라 다릅니다. 게이트웨이는 구독에 따라 IDE 또는 CLI에서 사용 가능한 모델에 대한 액세스를 제공합니다. 아래 목록은 **무료 플랜**에서 일반적으로 사용 가능한 모델을 보여줍니다.

> 🔒 **Claude Opus 4.5**는 2026년 1월 17일에 무료 플랜에서 제거되었습니다. 유료 플랜에서 사용 가능할 수 있습니다 — IDE/CLI의 모델 목록을 확인하세요.

🚀 **Claude Sonnet 4.5** — 균형 잡힌 성능. 코딩, 글쓰기, 범용 작업에 적합.

⚡ **Claude Haiku 4.5** — 번개처럼 빠름. 빠른 응답, 간단한 작업, 채팅에 완벽.

📦 **Claude Sonnet 4** — 이전 세대. 대부분의 사용 사례에서 여전히 강력하고 신뢰할 수 있음.

📦 **Claude 3.7 Sonnet** — 레거시 모델. 하위 호환성을 위해 제공.

💤 **GLM-5** — 오픈 MoE 모델 (744B 파라미터, 40B 활성). 복잡한 시스템 엔지니어링 및 장기 에이전트 작업을 위한 고급 모델.

🐋 **DeepSeek-V3.2** — 오픈 MoE 모델 (685B 파라미터, 37B 활성). 코딩, 추론 및 일반 작업을 위한 균형 잡힌 성능.

🧩 **MiniMax M2.5** — 오픈 MoE 모델 (230B 파라미터, 10B 활성). 향상된 추론 및 작업 처리 기능을 갖춘 개선된 버전.

🧩 **MiniMax M2.1** — 오픈 MoE 모델 (230B 파라미터, 10B 활성). 복잡한 작업, 계획 및 다단계 워크플로우에 적합.

🤖 **Qwen3-Coder-Next** — 오픈 MoE 모델 (80B 파라미터, 3B 활성). 코딩 중심. 개발 및 대규모 프로젝트에 탁월.

> 💡 **스마트 모델 해석:** 어떤 모델 이름 형식이든 사용 가능 — `claude-sonnet-4-5`, `claude-sonnet-4.5`, 또는 `claude-sonnet-4-5-20250929`와 같은 버전 이름도. 게이트웨이가 자동으로 정규화합니다.

---

## ✨ 기능

| 기능 | 설명 |
|------|------|
| 🔌 **OpenAI 호환 API** | OpenAI 호환 도구와 함께 작동 |
| 🔌 **Anthropic 호환 API** | 네이티브 `/v1/messages` 엔드포인트 |
| 🌐 **VPN/프록시 지원** | 제한된 네트워크용 HTTP/SOCKS5 프록시 |
| 🧠 **확장 사고** | 추론 기능은 우리 프로젝트만의 독점 기능 |
| 👁️ **비전 지원** | 모델에 이미지 전송 |
| 🔍 **웹 검색** | 인터넷에서 최신 정보 검색 |
| 🛠️ **도구 호출** | 함수 호출 지원 |
| 💬 **전체 메시지 기록** | 완전한 대화 컨텍스트 전달 |
| 📡 **스트리밍** | 완전한 SSE 스트리밍 지원 |
| 🔄 **재시도 로직** | 오류 시 자동 재시도 (403, 429, 5xx) |
| 📋 **확장 모델 목록** | 버전 모델 포함 |
| 🔐 **스마트 토큰 관리** | 만료 전 자동 갱신 |

---

## 🚀 빠른 시작

**배포 방법을 선택하세요:**
- 🐍 **네이티브 Python** - 완전한 제어, 쉬운 디버깅
- 🐳 **Docker** - 격리된 환경, 쉬운 배포 → [Docker로 이동](#-docker-deployment)

### 사전 요구 사항

- Python 3.10+
- 다음 중 하나:
  - 로그인된 계정이 있는 [Kiro IDE](https://kiro.dev/), 또는
  - AWS SSO (AWS IAM Identity Center, OIDC)가 있는 [Kiro CLI](https://kiro.dev/cli/) - 무료 Builder ID 또는 기업 계정

### 설치

```bash
# 저장소 클론 (Git 필요)
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# 또는 ZIP 다운로드: Code → Download ZIP → 압축 해제 → kiro-gateway 폴더 열기

# 의존성 설치
pip install -r requirements.txt

# 설정 (설정 섹션 참조)
cp .env.example .env
# .env를 복사하고 자격 증명으로 편집

# 서버 시작
python main.py

# 또는 사용자 정의 포트로 (8000이 사용 중인 경우)
python main.py --port 9000
```

서버는 `http://localhost:8000`에서 사용 가능합니다

---

## ⚙️ 설정

### 옵션 1: JSON 자격 증명 파일 (Kiro IDE / Enterprise)

자격 증명 파일 경로 지정:

다음과 함께 작동:
- **Kiro IDE** (표준) - 개인 계정용
- **Enterprise** - SSO가 있는 기업 계정용

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# 프록시 서버를 보호하는 비밀번호 (안전한 문자열 설정)
# 게이트웨이에 연결할 때 api_key로 사용합니다
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 JSON 파일 형식</summary>

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

> **참고:** `~/.aws/sso/cache/`에 두 개의 JSON 파일이 있는 경우 (예: `kiro-auth-token.json` 및 해시 이름의 파일), `KIRO_CREDS_FILE`에서 `kiro-auth-token.json`을 사용하세요. 게이트웨이가 다른 파일을 자동으로 로드합니다.

</details>

### 옵션 2: 환경 변수 (.env 파일)

프로젝트 루트에 `.env` 파일 생성:

```env
# 필수
REFRESH_TOKEN="your_kiro_refresh_token"

# 프록시 서버를 보호하는 비밀번호 (안전한 문자열 설정)
PROXY_API_KEY="my-super-secret-password-123"

# 선택 사항
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### 옵션 3: AWS SSO 자격 증명 (kiro-cli / Enterprise)

AWS SSO (AWS IAM Identity Center)와 함께 `kiro-cli` 또는 Kiro IDE를 사용하는 경우, 게이트웨이가 자동으로 적절한 인증을 감지하고 사용합니다.

무료 Builder ID 계정과 기업 계정 모두에서 작동합니다.

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# 프록시 서버를 보호하는 비밀번호
PROXY_API_KEY="my-super-secret-password-123"

# 참고: AWS SSO (Builder ID 및 기업 계정) 사용자는 PROFILE_ARN 불필요
# 게이트웨이는 그것 없이도 작동합니다
```

<details>
<summary>📄 AWS SSO JSON 파일 형식</summary>

AWS SSO 자격 증명 파일 (`~/.aws/sso/cache/`에서)에는 다음이 포함됩니다:

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

**참고:** AWS SSO (Builder ID 및 기업 계정) 사용자는 `profileArn`이 필요 없습니다. 게이트웨이는 그것 없이도 작동합니다 (지정된 경우 무시됨).

</details>

<details>
<summary>🔍 작동 방식</summary>

게이트웨이는 자격 증명 파일을 기반으로 인증 유형을 자동 감지합니다:

- **Kiro Desktop Auth** (기본값): `clientId`와 `clientSecret`이 없을 때 사용
  - 엔드포인트: `https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**: `clientId`와 `clientSecret`이 있을 때 사용
  - 엔드포인트: `https://oidc.{region}.amazonaws.com/token`

추가 설정 불필요 — 자격 증명 파일만 지정하면 됩니다!

</details>

### 옵션 4: kiro-cli SQLite 데이터베이스

`kiro-cli`를 사용하고 SQLite 데이터베이스를 직접 사용하려는 경우:

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# 프록시 서버를 보호하는 비밀번호
PROXY_API_KEY="my-super-secret-password-123"

# 참고: AWS SSO (Builder ID 및 기업 계정) 사용자는 PROFILE_ARN 불필요
# 게이트웨이는 그것 없이도 작동합니다
```

<details>
<summary>📄 데이터베이스 위치</summary>

| CLI 도구 | 데이터베이스 경로 |
|----------|------------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

게이트웨이는 `auth_kv` 테이블에서 자격 증명을 읽습니다:
- `kirocli:odic:token` 또는 `codewhisperer:odic:token` — 액세스 토큰, 리프레시 토큰, 만료 시간
- `kirocli:odic:device-registration` 또는 `codewhisperer:odic:device-registration` — 클라이언트 ID와 시크릿

다양한 kiro-cli 버전과의 호환성을 위해 두 키 형식 모두 지원됩니다.

</details>

### 자격 증명 얻기

**Kiro IDE 사용자:**
- Kiro IDE에 로그인하고 위의 옵션 1 (JSON 자격 증명 파일) 사용
- 자격 증명 파일은 로그인 후 자동 생성됩니다

**Kiro CLI 사용자:**
- `kiro-cli login`으로 로그인하고 위의 옵션 3 또는 4 사용
- 수동 토큰 추출 불필요!

<details>
<summary>🔧 고급: 수동 토큰 추출</summary>

리프레시 토큰을 수동으로 추출해야 하는 경우 (예: 디버깅용), Kiro IDE 트래픽을 가로챌 수 있습니다:
- 다음으로의 요청 찾기: `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🐳 Docker Deployment

> **Docker 기반 배포.** 네이티브 Python을 선호하시나요? 위의 [빠른 시작](#-빠른-시작)을 참조하세요.

### 빠른 시작

```bash
# 1. 클론 및 설정
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# .env를 자격 증명으로 편집

# 2. docker-compose로 실행
docker-compose up -d

# 3. 상태 확인
docker-compose logs -f
curl http://localhost:8000/health
```

### Docker Run (Compose 없음)

<details>
<summary>🔹 환경 변수 사용</summary>

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
<summary>🔹 자격 증명 파일 사용</summary>

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
<summary>🔹 .env 파일 사용</summary>

```bash
docker run -d -p 8000:8000 --env-file .env --name kiro-gateway ghcr.io/jwadow/kiro-gateway:latest
```

</details>

### Docker Compose 설정

`docker-compose.yml`을 편집하고 OS에 맞는 볼륨 마운트를 주석 해제하세요:

```yaml
volumes:
  # Kiro IDE 자격 증명 (OS 선택)
  - ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro              # Linux/macOS
  # - ${USERPROFILE}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro  # Windows
  
  # kiro-cli 데이터베이스 (OS 선택)
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Linux/macOS
  # - ${USERPROFILE}/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Windows
  
  # 디버그 로그 (선택 사항)
  - ./debug_logs:/app/debug_logs
```

### 관리 명령어

```bash
docker-compose logs -f      # 로그 보기
docker-compose restart      # 재시작
docker-compose down         # 중지
docker-compose pull && docker-compose up -d  # 업데이트
```

<details>
<summary>🔧 소스에서 빌드</summary>

```bash
docker build -t kiro-gateway .
docker run -d -p 8000:8000 --env-file .env kiro-gateway
```

</details>

---

## 🌐 VPN/프록시 지원

**중국, 기업 네트워크 또는 AWS 서비스 연결에 문제가 있는 지역의 사용자를 위한 것입니다.**

게이트웨이는 모든 Kiro API 요청을 VPN 또는 프록시 서버를 통해 라우팅하는 것을 지원합니다. AWS 엔드포인트에 대한 연결 문제가 발생하거나 기업 프록시를 사용해야 하는 경우 필수입니다.

### 설정

`.env` 파일에 추가:

```env
# HTTP 프록시
VPN_PROXY_URL=http://127.0.0.1:7890

# SOCKS5 프록시
VPN_PROXY_URL=socks5://127.0.0.1:1080

# 인증 포함 (기업 프록시)
VPN_PROXY_URL=http://username:password@proxy.company.com:8080

# 프로토콜 없음 (기본값 http://)
VPN_PROXY_URL=192.168.1.100:8080
```

### 지원되는 프로토콜

- ✅ **HTTP** — 표준 프록시 프로토콜
- ✅ **HTTPS** — 보안 프록시 연결
- ✅ **SOCKS5** — 고급 프록시 프로토콜 (VPN 소프트웨어에서 일반적)
- ✅ **인증** — URL에 포함된 사용자명/비밀번호

### 필요한 경우

| 상황 | 해결책 |
|------|--------|
| AWS 연결 타임아웃 | VPN/프록시를 사용하여 트래픽 라우팅 |
| 기업 네트워크 제한 | 회사 프록시 구성 |
| 지역 연결 문제 | 프록시 지원이 있는 VPN 서비스 사용 |
| 개인정보 보호 요구사항 | 자신의 프록시 서버를 통해 라우팅 |

### 프록시 지원이 있는 인기 VPN 소프트웨어

대부분의 VPN 클라이언트는 로컬 프록시 서버를 제공합니다:
- **Sing-box** — HTTP/SOCKS5 프록시 지원이 있는 최신 VPN 클라이언트
- **Clash** — 일반적으로 `http://127.0.0.1:7890`에서 실행
- **V2Ray** — 구성 가능한 SOCKS5/HTTP 프록시
- **Shadowsocks** — SOCKS5 프록시 지원
- **기업 VPN** — 프록시 설정에 대해 IT 부서에 문의

프록시 지원이 필요하지 않으면 `VPN_PROXY_URL`을 비워두세요 (기본값).

---

## 📡 API 레퍼런스

### 엔드포인트

| 엔드포인트 | 메서드 | 설명 |
|-----------|--------|------|
| `/` | GET | 헬스 체크 |
| `/health` | GET | 상세 헬스 체크 |
| `/v1/models` | GET | 사용 가능한 모델 목록 |
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/messages` | POST | Anthropic Messages API |

---

## 💡 사용 예시

### OpenAI API

<details>
<summary>🔹 간단한 cURL 요청</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "안녕하세요!"}],
    "stream": true
  }'
```

> **참고:** `my-super-secret-password-123`을 `.env` 파일에 설정한 `PROXY_API_KEY`로 교체하세요.

</details>

<details>
<summary>🔹 스트리밍 요청</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "system", "content": "당신은 도움이 되는 어시스턴트입니다."},
      {"role": "user", "content": "2+2는 얼마인가요?"}
    ],
    "stream": true
  }'
```

</details>

<details>
<summary>🛠️ 도구 호출 포함</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "런던 날씨는 어때요?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "위치의 날씨 가져오기",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "도시 이름"}
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
    api_key="my-super-secret-password-123"  # .env의 PROXY_API_KEY
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[
        {"role": "system", "content": "당신은 도움이 되는 어시스턴트입니다."},
        {"role": "user", "content": "안녕하세요!"}
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
    api_key="my-super-secret-password-123",  # .env의 PROXY_API_KEY
    model="claude-sonnet-4-5"
)

response = llm.invoke("안녕하세요, 어떻게 지내세요?")
print(response.content)
```

</details>

### Anthropic API

<details>
<summary>🔹 간단한 cURL 요청</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "안녕하세요!"}]
  }'
```

> **참고:** Anthropic API는 `Authorization: Bearer` 대신 `x-api-key` 헤더를 사용합니다. 둘 다 지원됩니다.

</details>

<details>
<summary>🔹 시스템 프롬프트 포함</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "system": "당신은 도움이 되는 어시스턴트입니다.",
    "messages": [{"role": "user", "content": "안녕하세요!"}]
  }'
```

> **참고:** Anthropic API에서 `system`은 메시지가 아닌 별도의 필드입니다.

</details>

<details>
<summary>📡 스트리밍</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "안녕하세요!"}]
  }'
```

</details>

<details>
<summary>🐍 Python Anthropic SDK</summary>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="my-super-secret-password-123",  # .env의 PROXY_API_KEY
    base_url="http://localhost:8000"
)

# 비스트리밍
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "안녕하세요!"}]
)
print(response.content[0].text)

# 스트리밍
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "안녕하세요!"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

</details>

---

## 🔧 디버깅

디버그 로깅은 **기본적으로 비활성화**되어 있습니다. 활성화하려면 `.env`에 추가:

```env
# 디버그 로깅 모드:
# - off: 비활성화 (기본값)
# - errors: 실패한 요청만 로그 저장 (4xx, 5xx) - 문제 해결에 권장
# - all: 모든 요청 로그 저장 (요청마다 덮어쓰기)
DEBUG_MODE=errors
```

### 디버그 모드

| 모드 | 설명 | 용도 |
|------|------|------|
| `off` | 비활성화 (기본값) | 프로덕션 |
| `errors` | 실패한 요청만 로그 저장 (4xx, 5xx) | **문제 해결에 권장** |
| `all` | 모든 요청 로그 저장 | 개발/디버깅 |

### 디버그 파일

활성화되면 요청이 `debug_logs/` 폴더에 기록됩니다:

| 파일 | 설명 |
|------|------|
| `request_body.json` | 클라이언트로부터의 수신 요청 (OpenAI 형식) |
| `kiro_request_body.json` | Kiro API로 전송된 요청 |
| `response_stream_raw.txt` | Kiro로부터의 원시 스트림 |
| `response_stream_modified.txt` | 변환된 스트림 (OpenAI 형식) |
| `app_logs.txt` | 요청에 대한 애플리케이션 로그 |
| `error_info.json` | 오류 세부 정보 (오류 시에만) |

---

## 📜 라이선스

이 프로젝트는 **GNU Affero General Public License v3.0 (AGPL-3.0)**으로 라이선스됩니다.

이것은 다음을 의미합니다:
- ✅ 이 소프트웨어를 사용, 수정, 배포할 수 있습니다
- ✅ 상업적 목적으로 사용할 수 있습니다
- ⚠️ 소프트웨어를 배포할 때 **소스 코드를 공개해야 합니다**
- ⚠️ **네트워크 사용은 배포입니다** — 수정된 버전을 서버에서 실행하고 다른 사람이 상호 작용할 수 있게 하면 소스 코드를 그들에게 제공해야 합니다
- ⚠️ 수정 사항은 동일한 라이선스로 릴리스해야 합니다

전체 라이선스 텍스트는 [LICENSE](../../LICENSE) 파일을 참조하세요.

### 왜 AGPL-3.0인가?

AGPL-3.0은 이 소프트웨어에 대한 개선이 전체 커뮤니티에 이익이 되도록 보장합니다. 이 게이트웨이를 수정하고 서비스로 배포하는 경우 사용자와 개선 사항을 공유해야 합니다.

### 기여자 라이선스 계약 (CLA)

이 프로젝트에 기여를 제출함으로써 [기여자 라이선스 계약 (CLA)](../../CLA.md)의 조건에 동의하게 됩니다. 이것은 다음을 보장합니다:
- 기여를 제출할 권리가 있음
- 메인테이너에게 기여를 사용하고 재라이선스할 권리를 부여함
- 프로젝트가 법적으로 보호됨

---

## 💖 프로젝트 후원

<div align="center">

<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Smilies/Smiling%20Face%20with%20Hearts.png" alt="Love" width="80" />

**이 프로젝트가 시간이나 돈을 절약해 주었다면 후원을 고려해 주세요!**

모든 기여가 이 프로젝트를 유지하고 성장시키는 데 도움이 됩니다

<br>

### 🤑 기부

[**☕ 일회성 후원**](https://app.lava.top/products/b4e34d12-3b6b-49b7-be50-50b6a20ed262/f3ea941f-de73-4ad1-bbb6-f82042ef8132)

<br>

### 🪙 또는 암호화폐 전송

| 통화 | 네트워크 | 주소 |
|:----:|:-------:|:-----|
| **USDT** | TRC20 | `TSVtgRc9pkC1UgcbVeijBHjFmpkYHDRu26` |
| **BTC** | Bitcoin | `12GZqxqpcBsqJ4Vf1YreLqwoMGvzBPgJq6` |
| **ETH** | Ethereum | `0xc86eab3bba3bbaf4eb5b5fff8586f1460f1fd395` |
| **SOL** | Solana | `9amykF7KibZmdaw66a1oqYJyi75fRqgdsqnG66AK3jvh` |
| **TON** | TON | `UQBVh8T1H3GI7gd7b-_PPNnxHYYxptrcCVf3qQk5v41h3QTM` |

</div>

---

## ⚠️ 면책 조항

이 프로젝트는 Amazon Web Services (AWS), Anthropic 또는 Kiro IDE와 제휴, 승인 또는 후원되지 않습니다. 자신의 책임 하에 사용하고 기본 API의 서비스 약관을 준수하세요.

---

<div align="center">

**[⬆ 맨 위로](#-kiro-gateway)**

</div>
