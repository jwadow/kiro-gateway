# Debugging Kiro Auth Flow with mitmproxy

This guide explains how to intercept and analyze the Kiro API authentication flow using mitmproxy. Useful for reverse engineering new auth methods or debugging connectivity issues.

## Prerequisites

- [mitmproxy](https://mitmproxy.org/) installed locally: `brew install mitmproxy`
- Docker installed
- A Kiro API key or other credentials

## Setup

### 1. Start mitmproxy locally

```bash
# Start mitmdump with full request/response logging
mitmdump -p 8080 --listen-host 0.0.0.0 --set block_global=false --set flow_detail=3 > /tmp/mitmdump-verbose.log 2>&1 &
```

Options:
- `-p 8080` — listen port
- `--set flow_detail=3` — log full headers and bodies
- `--set block_global=false` — allow non-local connections

For interactive web UI instead:
```bash
mitmweb -p 8080 --web-host 0.0.0.0 --set block_global=false
# Web UI at http://localhost:8081
```

### 2. Build the kiro-cli Docker image

Create `Dockerfile_kiro-cli`:

```dockerfile
FROM alpine:latest

ENV PATH="/home/kiro/.local/bin:$PATH"

RUN apk add bash curl
RUN adduser -D kiro

COPY mitmproxy-ca-cert.pem .
RUN cat mitmproxy-ca-cert.pem >> /etc/ssl/certs/ca-certificates.crt

USER kiro

RUN curl -fsSL https://cli.kiro.dev/install | bash

# Proxy only at runtime (not during build)
ENV HTTP_PROXY=http://host.docker.internal:8080
ENV HTTPS_PROXY=http://host.docker.internal:8080
```

Copy the mitmproxy CA cert to the project directory:
```bash
cp ~/.mitmproxy/mitmproxy-ca-cert.pem ./mitmproxy-ca-cert.pem
```

Build:
```bash
docker build -f Dockerfile_kiro-cli -t kiro:cli .
```

### 3. Run kiro-cli through the proxy

```bash
docker run --rm \
  -e KIRO_API_KEY=ksk_your_api_key_here \
  -e HTTP_PROXY=http://host.docker.internal:8080 \
  -e HTTPS_PROXY=http://host.docker.internal:8080 \
  -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
  -e AWS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
  kiro:cli kiro-cli chat --no-interactive "say hello"
```

### 4. Analyze the captured traffic

```bash
cat /tmp/mitmdump-verbose.log
```

## API Key Auth Flow (Captured)

The API key auth flow is straightforward — no token exchange needed:

### Headers

All Kiro API requests with API key auth use:
```
Authorization: Bearer ksk_<your_api_key>
tokentype: API_KEY
Content-Type: application/x-amz-json-1.0
```

### Request Sequence

1. **GetProfile** — Determines account region
   ```
   POST https://management.{region}.kiro.dev/
   x-amz-target: AmazonCodeWhispererService.GetProfile
   Body: {}
   ```
   - Tries `us-east-1` first, falls back to `eu-central-1`
   - Response contains profile ARN with correct region

2. **ListAvailableModels** — Gets available models
   ```
   POST https://management.{region}.kiro.dev/?origin=KIRO_CLI
   x-amz-target: AmazonCodeWhispererService.ListAvailableModels
   Body: {"origin":"KIRO_CLI"}
   ```

3. **GenerateAssistantResponse** — Chat completion (streaming)
   ```
   POST https://runtime.{region}.kiro.dev/
   x-amz-target: AmazonCodeWhispererStreamingService.GenerateAssistantResponse
   Response: application/vnd.amazon.eventstream
   ```

### Key Findings

- `profileArn` must NOT be included in the GenerateAssistantResponse payload for API key auth
- The `tokentype: API_KEY` header is required on all requests
- No Cognito, no SSO, no token refresh needed
- Cognito calls in the logs are only for anonymous telemetry (unrelated to auth)
- Region is auto-detected from the GetProfile response

## Tips

- Use `--set flow_detail=3` for full body logging (very verbose)
- Use `--set flow_detail=2` for headers only
- Filter traffic: `mitmdump -p 8080 --set flow_detail=3 -k "~d kiro.dev"`
- Save flows for later replay: `mitmdump -p 8080 -w /tmp/flows.mitm`
- Read saved flows: `mitmdump -r /tmp/flows.mitm --set flow_detail=3`

## Troubleshooting

**"invalid peer certificate: BadSignature"**
- The mitmproxy CA cert is not trusted. Ensure `mitmproxy-ca-cert.pem` from `~/.mitmproxy/` is appended to the container's CA bundle.

**"Connection refused" on 172.19.0.1:8080**
- mitmproxy is running in Docker but the container can't reach it. Use `host.docker.internal` instead of gateway IP, or run mitmproxy on the host.

**Proxy env vars blocking Docker build**
- Set `HTTP_PROXY`/`HTTPS_PROXY` after all `RUN` commands in the Dockerfile (runtime only).
