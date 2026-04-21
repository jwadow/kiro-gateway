<div align="center">

# 👻 Kiro Gateway

**Прокси-шлюз для Kiro API (Amazon Q Developer / AWS CodeWhisperer)**

[🇬🇧 English](../../README.md) • 🇷🇺 Русский • [🇨🇳 中文](../zh/README.md) • [🇪🇸 Español](../es/README.md) • [🇮🇩 Indonesia](../id/README.md) • [🇧🇷 Português](../pt/README.md) • [🇯🇵 日本語](../ja/README.md) • [🇰🇷 한국어](../ko/README.md)

Сделано с ❤️ от [@Jwadow](https://github.com/jwadow)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-Поддержать_разработку-ff69b4)](#-поддержать-проект)

*Используйте модели Claude из Kiro с Claude Code, OpenCode, OpenClaw, Claw Code, Codex app, Cursor, Cline, Roo Code, Kilo Code, Obsidian, OpenAI SDK, LangChain, Continue и другими инструментами, совместимыми с OpenAI или Anthropic*

[Модели](#-поддерживаемые-модели) • [Возможности](#-возможности) • [Быстрый старт](#-быстрый-старт) • [Конфигурация](#%EF%B8%8F-конфигурация) • [💖 Поддержать](#-поддержать-проект)

</div>

---

## 🤖 Доступные модели (Бесплатный список)

> ⚠️ **Важно:** Доступность моделей зависит от вашего тарифа Kiro (бесплатный/платный). Шлюз предоставляет доступ к тем моделям, которые доступны в вашей IDE или CLI в зависимости от вашей подписки. Список ниже показывает модели, обычно доступные на **бесплатном тарифе**.

> 🔒 **Claude Opus 4.5** был удалён из бесплатного тарифа 17 января 2026 года. Он может быть доступен на платных тарифах — проверьте список моделей в вашей IDE/CLI.

🚀 **Claude Sonnet 4.5** — Сбалансированная производительность. Отлично подходит для программирования, написания текстов и задач общего назначения.

⚡ **Claude Haiku 4.5** — Молниеносная скорость. Идеальна для быстрых ответов, простых задач и чата.

📦 **Claude Sonnet 4** — Предыдущее поколение. По-прежнему мощная и надёжная для большинства задач.

📦 **Claude 3.7 Sonnet** — Устаревшая модель. Доступна для обратной совместимости.

💤 **GLM-5** — Открытая MoE модель (744B параметров, 40B активных). Продвинутая модель для сложной системной инженерии и долгосрочных агентных задач.

🐋 **DeepSeek-V3.2** — Открытая MoE модель (685B параметров, 37B активных). Сбалансированная производительность для программирования, рассуждений и задач общего назначения.

🧩 **MiniMax M2.5** — Открытая MoE модель (230B параметров, 10B активных). Улучшенная версия с расширенными возможностями рассуждений и обработки задач.

🧩 **MiniMax M2.1** — Открытая MoE модель (230B параметров, 10B активных). Отлично подходит для сложных задач, планирования и многошаговых рабочих процессов.

🤖 **Qwen3-Coder-Next** — Открытая MoE модель (80B параметров, 3B активных). Ориентирована на программирование. Отлично подходит для разработки и крупных проектов.

> 💡 **Умное разрешение моделей:** Используйте любой формат названия модели — `claude-sonnet-4-5`, `claude-sonnet-4.5` или даже версионные названия вроде `claude-sonnet-4-5-20250929`. Шлюз автоматически нормализует их.

---

## ✨ Возможности

| Возможность | Описание |
|-------------|----------|
| 🔌 **API, совместимый с OpenAI** | Работает с любым инструментом, совместимым с OpenAI |
| 🔌 **API, совместимый с Anthropic** | Нативный эндпоинт `/v1/messages` |
| 🌐 **Поддержка VPN/Proxy** | HTTP/SOCKS5 прокси для ограниченных сетей |
| 🧠 **Расширенное мышление** | Режим рассуждений — эксклюзив нашего проекта |
| 👁️ **Поддержка изображений** | Отправляйте изображения модели |
| 🔍 **Веб-поиск** | Поиск актуальной информации в интернете |
| 🛠️ **Вызов инструментов** | Поддержка вызова функций |
| 💬 **Полная история сообщений** | Передаёт полный контекст разговора |
| 📡 **Стриминг** | Полная поддержка SSE-стриминга |
| 🔄 **Логика повторных попыток** | Автоматические повторы при ошибках (403, 429, 5xx) |
| 📋 **Расширенный список моделей** | Включая версионные модели |
| 🔐 **Умное управление токенами** | Автоматическое обновление до истечения срока |

---

## 🚀 Быстрый старт

**Выберите метод развертывания:**
- 🐍 **Нативный Python** - Полный контроль, легкая отладка
- 🐳 **Docker** - Изолированная среда, простое развертывание → [перейти к Docker](#-docker-deployment)

### Предварительные требования

- Python 3.10+
- Одно из следующего:
  - [Kiro IDE](https://kiro.dev/) с авторизованным аккаунтом, ИЛИ
  - [Kiro CLI](https://kiro.dev/cli/) с AWS SSO (AWS IAM Identity Center, OIDC) - бесплатный Builder ID или корпоративный аккаунт

### Установка

```bash
# Клонируйте репозиторий (требуется Git)
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# Или скачайте ZIP: Code → Download ZIP → распакуйте → откройте папку kiro-gateway

# Установите зависимости
pip install -r requirements.txt

# Настройте (см. раздел Конфигурация)
cp .env.example .env
# Скопируйте и отредактируйте .env с вашими учётными данными

# Запустите сервер
python main.py

# Или с другим портом (если 8000 занят)
python main.py --port 9000
```

Сервер будет доступен по адресу `http://localhost:8000`

---

## ⚙️ Конфигурация

### Вариант 1: JSON-файл с учётными данными (Kiro IDE / Enterprise)

Укажите путь к файлу с учётными данными:

Работает с:
- **Kiro IDE** (стандартный) - для личных аккаунтов
- **Enterprise** - для корпоративных аккаунтов с SSO

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Пароль для защиты ВАШЕГО прокси-сервера (придумайте любую надёжную строку)
# Вы будете использовать его как api_key при подключении к вашему шлюзу
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 Формат JSON-файла</summary>

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

> **Примечание:** Если у вас есть два JSON файла в `~/.aws/sso/cache/` (например, `kiro-auth-token.json` и файл с хешированным названием), используйте `kiro-auth-token.json` в `KIRO_CREDS_FILE`. Шлюз автоматически загрузит другой файл.

</details>

### Вариант 2: Переменные окружения (файл .env)

Создайте файл `.env` в корне проекта:

```env
# Обязательно
REFRESH_TOKEN="ваш_kiro_refresh_token"

# Пароль для защиты ВАШЕГО прокси-сервера (придумайте любую надёжную строку)
PROXY_API_KEY="my-super-secret-password-123"

# Опционально
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### Вариант 3: Учётные данные AWS SSO (kiro-cli / Enterprise)

Если вы используете `kiro-cli` или Kiro IDE с AWS SSO (AWS IAM Identity Center), шлюз автоматически обнаружит и использует соответствующую аутентификацию.

Работает как с бесплатными аккаунтами Builder ID, так и с корпоративными аккаунтами.

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# Пароль для защиты ВАШЕГО прокси-сервера
PROXY_API_KEY="my-super-secret-password-123"

# Примечание: PROFILE_ARN НЕ нужен для AWS SSO (Builder ID и корпоративные аккаунты)
# Шлюз будет работать без него
```

<details>
<summary>📄 Формат JSON-файла AWS SSO</summary>

Файлы учётных данных AWS SSO (из `~/.aws/sso/cache/`) содержат:

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

**Примечание:** Пользователям AWS SSO (Builder ID и корпоративные аккаунты) НЕ нужен `profileArn`. Шлюз будет работать без него (если указан, он будет проигнорирован).

</details>

<details>
<summary>🔍 Как это работает</summary>

Шлюз автоматически определяет тип аутентификации на основе файла учётных данных:

- **Kiro Desktop Auth** (по умолчанию): Используется, когда `clientId` и `clientSecret` НЕ присутствуют
  - Эндпоинт: `https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**: Используется, когда `clientId` и `clientSecret` присутствуют
  - Эндпоинт: `https://oidc.{region}.amazonaws.com/token`

Дополнительная настройка не требуется — просто укажите путь к вашему файлу учётных данных!

</details>

### Вариант 4: SQLite-база данных kiro-cli

Если вы используете `kiro-cli` и предпочитаете использовать его SQLite-базу данных напрямую:

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# Пароль для защиты ВАШЕГО прокси-сервер
PROXY_API_KEY="my-super-secret-password-123"

# Примечание: PROFILE_ARN НЕ нужен для AWS SSO (Builder ID и корпоративные аккаунты)
# Шлюз будет работать без него
```

<details>
<summary>📄 Расположение баз данных</summary>

| CLI-инструмент | Путь к базе данных |
|----------------|-------------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

Шлюз читает учётные данные из таблицы `auth_kv`, которая хранит:
- `kirocli:odic:token` или `codewhisperer:odic:token` — токен доступа, токен обновления, срок действия
- `kirocli:odic:device-registration` или `codewhisperer:odic:device-registration` — ID клиента и секрет

Оба формата ключей поддерживаются для совместимости с разными версиями kiro-cli.

</details>

### Получение учётных данных

**Для пользователей Kiro IDE:**
- Войдите в Kiro IDE и используйте Вариант 1 выше (JSON-файл с учётными данными)
- Файл учётных данных создаётся автоматически после входа

**Для пользователей Kiro CLI:**
- Войдите с помощью `kiro-cli login` и используйте Вариант 3 или Вариант 4 выше
- Ручное извлечение токена не требуется!

<details>
<summary>🔧 Продвинутое: Ручное извлечение токена</summary>

Если вам нужно вручную извлечь refresh token (например, для отладки), вы можете перехватить трафик Kiro IDE:
- Ищите запросы к: `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🐳 Docker Deployment

> **Docker-развертывание.** Предпочитаете нативный Python? Смотрите [Быстрый старт](#-быстрый-старт) выше.

### Быстрый старт

```bash
# 1. Клонируйте и настройте
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# Отредактируйте .env с вашими учётными данными

# 2. Запустите с docker-compose
docker-compose up -d

# 3. Проверьте статус
docker-compose logs -f
curl http://localhost:8000/health
```

### Docker Run (без Compose)

<details>
<summary>🔹 Использование переменных окружения</summary>

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
<summary>🔹 Использование файла с учётными данными</summary>

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
<summary>🔹 Использование файла .env</summary>

```bash
docker run -d -p 8000:8000 --env-file .env --name kiro-gateway ghcr.io/jwadow/kiro-gateway:latest
```

</details>

### Конфигурация Docker Compose

Отредактируйте `docker-compose.yml` и раскомментируйте монтирования томов для вашей ОС:

```yaml
volumes:
  # Учётные данные Kiro IDE (выберите вашу ОС)
  - ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro              # Linux/macOS
  # - ${USERPROFILE}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro  # Windows
  
  # База данных kiro-cli (выберите вашу ОС)
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Linux/macOS
  # - ${USERPROFILE}/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Windows
  
  # Логи отладки (опционально)
  - ./debug_logs:/app/debug_logs
```

### Команды управления

```bash
docker-compose logs -f      # Просмотр логов
docker-compose restart      # Перезапуск
docker-compose down         # Остановка
docker-compose pull && docker-compose up -d  # Обновление
```

<details>
<summary>🔧 Сборка из исходников</summary>

```bash
docker build -t kiro-gateway .
docker run -d -p 8000:8000 --env-file .env kiro-gateway
```

</details>

---

## 🌐 Поддержка VPN/Proxy

**Для пользователей в Китае, корпоративных сетях или регионах с проблемами подключения к сервисам AWS.**

Шлюз поддерживает маршрутизацию всех запросов Kiro API через VPN или прокси-сервер. Это необходимо, если у вас возникают проблемы с подключением к конечным точкам AWS или вам нужно использовать корпоративный прокси.

### Конфигурация

Добавьте в ваш файл `.env`:

```env
# HTTP прокси
VPN_PROXY_URL=http://127.0.0.1:7890

# SOCKS5 прокси
VPN_PROXY_URL=socks5://127.0.0.1:1080

# С аутентификацией (корпоративные прокси)
VPN_PROXY_URL=http://username:password@proxy.company.com:8080

# Без протокола (по умолчанию http://)
VPN_PROXY_URL=192.168.1.100:8080
```

### Поддерживаемые протоколы

- ✅ **HTTP** — Стандартный протокол прокси
- ✅ **HTTPS** — Безопасные соединения прокси
- ✅ **SOCKS5** — Продвинутый протокол прокси (распространён в ПО VPN)
- ✅ **Аутентификация** — Имя пользователя/пароль встроены в URL

### Когда это нужно

| Ситуация | Решение |
|----------|---------|
| Таймауты подключения к AWS | Используйте VPN/прокси для маршрутизации трафика |
| Ограничения корпоративной сети | Настройте прокси вашей компании |
| Проблемы с региональным подключением | Используйте VPN-сервис с поддержкой прокси |
| Требования конфиденциальности | Маршрутизируйте через собственный прокси-сервер |

### Популярное ПО VPN с поддержкой прокси

Большинство VPN-клиентов предоставляют локальный прокси-сервер:
- **Sing-box** — Современный VPN-клиент с поддержкой HTTP/SOCKS5 прокси
- **Clash** — Обычно работает на `http://127.0.0.1:7890`
- **V2Ray** — Настраиваемый SOCKS5/HTTP прокси
- **Shadowsocks** — Поддержка SOCKS5 прокси
- **Корпоративный VPN** — Уточните параметры прокси у вашего IT-отдела

Оставьте `VPN_PROXY_URL` пустым (по умолчанию), если вам не нужна поддержка прокси.

---

## 📡 Справочник API

### Эндпоинты

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/` | GET | Проверка работоспособности |
| `/health` | GET | Детальная проверка работоспособности |
| `/v1/models` | GET | Список доступных моделей |
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/messages` | POST | Anthropic Messages API |

---

## 💡 Примеры использования

### OpenAI API

<details>
<summary>🔹 Простой cURL-запрос</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Привет!"}],
    "stream": true
  }'
```

> **Примечание:** Замените `my-super-secret-password-123` на `PROXY_API_KEY`, который вы указали в файле `.env`.

</details>

<details>
<summary>🔹 Запрос со стримингом</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "system", "content": "Ты полезный ассистент."},
      {"role": "user", "content": "Сколько будет 2+2?"}
    ],
    "stream": true
  }'
```

</details>

<details>
<summary>🛠️ С вызовом инструментов</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Какая погода в Лондоне?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Получить погоду для местоположения",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "Название города"}
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
    api_key="my-super-secret-password-123"  # Ваш PROXY_API_KEY из .env
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[
        {"role": "system", "content": "Ты полезный ассистент."},
        {"role": "user", "content": "Привет!"}
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
    api_key="my-super-secret-password-123",  # Ваш PROXY_API_KEY из .env
    model="claude-sonnet-4-5"
)

response = llm.invoke("Привет, как дела?")
print(response.content)
```

</details>

### Anthropic API

<details>
<summary>🔹 Простой cURL-запрос</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Привет!"}]
  }'
```

> **Примечание:** Anthropic API использует заголовок `x-api-key` вместо `Authorization: Bearer`. Оба варианта поддерживаются.

</details>

<details>
<summary>🔹 С системным промптом</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "system": "Ты полезный ассистент.",
    "messages": [{"role": "user", "content": "Привет!"}]
  }'
```

> **Примечание:** В Anthropic API `system` — это отдельное поле, а не сообщение.

</details>

<details>
<summary>📡 Стриминг</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "Привет!"}]
  }'
```

</details>

<details>
<summary>🐍 Python Anthropic SDK</summary>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="my-super-secret-password-123",  # Ваш PROXY_API_KEY из .env
    base_url="http://localhost:8000"
)

# Без стриминга
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Привет!"}]
)
print(response.content[0].text)

# Со стримингом
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Привет!"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

</details>

---

## 🔧 Отладка

Логирование отладки **отключено по умолчанию**. Чтобы включить, добавьте в ваш `.env`:

```env
# Режим логирования отладки:
# - off: отключено (по умолчанию)
# - errors: сохранять логи только для неудачных запросов (4xx, 5xx) - рекомендуется для устранения неполадок
# - all: сохранять логи для каждого запроса (перезаписывается при каждом запросе)
DEBUG_MODE=errors
```

### Режимы отладки

| Режим | Описание | Случай использования |
|-------|----------|---------------------|
| `off` | Отключено (по умолчанию) | Продакшен |
| `errors` | Сохранять логи только для неудачных запросов (4xx, 5xx) | **Рекомендуется для устранения неполадок** |
| `all` | Сохранять логи для каждого запроса | Разработка/отладка |

### Файлы отладки

При включении запросы логируются в папку `debug_logs/`:

| Файл | Описание |
|------|----------|
| `request_body.json` | Входящий запрос от клиента (формат OpenAI) |
| `kiro_request_body.json` | Запрос, отправленный в Kiro API |
| `response_stream_raw.txt` | Сырой поток от Kiro |
| `response_stream_modified.txt` | Преобразованный поток (формат OpenAI) |
| `app_logs.txt` | Логи приложения для запроса |
| `error_info.json` | Детали ошибки (только при ошибках) |

---

## 📜 Лицензия

Этот проект лицензирован под **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Это означает:
- ✅ Вы можете использовать, модифицировать и распространять это программное обеспечение
- ✅ Вы можете использовать его в коммерческих целях
- ⚠️ **Вы должны раскрыть исходный код** при распространении программного обеспечения
- ⚠️ **Сетевое использование является распространением** — если вы запускаете модифицированную версию на сервере и позволяете другим взаимодействовать с ней, вы должны сделать исходный код доступным для них
- ⚠️ Модификации должны быть выпущены под той же лицензией

Полный текст лицензии см. в файле [LICENSE](../../LICENSE).

### Почему AGPL-3.0?

AGPL-3.0 гарантирует, что улучшения этого программного обеспечения принесут пользу всему сообществу. Если вы модифицируете этот шлюз и развёртываете его как сервис, вы должны поделиться своими улучшениями с вашими пользователями.

### Лицензионное соглашение участника (CLA)

Отправляя вклад в этот проект, вы соглашаетесь с условиями нашего [Лицензионного соглашения участника (CLA)](../../CLA.md). Это гарантирует, что:
- Вы имеете право отправить вклад
- Вы предоставляете мейнтейнеру права на использование и перелицензирование вашего вклада
- Проект остаётся юридически защищённым

---

## 💖 Поддержать проект

<div align="center">

<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Smilies/Smiling%20Face%20with%20Hearts.png" alt="Love" width="80" />

**Если этот проект сэкономил вам время или деньги, рассмотрите возможность его поддержки!**

Каждый вклад помогает поддерживать жизнь и развитие этого проекта

<br>

### 🤑 Пожертвовать

[**☕ Разовая поддержка**](https://app.lava.top/products/b4e34d12-3b6b-49b7-be50-50b6a20ed262/f3ea941f-de73-4ad1-bbb6-f82042ef8132)

<br>

### 🪙 Или отправьте криптовалюту

| Валюта | Сеть | Адрес |
|:------:|:----:|:------|
| **USDT** | TRC20 | `TSVtgRc9pkC1UgcbVeijBHjFmpkYHDRu26` |
| **BTC** | Bitcoin | `12GZqxqpcBsqJ4Vf1YreLqwoMGvzBPgJq6` |
| **ETH** | Ethereum | `0xc86eab3bba3bbaf4eb5b5fff8586f1460f1fd395` |
| **SOL** | Solana | `9amykF7KibZmdaw66a1oqYJyi75fRqgdsqnG66AK3jvh` |
| **TON** | TON | `UQBVh8T1H3GI7gd7b-_PPNnxHYYxptrcCVf3qQk5v41h3QTM` |

</div>

---

## ⚠️ Отказ от ответственности

Этот проект не связан с Amazon Web Services (AWS), Anthropic или Kiro IDE, не одобрен и не спонсируется ими. Используйте на свой страх и риск и в соответствии с условиями использования базовых API.

---

<div align="center">

**[⬆ Вернуться наверх](#-kiro-gateway)**

</div>
