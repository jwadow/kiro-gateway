#!/usr/bin/env python3
"""
HTTP/HTTPS forward proxy on port 60000 — ResilientClient edition.

Option A: transparent proxy — set HTTP_PROXY/HTTPS_PROXY and all outbound
API calls from OpenCode / owl / kiro get automatic retry + rate-limit backoff.

Option B (MCP): run mcp_proxy_server.py alongside this for tool-based control.

Retry logic (mirrors KiroHttpClient from kiro-gateway):
  - 429 → exponential backoff (1s, 2s, 4s, 8s)
  - 5xx → exponential backoff
  - timeout / network error → exponential backoff
  - HTTPS CONNECT → transparent TCP tunnel (no retry needed, TLS end-to-end)

Stats exposed on http://127.0.0.1:60000/_proxy/stats (JSON).
"""

import asyncio
import json
import logging
import os
import sys
import time
from collections import defaultdict
from typing import Optional

import httpx

PROXY_HOST = os.getenv("FORWARD_PROXY_HOST", "127.0.0.1")
PROXY_PORT = int(os.getenv("FORWARD_PROXY_PORT", "60000"))
MAX_RETRIES = int(os.getenv("FORWARD_PROXY_MAX_RETRIES", "4"))
BASE_RETRY_DELAY = float(os.getenv("FORWARD_PROXY_BASE_RETRY_DELAY", "1.0"))
# Chain through an upstream proxy (e.g. mihomo/9router for geo-routing)
# Set via env: UPSTREAM_PROXY=http://127.0.0.1:7890
# Or CLI:      python3 forward_proxy.py --upstream-proxy http://127.0.0.1:7890
UPSTREAM_PROXY: Optional[str] = os.getenv("UPSTREAM_PROXY")

# Parse --upstream-proxy CLI arg
if "--upstream-proxy" in sys.argv:
    idx = sys.argv.index("--upstream-proxy")
    if idx + 1 < len(sys.argv):
        UPSTREAM_PROXY = sys.argv[idx + 1]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("forward_proxy")

# ---------------------------------------------------------------------------
# Stats (read by MCP server via /_proxy/stats)
# ---------------------------------------------------------------------------
_stats: dict = {
    "started": time.time(),
    "requests": 0,
    "retries": 0,
    "errors": 0,
    "status_counts": defaultdict(int),
}


def _record(status: int, retries: int = 0, error: bool = False) -> None:
    _stats["requests"] += 1
    _stats["retries"] += retries
    if error:
        _stats["errors"] += 1
    _stats["status_counts"][str(status)] += 1


# ---------------------------------------------------------------------------
# Shared httpx client
# ---------------------------------------------------------------------------
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        kwargs: dict = dict(
            timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        )
        if UPSTREAM_PROXY:
            kwargs["proxy"] = UPSTREAM_PROXY
            log.info(f"Upstream proxy: {UPSTREAM_PROXY}")
        _client = httpx.AsyncClient(**kwargs)
    return _client


# ---------------------------------------------------------------------------
# ResilientClient retry core (mirrors KiroHttpClient.request_with_retry)
# ---------------------------------------------------------------------------
async def _resilient_request(
    method: str,
    url: str,
    headers: dict,
    body: bytes,
) -> tuple[Optional[httpx.Response], int]:
    """Returns (response, retry_count). response=None means all retries failed."""
    client = _get_client()
    last_response: Optional[httpx.Response] = None
    retries = 0

    for attempt in range(MAX_RETRIES):
        try:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                content=body or None,
            )

            if response.status_code == 429 or (500 <= response.status_code < 600):
                last_response = response
                delay = BASE_RETRY_DELAY * (2 ** attempt)
                log.warning(
                    f"HTTP {response.status_code} ← {url} "
                    f"retry in {delay:.0f}s ({attempt+1}/{MAX_RETRIES})"
                )
                retries += 1
                await asyncio.sleep(delay)
                continue

            return response, retries

        except (httpx.TimeoutException, httpx.RequestError) as e:
            delay = BASE_RETRY_DELAY * (2 ** attempt)
            log.warning(f"{type(e).__name__} ← {url} retry in {delay:.0f}s ({attempt+1}/{MAX_RETRIES})")
            retries += 1
            await asyncio.sleep(delay)

    return last_response, retries  # exhausted — return last known response or None


# ---------------------------------------------------------------------------
# HTTP forwarding
# ---------------------------------------------------------------------------
async def _forward_http(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        raw = await reader.read(65536)
    except Exception:
        writer.close()
        return

    if not raw:
        writer.close()
        return

    # Internal control endpoints
    if raw.startswith(b"GET /_proxy/rotate") or raw.startswith(b"POST /_proxy/rotate"):
        global _client
        if _client and not _client.is_closed:
            asyncio.create_task(_client.aclose())
        _client = None
        log.info("Connection pool flushed (rotate requested)")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK")
        await writer.drain()
        writer.close()
        return

    if raw.startswith(b"GET /_proxy/stats"):
        body = json.dumps({
            **_stats,
            "uptime_s": round(time.time() - _stats["started"], 1),
            "status_counts": dict(_stats["status_counts"]),
            "upstream_proxy": UPSTREAM_PROXY,
        }).encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n"
            + body
        )
        await writer.drain()
        writer.close()
        return

    try:
        header_end = raw.index(b"\r\n\r\n")
        header_bytes = raw[:header_end]
        body = raw[header_end + 4:]
        lines = header_bytes.split(b"\r\n")
        method, url, _ = lines[0].decode().split(" ", 2)

        headers = {}
        for line in lines[1:]:
            if b":" in line:
                k, v = line.split(b":", 1)
                key = k.decode().strip()
                if key.lower() not in ("proxy-connection", "proxy-authorization", "connection", "keep-alive"):
                    headers[key] = v.decode().strip()
    except Exception as e:
        log.warning(f"Parse error: {e}")
        writer.close()
        return

    # Read remaining body
    content_length = int(headers.get("Content-Length", len(body)))
    while len(body) < content_length:
        try:
            chunk = await reader.read(65536)
            if not chunk:
                break
            body += chunk
        except Exception:
            break

    response, retries = await _resilient_request(method, url, headers, body)

    if response is None:
        _record(502, retries, error=True)
        err = b"Bad Gateway: all retries exhausted"
        writer.write(
            b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: "
            + str(len(err)).encode() + b"\r\nConnection: close\r\n\r\n" + err
        )
        await writer.drain()
        writer.close()
        return

    _record(response.status_code, retries)

    resp_headers = b""
    for k, v in response.headers.items():
        if k.lower() not in ("transfer-encoding",):
            resp_headers += f"{k}: {v}\r\n".encode()
    resp_body = response.content
    resp_headers += f"Content-Length: {len(resp_body)}\r\nConnection: close\r\n".encode()

    try:
        writer.write(
            f"HTTP/1.1 {response.status_code} {response.reason_phrase}\r\n".encode()
            + resp_headers + b"\r\n" + resp_body
        )
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


# ---------------------------------------------------------------------------
# CONNECT tunnel (HTTPS — transparent, no TLS interception)
# ---------------------------------------------------------------------------
async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while chunk := await src.read(65536):
            dst.write(chunk)
            await dst.drain()
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def _handle_connect(host: str, port: int, cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
    try:
        rr, rw = await asyncio.open_connection(host, port)
    except Exception as e:
        log.warning(f"CONNECT {host}:{port} failed: {e}")
        cw.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
        await cw.drain()
        cw.close()
        return

    cw.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await cw.drain()
    _record(200)
    await asyncio.gather(_pipe(cr, rw), _pipe(rr, cw), return_exceptions=True)


# ---------------------------------------------------------------------------
# Connection dispatcher
# ---------------------------------------------------------------------------
async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        first_line = await reader.readline()
        if not first_line:
            writer.close()
            return

        parts = first_line.decode(errors="replace").strip().split()
        if len(parts) < 2:
            writer.close()
            return

        if parts[0].upper() == "CONNECT":
            target = parts[1]
            host, port_str = (target.rsplit(":", 1) if ":" in target else (target, "443"))
            log.info(f"CONNECT {host}:{port_str}")
            while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass
            await _handle_connect(host, int(port_str), reader, writer)
        else:
            rest = await reader.read(65536)
            fake = asyncio.StreamReader()
            fake.feed_data(first_line + rest)
            fake.feed_eof()
            await _forward_http(fake, writer)

    except Exception as e:
        log.debug(f"Handler error: {e}")
        try:
            writer.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    server = await asyncio.start_server(_handle, PROXY_HOST, PROXY_PORT)
    addr = server.sockets[0].getsockname()
    log.info(f"ResilientProxy listening on http://{addr[0]}:{addr[1]}")
    log.info(f"Stats: http://{addr[0]}:{addr[1]}/_proxy/stats")
    log.info("Export: HTTP_PROXY=http://127.0.0.1:60000  HTTPS_PROXY=http://127.0.0.1:60000")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Proxy stopped.")
