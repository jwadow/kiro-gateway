<div align="center">

# 👻 Kiro Gateway

**Gateway proxy para Kiro API (Amazon Q Developer / AWS CodeWhisperer)**

[🇬🇧 English](../../README.md) • [🇷🇺 Русский](../ru/README.md) • [🇨🇳 中文](../zh/README.md) • [🇪🇸 Español](../es/README.md) • [🇮🇩 Indonesia](../id/README.md) • [🇯🇵 日本語](../ja/README.md) • [🇰🇷 한국어](../ko/README.md)

Feito com ❤️ por [@Jwadow](https://github.com/jwadow)

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Sponsor](https://img.shields.io/badge/💖_Sponsor-Apoie_o_Desenvolvimento-ff69b4)](#-apoie-o-projeto)

*Use modelos Claude do Kiro com Claude Code, OpenCode, Codex app, Cursor, Cline, Roo Code, Kilo Code, Obsidian, OpenAI SDK, LangChain, Continue e outras ferramentas compatíveis com OpenAI ou Anthropic*

[Modelos](#-modelos-suportados) • [Recursos](#-recursos) • [Início Rápido](#-início-rápido) • [Configuração](#%EF%B8%8F-configuração) • [💖 Apoiar](#-apoie-o-projeto)

</div>

---

## 🤖 Modelos Disponíveis

> ⚠️ **Importante:** A disponibilidade de modelos depende do seu plano Kiro (gratuito/pago). O gateway fornece acesso aos modelos disponíveis no seu IDE ou CLI com base na sua assinatura. A lista abaixo mostra os modelos comumente disponíveis no **plano gratuito**.

> 🔒 **Claude Opus 4.5** foi removido do plano gratuito em 17 de janeiro de 2026. Pode estar disponível em planos pagos — verifique a lista de modelos no seu IDE/CLI.

🚀 **Claude Sonnet 4.5** — Desempenho equilibrado. Ótimo para programação, escrita e tarefas de uso geral.

⚡ **Claude Haiku 4.5** — Velocidade relâmpago. Perfeito para respostas rápidas, tarefas simples e chat.

📦 **Claude Sonnet 4** — Geração anterior. Ainda poderoso e confiável para a maioria dos casos de uso.

📦 **Claude 3.7 Sonnet** — Modelo legado. Disponível para compatibilidade retroativa.

🐋 **DeepSeek-V3.2** — Modelo MoE aberto (685B parâmetros, 37B ativos). Desempenho equilibrado para programação, raciocínio e tarefas gerais.

🧩 **MiniMax M2.1** — Modelo MoE aberto (230B parâmetros, 10B ativos). Ótimo para tarefas complexas, planejamento e fluxos de trabalho multietapas.

🤖 **Qwen3-Coder-Next** — Modelo MoE aberto (80B parâmetros, 3B ativos). Focado em programação. Excelente para desenvolvimento e projetos grandes.

> 💡 **Resolução Inteligente de Modelos:** Use qualquer formato de nome de modelo — `claude-sonnet-4-5`, `claude-sonnet-4.5`, ou até nomes versionados como `claude-sonnet-4-5-20250929`. O gateway normaliza automaticamente.

---

## ✨ Recursos

| Recurso | Descrição |
|---------|-----------|
| 🔌 **API compatível com OpenAI** | Funciona com qualquer ferramenta compatível com OpenAI |
| 🔌 **API compatível com Anthropic** | Endpoint nativo `/v1/messages` |
| 🌐 **Suporte a VPN/Proxy** | Proxy HTTP/SOCKS5 para redes restritas |
| 🧠 **Pensamento Estendido** | Raciocínio é exclusivo do nosso projeto |
| 👁️ **Suporte a Visão** | Envie imagens para o modelo |
| 🛠️ **Chamada de Ferramentas** | Suporta chamada de funções |
| 💬 **Histórico completo de mensagens** | Passa o contexto completo da conversa |
| 📡 **Streaming** | Suporte completo a streaming SSE |
| 🔄 **Lógica de Retry** | Retentativas automáticas em erros (403, 429, 5xx) |
| 📋 **Lista estendida de modelos** | Incluindo modelos versionados |
| 🔐 **Gerenciamento inteligente de tokens** | Atualização automática antes da expiração |

---

## 🚀 Início Rápido

**Escolha seu método de implantação:**
- 🐍 **Python Nativo** - Controle total, depuração fácil
- 🐳 **Docker** - Ambiente isolado, implantação fácil → [ir para Docker](#-docker-deployment)

### Pré-requisitos

- Python 3.10+
- Um dos seguintes:
  - [Kiro IDE](https://kiro.dev/) com conta logada, OU
  - [Kiro CLI](https://kiro.dev/cli/) com AWS SSO (AWS IAM Identity Center, OIDC) - Builder ID gratuito ou conta corporativa

### Instalação

```bash
# Clone o repositório (requer Git)
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway

# Ou baixe o ZIP: Code → Download ZIP → extraia → abra a pasta kiro-gateway

# Instale as dependências
pip install -r requirements.txt

# Configure (veja a seção Configuração)
cp .env.example .env
# Copie e edite o .env com suas credenciais

# Inicie o servidor
python main.py

# Ou com porta personalizada (se 8000 estiver ocupada)
python main.py --port 9000
```

O servidor estará disponível em `http://localhost:8000`

---

## ⚙️ Configuração

### Opção 1: Arquivo JSON de Credenciais (Kiro IDE / Enterprise)

Especifique o caminho para o arquivo de credenciais:

Funciona com:
- **Kiro IDE** (padrão) - para contas pessoais
- **Enterprise** - para contas corporativas com SSO

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/kiro-auth-token.json"

# Senha para proteger SEU servidor proxy (crie qualquer string segura)
# Você usará isso como api_key ao conectar ao seu gateway
PROXY_API_KEY="my-super-secret-password-123"
```

<details>
<summary>📄 Formato do arquivo JSON</summary>

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

> **Nota:** Se você tiver dois arquivos JSON em `~/.aws/sso/cache/` (por exemplo, `kiro-auth-token.json` e um arquivo com nome hash), use `kiro-auth-token.json` em `KIRO_CREDS_FILE`. O gateway carregará automaticamente o outro arquivo.

</details>

### Opção 2: Variáveis de Ambiente (arquivo .env)

Crie um arquivo `.env` na raiz do projeto:

```env
# Obrigatório
REFRESH_TOKEN="seu_kiro_refresh_token"

# Senha para proteger SEU servidor proxy (crie qualquer string segura)
PROXY_API_KEY="my-super-secret-password-123"

# Opcional
PROFILE_ARN="arn:aws:codewhisperer:us-east-1:..."
KIRO_REGION="us-east-1"
```

### Opção 3: Credenciais AWS SSO (kiro-cli / Enterprise)

Se você usa `kiro-cli` ou Kiro IDE com AWS SSO (AWS IAM Identity Center), o gateway detectará e usará automaticamente a autenticação apropriada.

Funciona tanto com contas Builder ID gratuitas quanto com contas corporativas.

```env
KIRO_CREDS_FILE="~/.aws/sso/cache/your-sso-cache-file.json"

# Senha para proteger SEU servidor proxy
PROXY_API_KEY="my-super-secret-password-123"

# Nota: PROFILE_ARN NÃO é necessário para AWS SSO (Builder ID e contas corporativas)
# O gateway funcionará sem ele
```

<details>
<summary>📄 Formato do arquivo JSON AWS SSO</summary>

Arquivos de credenciais AWS SSO (de `~/.aws/sso/cache/`) contêm:

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

**Nota:** Usuários AWS SSO (Builder ID e contas corporativas) NÃO precisam de `profileArn`. O gateway funcionará sem ele (se especificado, será ignorado).

</details>

<details>
<summary>🔍 Como funciona</summary>

O gateway detecta automaticamente o tipo de autenticação com base no arquivo de credenciais:

- **Kiro Desktop Auth** (padrão): Usado quando `clientId` e `clientSecret` NÃO estão presentes
  - Endpoint: `https://prod.{region}.auth.desktop.kiro.dev/refreshToken`
  
- **AWS SSO (OIDC)**: Usado quando `clientId` e `clientSecret` estão presentes
  - Endpoint: `https://oidc.{region}.amazonaws.com/token`

Nenhuma configuração adicional necessária — apenas aponte para seu arquivo de credenciais!

</details>

### Opção 4: Banco de dados SQLite do kiro-cli

Se você usa `kiro-cli` e prefere usar seu banco de dados SQLite diretamente:

```env
KIRO_CLI_DB_FILE="~/.local/share/kiro-cli/data.sqlite3"

# Senha para proteger SEU servidor proxy
PROXY_API_KEY="my-super-secret-password-123"

# Nota: PROFILE_ARN NÃO é necessário para AWS SSO (Builder ID e contas corporativas)
# O gateway funcionará sem ele
```

<details>
<summary>📄 Localizações do banco de dados</summary>

| Ferramenta CLI | Caminho do Banco de Dados |
|----------------|---------------------------|
| kiro-cli | `~/.local/share/kiro-cli/data.sqlite3` |
| amazon-q-developer-cli | `~/.local/share/amazon-q/data.sqlite3` |

O gateway lê credenciais da tabela `auth_kv` que armazena:
- `kirocli:odic:token` ou `codewhisperer:odic:token` — token de acesso, token de atualização, expiração
- `kirocli:odic:device-registration` ou `codewhisperer:odic:device-registration` — ID do cliente e segredo

Ambos os formatos de chave são suportados para compatibilidade com diferentes versões do kiro-cli.

</details>

### Obtendo Credenciais

**Para usuários do Kiro IDE:**
- Faça login no Kiro IDE e use a Opção 1 acima (arquivo JSON de credenciais)
- O arquivo de credenciais é criado automaticamente após o login

**Para usuários do Kiro CLI:**
- Faça login com `kiro-cli login` e use a Opção 3 ou Opção 4 acima
- Não é necessário extrair tokens manualmente!

<details>
<summary>🔧 Avançado: Extração manual de token</summary>

Se você precisar extrair manualmente o refresh token (por exemplo, para depuração), você pode interceptar o tráfego do Kiro IDE:
- Procure por requisições para: `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`

</details>

---

## 🐳 Docker Deployment

> **Implantação baseada em Docker.** Prefere Python nativo? Veja [Início Rápido](#-início-rápido) acima.

### Início Rápido

```bash
# 1. Clone e configure
git clone https://github.com/Jwadow/kiro-gateway.git
cd kiro-gateway
cp .env.example .env
# Edite .env com suas credenciais

# 2. Execute com docker-compose
docker-compose up -d

# 3. Verifique o status
docker-compose logs -f
curl http://localhost:8000/health
```

### Docker Run (Sem Compose)

<details>
<summary>🔹 Usando Variáveis de Ambiente</summary>

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
<summary>🔹 Usando Arquivo de Credenciais</summary>

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
<summary>🔹 Usando Arquivo .env</summary>

```bash
docker run -d -p 8000:8000 --env-file .env --name kiro-gateway ghcr.io/jwadow/kiro-gateway:latest
```

</details>

### Configuração do Docker Compose

Edite `docker-compose.yml` e descomente os volumes para seu SO:

```yaml
volumes:
  # Credenciais do Kiro IDE (escolha seu SO)
  - ~/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro              # Linux/macOS
  # - ${USERPROFILE}/.aws/sso/cache:/home/kiro/.aws/sso/cache:ro  # Windows
  
  # Banco de dados kiro-cli (escolha seu SO)
  - ~/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Linux/macOS
  # - ${USERPROFILE}/.local/share/kiro-cli:/home/kiro/.local/share/kiro-cli  # Windows
  
  # Logs de depuração (opcional)
  - ./debug_logs:/app/debug_logs
```

### Comandos de Gerenciamento

```bash
docker-compose logs -f      # Ver logs
docker-compose restart      # Reiniciar
docker-compose down         # Parar
docker-compose pull && docker-compose up -d  # Atualizar
```

<details>
<summary>🔧 Compilar do Código-Fonte</summary>

```bash
docker build -t kiro-gateway .
docker run -d -p 8000:8000 --env-file .env kiro-gateway
```

</details>

---

## 🌐 Suporte a VPN/Proxy

**Para usuários na China, redes corporativas ou regiões com problemas de conectividade com serviços AWS.**

O gateway suporta rotear todas as solicitações da Kiro API através de um servidor VPN ou proxy. Isso é essencial se você enfrentar problemas de conexão com endpoints AWS ou precisar usar um proxy corporativo.

### Configuração

Adicione ao seu arquivo `.env`:

```env
# Proxy HTTP
VPN_PROXY_URL=http://127.0.0.1:7890

# Proxy SOCKS5
VPN_PROXY_URL=socks5://127.0.0.1:1080

# Com autenticação (proxies corporativos)
VPN_PROXY_URL=http://username:password@proxy.company.com:8080

# Sem protocolo (padrão para http://)
VPN_PROXY_URL=192.168.1.100:8080
```

### Protocolos Suportados

- ✅ **HTTP** — Protocolo proxy padrão
- ✅ **HTTPS** — Conexões proxy seguras
- ✅ **SOCKS5** — Protocolo proxy avançado (comum em software VPN)
- ✅ **Autenticação** — Nome de usuário/senha incorporados na URL

### Quando Você Precisa Disso

| Situação | Solução |
|----------|---------|
| Timeouts de conexão com AWS | Use VPN/proxy para rotear tráfego |
| Restrições de rede corporativa | Configure o proxy da sua empresa |
| Problemas de conectividade regional | Use um serviço VPN com suporte a proxy |
| Requisitos de privacidade | Roteie através do seu próprio servidor proxy |

### Software VPN Popular com Suporte a Proxy

A maioria dos clientes VPN fornece um servidor proxy local:
- **Sing-box** — Cliente VPN moderno com suporte a proxy HTTP/SOCKS5
- **Clash** — Geralmente executado em `http://127.0.0.1:7890`
- **V2Ray** — Proxy SOCKS5/HTTP configurável
- **Shadowsocks** — Suporte a proxy SOCKS5
- **VPN Corporativo** — Consulte seu departamento de TI para configurações de proxy

Deixe `VPN_PROXY_URL` vazio (padrão) se você não precisar de suporte a proxy.

---

## 📡 Referência da API

### Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/` | GET | Verificação de saúde |
| `/health` | GET | Verificação de saúde detalhada |
| `/v1/models` | GET | Lista modelos disponíveis |
| `/v1/chat/completions` | POST | OpenAI Chat Completions API |
| `/v1/messages` | POST | Anthropic Messages API |

---

## 💡 Exemplos de Uso

### OpenAI API

<details>
<summary>🔹 Requisição cURL Simples</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Olá!"}],
    "stream": true
  }'
```

> **Nota:** Substitua `my-super-secret-password-123` pelo `PROXY_API_KEY` que você definiu no arquivo `.env`.

</details>

<details>
<summary>🔹 Requisição com Streaming</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [
      {"role": "system", "content": "Você é um assistente útil."},
      {"role": "user", "content": "Quanto é 2+2?"}
    ],
    "stream": true
  }'
```

</details>

<details>
<summary>🛠️ Com Chamada de Ferramentas</summary>

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer my-super-secret-password-123" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "messages": [{"role": "user", "content": "Como está o tempo em Londres?"}],
    "tools": [{
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Obter o tempo para uma localização",
        "parameters": {
          "type": "object",
          "properties": {
            "location": {"type": "string", "description": "Nome da cidade"}
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
    api_key="my-super-secret-password-123"  # Seu PROXY_API_KEY do .env
)

response = client.chat.completions.create(
    model="claude-sonnet-4-5",
    messages=[
        {"role": "system", "content": "Você é um assistente útil."},
        {"role": "user", "content": "Olá!"}
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
    api_key="my-super-secret-password-123",  # Seu PROXY_API_KEY do .env
    model="claude-sonnet-4-5"
)

response = llm.invoke("Olá, como você está?")
print(response.content)
```

</details>

### Anthropic API

<details>
<summary>🔹 Requisição cURL Simples</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "messages": [{"role": "user", "content": "Olá!"}]
  }'
```

> **Nota:** A API Anthropic usa o header `x-api-key` em vez de `Authorization: Bearer`. Ambos são suportados.

</details>

<details>
<summary>🔹 Com Prompt de Sistema</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "system": "Você é um assistente útil.",
    "messages": [{"role": "user", "content": "Olá!"}]
  }'
```

> **Nota:** Na API Anthropic, `system` é um campo separado, não uma mensagem.

</details>

<details>
<summary>📡 Streaming</summary>

```bash
curl http://localhost:8000/v1/messages \
  -H "x-api-key: my-super-secret-password-123" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-sonnet-4-5",
    "max_tokens": 1024,
    "stream": true,
    "messages": [{"role": "user", "content": "Olá!"}]
  }'
```

</details>

<details>
<summary>🐍 Python Anthropic SDK</summary>

```python
import anthropic

client = anthropic.Anthropic(
    api_key="my-super-secret-password-123",  # Seu PROXY_API_KEY do .env
    base_url="http://localhost:8000"
)

# Sem streaming
response = client.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Olá!"}]
)
print(response.content[0].text)

# Com streaming
with client.messages.stream(
    model="claude-sonnet-4-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Olá!"}]
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

</details>

---

## 🔧 Depuração

O log de depuração está **desabilitado por padrão**. Para habilitar, adicione ao seu `.env`:

```env
# Modo de log de depuração:
# - off: desabilitado (padrão)
# - errors: salvar logs apenas para requisições com falha (4xx, 5xx) - recomendado para solução de problemas
# - all: salvar logs para cada requisição (sobrescreve a cada requisição)
DEBUG_MODE=errors
```

### Modos de Depuração

| Modo | Descrição | Caso de Uso |
|------|-----------|-------------|
| `off` | Desabilitado (padrão) | Produção |
| `errors` | Salvar logs apenas para requisições com falha (4xx, 5xx) | **Recomendado para solução de problemas** |
| `all` | Salvar logs para cada requisição | Desenvolvimento/depuração |

### Arquivos de Depuração

Quando habilitado, as requisições são registradas na pasta `debug_logs/`:

| Arquivo | Descrição |
|---------|-----------|
| `request_body.json` | Requisição recebida do cliente (formato OpenAI) |
| `kiro_request_body.json` | Requisição enviada para a API Kiro |
| `response_stream_raw.txt` | Stream bruto do Kiro |
| `response_stream_modified.txt` | Stream transformado (formato OpenAI) |
| `app_logs.txt` | Logs da aplicação para a requisição |
| `error_info.json` | Detalhes do erro (apenas em erros) |

---

## 📜 Licença

Este projeto está licenciado sob a **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Isso significa:
- ✅ Você pode usar, modificar e distribuir este software
- ✅ Você pode usá-lo para fins comerciais
- ⚠️ **Você deve divulgar o código-fonte** quando distribuir o software
- ⚠️ **Uso em rede é distribuição** — se você executar uma versão modificada em um servidor e permitir que outros interajam com ela, você deve disponibilizar o código-fonte para eles
- ⚠️ Modificações devem ser lançadas sob a mesma licença

Veja o arquivo [LICENSE](../../LICENSE) para o texto completo da licença.

### Por que AGPL-3.0?

AGPL-3.0 garante que melhorias neste software beneficiem toda a comunidade. Se você modificar este gateway e implantá-lo como um serviço, você deve compartilhar suas melhorias com seus usuários.

### Acordo de Licença de Contribuidor (CLA)

Ao enviar uma contribuição para este projeto, você concorda com os termos do nosso [Acordo de Licença de Contribuidor (CLA)](../../CLA.md). Isso garante que:
- Você tem o direito de enviar a contribuição
- Você concede ao mantenedor direitos de usar e relicenciar sua contribuição
- O projeto permanece legalmente protegido

---

## 💖 Apoie o Projeto

<div align="center">

<img src="https://raw.githubusercontent.com/Tarikul-Islam-Anik/Animated-Fluent-Emojis/master/Emojis/Smilies/Smiling%20Face%20with%20Hearts.png" alt="Love" width="80" />

**Se este projeto economizou seu tempo ou dinheiro, considere apoiá-lo!**

Cada contribuição ajuda a manter este projeto vivo e crescendo

<br>

### 🤑 Doar

[**☕ Doação Única**](https://app.lava.top/jwadow?tabId=donate) &nbsp;•&nbsp; [**💎 Apoio Mensal**](https://app.lava.top/jwadow?tabId=subscriptions)

<br>

### 🪙 Ou envie criptomoedas

| Moeda | Rede | Endereço |
|:-----:|:----:|:---------|
| **USDT** | TRC20 | `TSVtgRc9pkC1UgcbVeijBHjFmpkYHDRu26` |
| **BTC** | Bitcoin | `12GZqxqpcBsqJ4Vf1YreLqwoMGvzBPgJq6` |
| **ETH** | Ethereum | `0xc86eab3bba3bbaf4eb5b5fff8586f1460f1fd395` |
| **SOL** | Solana | `9amykF7KibZmdaw66a1oqYJyi75fRqgdsqnG66AK3jvh` |
| **TON** | TON | `UQBVh8T1H3GI7gd7b-_PPNnxHYYxptrcCVf3qQk5v41h3QTM` |

</div>

---

## ⚠️ Aviso Legal

Este projeto não é afiliado, endossado ou patrocinado pela Amazon Web Services (AWS), Anthropic ou Kiro IDE. Use por sua conta e risco e em conformidade com os termos de serviço das APIs subjacentes.

---

<div align="center">

**[⬆ Voltar ao Topo](#-kiro-gateway)**

</div>
