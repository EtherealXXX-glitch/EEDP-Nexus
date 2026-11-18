"""Portable MCP entry point for Windows or WSL agents (standard library only)."""
import os
import sys
from bridge_client import Client
from mcp_adapter import serve_mcp

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8")
    client = Client("mcp-windows" if os.name == "nt" else "mcp-wsl")
    serve_mcp(client.request)
