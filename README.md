# Kiro Proxy

Local proxy gateway for Kiro API, giving you free Claude models via an OpenAI/Anthropic-compatible API.

Based on [jwadow/kiro-gateway](https://github.com/jwadow/kiro-gateway).

### Changes from upstream

- Makefile for quick start (`make up`, `make python-up`, etc.)
- Corporate VPN support: SSL verification bypass (`start_no_ssl_verify.py`)
- Simplified Docker Compose setup that reads `.env` directly
- Client setup guides for OpenCode and VS Code — see [CLIENTS.md](CLIENTS.md)

## Prerequisites

- Signed in to `kiro-cli` (`kiro-cli login`)
- Python 3.10+ (for the Python method) or Docker (for the Docker method)

## Getting your credentials

### PROXY_API_KEY

This is a password you make up yourself. It protects your local proxy so only you can use it. Pick any string.

### PROFILE_ARN

Your AWS CodeWhisperer profile ARN. Required for corporate SSO accounts.

Run:

```bash
kiro-cli whoami
```

The output will show something like:

```
Profile:
profile-UVG4KVWQCQN3
arn:aws:codewhisperer:us-east-1:562791833499:profile/UVG4KVWQCQN3
```

The `arn:aws:codewhisperer:...` line is your `PROFILE_ARN`.

### KIRO_API_REGION

The AWS region where the Kiro API is reachable from your network. On corporate VPN, some regions may not resolve via DNS.

Test which regions resolve:

```bash
nslookup runtime.us-east-1.kiro.dev
nslookup runtime.eu-central-1.kiro.dev
nslookup runtime.eu-west-1.kiro.dev
```

Use whichever resolves. `us-east-1` works for most corporate networks.

### KIRO_CREDS_FILE

Path to your Kiro authentication token file. After logging in with `kiro-cli login`, this is at:

```
~/.aws/sso/cache/kiro-auth-token-cli.json
```

## Setup

Create `.env` in the project root:

```
PROXY_API_KEY=pick-any-secret-string
```

---

## Option A: Python (recommended for corporate VPN)

Runs natively on your machine. No Docker DNS issues, uses your host DNS directly.

### 1. Install dependencies

```bash
make python-install
```

### 2. Configure

Edit `python/kiro-gateway/.env`:

```bash
PROXY_API_KEY=pick-any-secret-string
KIRO_CREDS_FILE=~/.aws/sso/cache/kiro-auth-token-cli.json
KIRO_API_REGION=us-east-1
PROFILE_ARN=arn:aws:codewhisperer:us-east-1:YOUR_ACCOUNT:profile/YOUR_PROFILE
FAKE_REASONING=false
WEB_SEARCH_ENABLED=false
TRUNCATION_RECOVERY=false
```

### 3. Start

```bash
make python-up       # foreground (see logs directly)
make python-up-bg    # background (logs go to /tmp/kiro-gateway.log)
```

### 4. Stop

```bash
make python-down
```

### Corporate VPN / SSL issues

The `start_no_ssl_verify.py` wrapper disables SSL certificate verification. This is needed when your corporate VPN does TLS inspection (MITM) and Python's httpx rejects the injected certificate.

If you're NOT on a corporate VPN with TLS inspection, you can run `python main.py` directly instead of using the wrapper.

---

## Option B: Docker

Works out of the box on networks without DNS/SSL restrictions. On corporate VPN, you need `extra_hosts` entries because Docker containers can't resolve the Kiro hostnames.

### 1. Configure

The Docker config is in `docker/docker-compose.yml`. The env vars are passed directly in the compose file. Edit the `PROFILE_ARN` value there.

### 2. Update extra_hosts IPs (corporate VPN only)

The `extra_hosts` section hardcodes IP addresses for Kiro endpoints. These IPs may rotate over time. To update them:

```bash
python3 -c "import socket; print(socket.getaddrinfo('runtime.us-east-1.kiro.dev', 443)[0][4][0])"
python3 -c "import socket; print(socket.getaddrinfo('oidc.eu-west-1.amazonaws.com', 443)[0][4][0])"
```

Update the IPs in `docker/docker-compose.yml` under `extra_hosts`.

### 3. Start

```bash
make up
```

### 4. Stop

```bash
make down
```

---

## Verify it works

```bash
make health        # should return {"status": "healthy", ...}
make test-prompt   # should return a chat completion response
```

---

## Connecting clients

See [CLIENTS.md](CLIENTS.md) for setup instructions for OpenCode and VS Code.

---

## Make commands

| Command             | What it does                       |
|---------------------|------------------------------------|
| `make up`           | Start Docker gateway               |
| `make down`         | Stop Docker gateway                |
| `make restart`      | Restart Docker gateway             |
| `make logs`         | Tail Docker container logs         |
| `make status`       | Show container status              |
| `make pull`         | Pull latest image and restart      |
| `make python-install` | Install Python dependencies      |
| `make python-up`    | Start Python gateway (foreground)  |
| `make python-up-bg` | Start Python gateway (background)  |
| `make python-down`  | Stop Python gateway                |
| `make python-logs`  | Tail Python gateway logs           |
| `make health`       | Check health endpoint              |
| `make test-prompt`  | Send a test chat completion        |

---

## Troubleshooting

### "Name or service not known" / DNS resolution failed

Your network can't resolve the Kiro endpoint hostname. Check which regions resolve (see KIRO_API_REGION section above) and use one that works.

For Docker, update the `extra_hosts` IPs in `docker/docker-compose.yml`.

### "profileArn is required for this request"

You're on a corporate SSO account. Get your profile ARN with `kiro-cli whoami` and add it to your config.

### SSL certificate errors (Python)

Your corporate VPN does TLS inspection. Use `start_no_ssl_verify.py` (the default in this setup) which disables SSL verification for outbound requests.

### Token expired

Re-login with `kiro-cli login`. The gateway auto-refreshes tokens, but if the refresh token itself expires you need to re-authenticate.
