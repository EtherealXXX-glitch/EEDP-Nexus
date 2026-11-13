"""Local agent workbench. Components are discovered through describe/call."""
from __future__ import annotations

import argparse
import hmac
import json
import os
from pathlib import Path
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time

from core import Activity, Registry, Resources
from plugin_manager import Plugins
from settings import Settings
from api import dispatch, VERSION
from app_paths import ROOT, STATE, service_command, APP_NAME
from log_store import diagnostic_path

def build_registry(directory=STATE):
    activity, resources = Activity(directory / "logs"), Resources()
    registry = Registry(activity, resources, Settings(directory / "settings.json"))
    Plugins(ROOT / "plugins", registry).rescan()
    return registry


def request(method, arguments=None, directory=STATE, client=None):
    endpoint = json.loads((directory / "endpoint.json").read_text(encoding="utf-8"))
    payload = dict(token=endpoint["token"], method=method, arguments=arguments or {},
                   client=client or os.environ.get("AGENT_WORKBENCH_CLIENT", "windows-cli"))
    with socket.create_connection(("127.0.0.1", endpoint["port"]), timeout=120 if method.startswith("logs.") else 8) as conn:
        conn.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        with conn.makefile("rb") as stream:
            response = json.loads(stream.readline(20_000_000))
    if not response["ok"]:
        raise RuntimeError(response["error"])
    return response["result"]


def ensure_started():
    try:
        request("ping")
        return
    except (OSError, ValueError, RuntimeError):
        pass
    STATE.mkdir(parents=True, exist_ok=True)
    with diagnostic_path(STATE, "startup.log").open("ab") as log:
        subprocess.Popen(service_command(), cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(60):
        try:
            request("ping")
            return
        except (OSError, ValueError, RuntimeError):
            time.sleep(0.1)
    raise RuntimeError(f"后台服务未启动，请查看 {STATE / 'startup.log'}")


def serve():
    import msvcrt
    STATE.mkdir(parents=True, exist_ok=True)
    singleton = (STATE / "service.lock").open("a+b")
    singleton.seek(0)
    if singleton.read(1) == b"":
        singleton.write(b"0")
        singleton.flush()
    singleton.seek(0)
    try:
        msvcrt.locking(singleton.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        singleton.close()
        return
    registry = build_registry()
    token = secrets.token_urlsafe(32)
    maintenance_stopped = threading.Event()
    def maintain_logs():
        while not maintenance_stopped.is_set():
            try: registry.logs.maintain()
            except Exception as exc: registry.activity.emit("workbench", "error", "日志维护失败：" + str(exc))
            maintenance_stopped.wait(3600)
    maintenance_thread = threading.Thread(target=maintain_logs, daemon=True)
    maintenance_thread.start()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(10)
            try:
                line = self.rfile.readline(1_000_001)
                if len(line) > 1_000_000:
                    raise ValueError("请求过大")
                incoming = json.loads(line)
                if not hmac.compare_digest(str(incoming.get("token", "")), token):
                    raise ValueError("未授权的本地客户端")
                method, params = incoming["method"], incoming.get("arguments", {})
                if method == "ping": result = dict(pid=os.getpid(), version=VERSION)
                elif method == "shutdown":
                    with registry.lock:
                        if any(registry.in_flight.values()) or any(c.status().get("state") == "running" for c in registry.components.values()):
                            raise ValueError("组件调用/任务正在运行，请先等待完成或显式中止任务")
                        registry.closing = True
                    result = dict(stopping=True)
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else: result = dispatch(registry, method, params, str(incoming.get("client", "unknown"))[:100])
                answer = dict(ok=True, result=result)
            except Exception as exc:
                answer = dict(ok=False, error=str(exc))
            self.wfile.write(json.dumps(answer, ensure_ascii=False).encode("utf-8") + b"\n")

    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = False
        request_queue_size = 16
        slots = threading.BoundedSemaphore(16)

        def process_request(self, request, client_address):
            if not self.slots.acquire(blocking=False):
                try: request.sendall(b'{"ok":false,"error":"Server busy; retry later"}\n')
                finally: self.shutdown_request(request)
                return
            try: super().process_request(request,client_address)
            except Exception:
                self.slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try: super().process_request_thread(request,client_address)
            finally: self.slots.release()

    try:
        with Server(("127.0.0.1", 0), Handler) as server:
            temporary = STATE / "endpoint.tmp"
            temporary.write_text(json.dumps(dict(port=server.server_address[1], token=token)), encoding="utf-8")
            temporary.replace(STATE / "endpoint.json")
            registry.activity.emit("workbench", "started", "本地组件服务已启动；尚未连接设备")
            server.serve_forever(poll_interval=0.2)
    finally:
        maintenance_stopped.set()
        maintenance_thread.join()
        registry.close()
        (STATE / "endpoint.json").unlink(missing_ok=True)
        singleton.close()


def gui():
    from desktop import launch
    return launch(lambda method, arguments=None: request(method, arguments, client="desktop"), ensure_started, STATE)


def main():
    parser = argparse.ArgumentParser(description=APP_NAME + "：可发现、可调用的本地组件")
    parser.add_argument("command", nargs="?", default="gui", choices=["gui", "serve", "tools", "status", "call", "events", "stop", "rpc", "mcp", "setup", "shell"])
    parser.add_argument("--wsl",action="store_true",help="setup: also register the default WSL distribution")
    parser.add_argument("--plan",action="store_true",help="setup: print configuration without writing files")
    parser.add_argument("target", nargs="?")
    parser.add_argument("--args", default="{}", help="JSON 参数对象")
    parser.add_argument("--args-file", help="UTF-8 JSON 参数文件，避免 Shell 转义")
    parser.add_argument("--after", type=int, default=0)
    parser.add_argument("--component", default="")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--client", default=None, help="调用来源标识（审计标签，不授予权限）")
    args = parser.parse_args()
    if args.command=='shell':
        from windows_identity import set_shortcut_identity
        if not args.target:raise ValueError('A shortcut path is required')
        set_shortcut_identity(args.target)
        return
    if args.command=="setup":
        from agent_setup import main as setup
        return setup(["--root",str(ROOT),*(["--wsl"] if args.wsl else []),*(["--plan"] if args.plan else [])])
    if args.command == "serve": return serve()
    if args.command == "gui": return gui()
    if args.command == "mcp":
        from mcp_adapter import serve_mcp
        ensure_started()
        return serve_mcp(lambda method, arguments=None: request(method, arguments, client="mcp-windows"))
    if args.command != "stop": ensure_started()
    if args.command in ("call", "rpc"):
        payload = json.loads(Path(args.args_file).read_text(encoding="utf-8-sig") if args.args_file else args.args)
        if not isinstance(payload, dict): raise ValueError("参数必须是 JSON 对象")
        result = request("call", dict(target=args.target, arguments=payload), client=args.client) if args.command == "call" else request(args.target, payload, client=args.client)
    elif args.command == "events":
        cursor = args.after
        while True:
            result = request("events", dict(after=cursor, component=args.component), client=args.client)
            print(json.dumps(result, ensure_ascii=False), flush=True)
            cursor = result["cursor"]
            if not args.watch: return
            time.sleep(0.5)
    else: result = request("shutdown" if args.command == "stop" else args.command, client=args.client)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.stdin is not None:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        main()
    except Exception as exc:
        if sys.stderr is not None:
            print(str(exc), file=sys.stderr)
        else:
            STATE.mkdir(parents=True, exist_ok=True)
            with diagnostic_path(STATE, "startup.log").open("a", encoding="utf-8") as log:
                import traceback
                traceback.print_exc(file=log)
        sys.exit(1)
