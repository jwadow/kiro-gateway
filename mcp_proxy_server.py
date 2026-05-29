#!/usr/bin/env python3
"""
MCP server — proxy control plane (Option B, synergized with Option A).

Exposes the forward_proxy's stats and control as MCP tools so OpenCode
agents can query rate-limit status, trigger proxy rotation, and inspect
traffic without leaving the agent loop.

Add to opencode.jsonc:
  "mcp": {
    "proxy-control": {
      "type": "stdio",
      "command": ["python3", "/home/x1/Documents/proxy/kiro-gateway/mcp_proxy_server.py"]
    }
  }

Tools:
  proxy_stats   — live counters (requests, retries, errors, uptime)
  proxy_health  — is the proxy up? latency check
  proxy_rotate  — signal proxy to flush connection pool (forces new connections)
"""

import asyncio
import json
import sys
import time
import urllib.request

PROXY_STATS_URL = "http://127.0.0.1:60000/_proxy/stats"


def _fetch_stats() -> dict:
    try:
        with urllib.request.urlopen(PROXY_STATS_URL, timeout=2) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _mcp_response(id_, result) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "result": result})


def _mcp_error(id_, msg: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "error": {"code": -32000, "message": msg}})


TOOLS = [
    {
        "name": "proxy_stats",
        "description": "Get live stats from the forward proxy: request count, retry count, error count, status code breakdown, uptime.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "proxy_health",
        "description": "Check if the forward proxy is running and measure its response latency.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "proxy_rotate",
        "description": "Flush the proxy's connection pool, forcing fresh connections on next requests. Use when you suspect stale/rate-limited connections.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def handle_request(req: dict) -> str:
    method = req.get("method")
    id_ = req.get("id")

    if method == "initialize":
        return _mcp_response(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "proxy-control", "version": "1.0.0"},
        })

    if method == "tools/list":
        return _mcp_response(id_, {"tools": TOOLS})

    if method == "tools/call":
        name = req.get("params", {}).get("name")

        if name == "proxy_stats":
            stats = _fetch_stats()
            return _mcp_response(id_, {
                "content": [{"type": "text", "text": json.dumps(stats, indent=2)}]
            })

        if name == "proxy_health":
            t0 = time.time()
            stats = _fetch_stats()
            latency_ms = round((time.time() - t0) * 1000, 1)
            up = "error" not in stats
            return _mcp_response(id_, {
                "content": [{"type": "text", "text": json.dumps({
                    "up": up,
                    "latency_ms": latency_ms,
                    "proxy_url": "http://127.0.0.1:60000",
                })}]
            })

        if name == "proxy_rotate":
            # Signal rotation by hitting a no-op endpoint; actual pool flush
            # happens in forward_proxy.py when _client is set to None
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:60000/_proxy/rotate", timeout=2
                )
                msg = "Pool flush signalled."
            except Exception:
                msg = "Proxy unreachable — start forward_proxy.py first."
            return _mcp_response(id_, {
                "content": [{"type": "text", "text": msg}]
            })

        return _mcp_error(id_, f"Unknown tool: {name}")

    # Notifications (no id) — silently ignore
    if id_ is None:
        return ""

    return _mcp_error(id_, f"Unknown method: {method}")


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_request(req)
        if response:
            print(response, flush=True)


if __name__ == "__main__":
    main()
