#!/usr/bin/env sh

if [ -z "$PORT" ]; then
  PORT=3000
fi

mcp-proxy --pass-environment --sse-port=$PORT --sse-host 0.0.0.0 uv run mcp-obsidian
