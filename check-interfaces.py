"""Read-only live MCP smoke test; never opens a port, sends bytes or flashes."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading


def main():
    root = Path(__file__).resolve().parent
    command = [sys.executable, str(root / "mcp-bridge.py")]
    pointer = Path.home() / ".eedp-agent.json"
    if pointer.exists():
        installed = json.loads(pointer.read_text(encoding="utf-8-sig"))["root"]
        if os.name != "nt" and len(installed)>1 and installed[1]==":":
            installed = subprocess.check_output(["wslpath", "-u", installed], text=True).strip()
        app = Path(installed)
        command = [str(app / "EEDP-Agent.exe"), "mcp"] if os.name == "nt" else [sys.executable, str(app / "agent_bridge/mcp-bridge.py")]
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
    replies = queue.Queue()
    def reader():
        for line in process.stdout:
            try: replies.put(json.loads(line))
            except ValueError: replies.put({"unexpected_stdout": line})
    threading.Thread(target=reader, daemon=True).start()
    identifier = 0
    def send(method, params=None):
        nonlocal identifier
        identifier += 1
        process.stdin.write(json.dumps(dict(jsonrpc="2.0", id=identifier, method=method, params=params or {})) + "\n")
        process.stdin.flush()
        while True:
            response = replies.get(timeout=30)
            if response.get("id") == identifier:
                if "error" in response: raise RuntimeError(response["error"])
                return response["result"]
    try:
        initialized = send("initialize", {"protocolVersion":"2025-11-25","clientInfo":{"name":"read-only-interface-check","version":"1.0"},"capabilities":{}})
        process.stdin.write(json.dumps(dict(jsonrpc="2.0",method="notifications/initialized")) + "\n")
        process.stdin.flush()
        tools = send("tools/list")["tools"]
        assert any(x["name"] == "workbench_status" for x in tools)
        result = send("tools/call", {"name":"workbench_status","arguments":{}})
        assert not result["isError"]
        status = result["structuredContent"]
        if any(t["name"] == "serial__status" for t in tools):
            call = send("tools/call", {"name":"serial__status","arguments":{}})
            assert not call["isError"]
        print(json.dumps(dict(protocol=initialized["protocolVersion"], tool_count=len(tools),
            server_version=status.get("version"), session=status["session"],
            component_ids=list(status["components"]), event_cursor=status.get("event_cursor")),ensure_ascii=False))
    finally:
        process.stdin.close()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__": main()
