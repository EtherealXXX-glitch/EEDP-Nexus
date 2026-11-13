"""Verify the frozen distribution using an isolated state and loopback device."""
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent


def main():
    app = ROOT / "dist/EEDP Nexus"
    exe = app / "EEDP-Agent.exe"
    state = ROOT / "build/packaged-smoke-state"
    env = {**os.environ, "EEDP_STATE_DIR": str(state)}
    import pefile
    pe=pefile.PE(str(app/'EEDP Nexus.exe'))
    try:
        groups=next(entry for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries if entry.id==14)
        assert any(entry.id==1 for entry in groups.directory.entries),'Shell icon resource ID 1 missing'
    finally:pe.close()
    def cli(*arguments):
        p = subprocess.run([str(exe), *arguments], capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
        if p.returncode: raise RuntimeError(p.stdout + p.stderr)
        return json.loads(p.stdout)
    try:
        tools = cli("tools")
        assert {t["id"] for t in tools} == {"serial", "beken", "slogic"}, tools
        decoder=cli("call","slogic.decoder","--args",json.dumps({"name":"uart"}))
        assert "UART" in decoder["raw"]
        cli("call", "serial.connect", "--args", json.dumps(dict(port="loop://", baudrate=1500000)))
        payload = "EXE-串口回环"
        cli("call", "serial.send", "--args", json.dumps(dict(text=payload, newline="LF")))
        time.sleep(.2)
        status = cli("call", "serial.status")
        assert status["rx_bytes"] == len((payload + "\n").encode()), status
        cli("call", "serial.disconnect")
        history = cli("rpc", "logs.query", "--args", json.dumps(dict(component="serial", kind="tx", limit=10)))
        assert any(payload in x["text"] for x in history["events"])
        inventory = cli("rpc", "logs.inventory")
        assert inventory["policy"]["protect_history"]
        exported = cli("rpc", "logs.export", "--args", json.dumps(dict(filters={"kind":"tx"})))
        assert Path(exported["path"]).is_file()
        state.mkdir(parents=True, exist_ok=True)
        firmware = state / "probe.bin"
        firmware.write_bytes(bytes(range(256)) * 2)
        plan = cli("call", "beken.inspect", "--args", json.dumps(dict(firmware=str(firmware))))
        assert plan["sha256"] == hashlib.sha256(firmware.read_bytes()).hexdigest()
        assert str(app) in plan["engine"], plan["engine"]
        engine = subprocess.run([plan["engine"], "--help"], capture_output=True, text=True, timeout=10)
        assert "download" in engine.stdout
        p = subprocess.Popen([str(exe), "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        replies = queue.Queue()
        def read():
            for line in p.stdout: replies.put(json.loads(line))
        threading.Thread(target=read, daemon=True).start()
        def message(identifier, method, params=None):
            p.stdin.write(json.dumps(dict(jsonrpc="2.0", id=identifier, method=method, params=params or {}), ensure_ascii=False)+"\n")
            p.stdin.flush()
            while True:
                result = replies.get(timeout=15)
                if result.get("id") == identifier:
                    assert "error" not in result, result
                    return result["result"]
        try:
            message(1, "initialize", {"protocolVersion":"2025-11-25","clientInfo":{"name":"packaged-check","version":"1"},"capabilities":{}})
            catalog = message(2, "tools/list")
            expected_tools=12+sum(len(t["actions"]) for t in tools)
            assert len(catalog["tools"]) == expected_tools
            answer = message(3, "tools/call", {"name":"workbench_update_settings","arguments":{"scope":"smoke","values":{"label":"中文UTF-8"}}})
            assert answer["structuredContent"]["label"] == "中文UTF-8", answer
        finally:
            p.stdin.close()
            p.wait(timeout=10)
        print(json.dumps(dict(packaged_components=True, loopback=True, firmware_preflight=True,
            bundled_engine=True, mcp_tools=expected_tools, utf8_stdio=True, log_center_rpc=True, slogic_decoder=True, no_physical_device_touched=True), ensure_ascii=False))
    finally:
        cli("stop")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
