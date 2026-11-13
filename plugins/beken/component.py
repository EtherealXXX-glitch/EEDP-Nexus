from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
from core import field

BUNDLED_ENGINE = Path(__file__).resolve().parent / "bin/bk_loader.exe"
DEFAULT_ENGINE = os.environ.get("EEDP_BEKEN_ENGINE",str(BUNDLED_ENGINE))


class OutputLines:
    """Progress is terminated by CR, ordinary log lines by LF or CRLF."""
    def __init__(self):
        self.pending = b""

    def feed(self, data, final=False):
        pieces = re.split(rb"\r\n|\r|\n", self.pending + data)
        self.pending = pieces.pop()
        if final and self.pending:
            pieces.append(self.pending)
            self.pending = b""
        return [piece.decode("utf-8", errors="replace") for piece in pieces if piece]


class BekenFlash:
    id = "beken"
    name = "Beken 烧录"
    description = "独立烧录组件，调用本机 bk_loader 引擎。先预检，再显式启动任务；不会自动断开其他组件。"
    common = [field("firmware", "固件文件", str(Path.home() / "Desktop/all-app.bin")),
              field("port", "串口", "COM14"), field("baudrate", "波特率", 1500000, kind="int"),
              field("address", "起始地址", "0x0"),
              field("engine", "烧录引擎", DEFAULT_ENGINE, remember=False)]
    actions = {
        "inspect": dict(label="预检固件 / 命令", fields=common),
        "start": dict(label="启动烧录", destructive=True, fields=common),
        "status": dict(label="任务状态", fields=[]),
        "cancel": dict(label="中止任务", destructive=True, fields=[])}

    for _action, _definition in actions.items():
        _definition["read_only"] = _action in ("inspect", "status")
        _definition.setdefault("destructive", False)
    del _action, _definition

    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources
        self.lock = threading.RLock()
        self.job = dict(state="idle", stage="等待任务")
        self.state_file = activity.directory / "last-flash.json"
        if self.state_file.exists():
            try:
                self.job = json.loads(self.state_file.read_text(encoding="utf-8"))
                if self.job.get("state") == "running":
                    self.job.update(state="interrupted", stage="上次服务异常结束，请核对设备与烧录日志")
            except (OSError, ValueError):
                pass
        self.process = None
        self.worker = None
        self.cancelled = threading.Event()

    @staticmethod
    def plan(firmware, port="COM14", baudrate=1500000, address="0x0", engine=DEFAULT_ENGINE):
        file = Path(firmware).expanduser().resolve(strict=True)
        loader = Path(engine).expanduser().resolve(strict=True)
        if not file.is_file() or file.suffix.lower() != ".bin":
            raise ValueError("请选择有效的 .bin 文件")
        if not loader.is_file() or loader.name.lower() != "bk_loader.exe":
            raise ValueError("请选择厂商的 bk_loader.exe")
        match = re.fullmatch(r"COM(\d+)", port.upper())
        if not match or not 0 <= int(match[1]) <= 255:
            raise ValueError("烧录串口必须为 COM0 至 COM255")
        baudrate, start = int(baudrate), int(str(address), 0)
        if not 1 <= baudrate <= 6000000 or start < 0 or start % 4096:
            raise ValueError("波特率范围为 1 至 6000000；起始地址必须 4K 对齐")
        data = file.read_bytes()
        if not data:
            raise ValueError("固件文件为空")
        padded = (len(data) + 255) // 256 * 256
        command = [str(loader), "download", "-p", match[1], "-b", str(baudrate),
                   "--uart-type", "CH340", "--mainBin-multi",
                   f"{file.as_posix()}@{hex(start)}-{hex(padded)}", "--fast-link", "1"]
        return dict(firmware=str(file), engine=str(loader), port=port.upper(), baudrate=baudrate,
                    address=hex(start), length=len(data), transfer_length=padded,
                    sha256=hashlib.sha256(data).hexdigest(), command=command)

    def inspect(self, **kwargs):
        plan = self.plan(**kwargs)
        plan["resources"] = self.resources.status()
        return plan

    def start(self, **kwargs):
        plan = self.plan(**kwargs)
        with self.lock:
            if self.job["state"] == "running":
                raise ValueError("已有烧录任务正在运行")
            self.resources.acquire(plan["port"], self.id)
            directory = self.activity.directory / ("flash-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
            try:
                directory.mkdir()
                snapshot = directory / "firmware.bin"
                shutil.copyfile(plan["firmware"], snapshot)
                if hashlib.sha256(snapshot.read_bytes()).hexdigest() != plan["sha256"]:
                    raise ValueError("固件在预检期间发生变化，请重试")
                command = list(plan["command"])
                command[-3] = f"{snapshot.as_posix()}@{plan['address']}-{hex(plan['transfer_length'])}"
                self.cancelled.clear()
                self.job = dict(id=directory.name, state="running", stage="启动引擎", started=time.time(),
                                phase_progress=None,
                                firmware=plan["firmware"], sha256=plan["sha256"],
                                port=plan["port"], log=str(directory / "engine.log"), command=command)
                self._save_state()
                self.worker = threading.Thread(target=self._run, args=(command, directory, plan["port"]), daemon=True)
                self.worker.start()
            except Exception:
                self.resources.release(plan["port"], self.id)
                raise
            return self.status()

    def _save_state(self):
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.job, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.state_file)

    def _output(self, text):
        self.activity.emit(self.id, "output", text)
        with self.lock:
            if "Getting Bus" in text:
                self.job.update(stage="连接设备", phase_progress=None)
            if "Begin EraseFlash" in text:
                self.job.update(stage="擦除目标区域", phase_progress=None)
            if "Begin write to flash" in text:
                self.job.update(stage="写入固件", phase_progress=None)
            match = re.search(r"(Erasing|Writing)\s+Flash.*?(\d+)%", text)
            if match:
                self.job.update(stage="擦除目标区域" if match[1] == "Erasing" else "写入固件",
                                phase_progress=min(100, int(match[2])))

    def _run(self, command, directory, port):
        success_markers = set()
        try:
            with (directory / "engine.log").open("wb") as log:
                with self.lock:
                    self.process = subprocess.Popen(command, cwd=directory, stdout=log,
                        stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    process = self.process
                offset, splitter = 0, OutputLines()
                deadline = time.monotonic() + 300
                while True:
                    with (directory / "engine.log").open("rb") as source:
                        source.seek(offset)
                        data = source.read()
                        offset += len(data)
                    for text in splitter.feed(data, final=process.poll() is not None):
                        self._output(text)
                        for marker in ("WriteFlash ->pass", "Writing Flash OK", "All Finished Successfully"):
                            if marker in text:
                                success_markers.add(marker)
                    if process.poll() is not None:
                        # One extra read after exit captures buffered final output.
                        if (directory / "engine.log").stat().st_size > offset:
                            continue
                        break
                    if self.cancelled.is_set() or time.monotonic() > deadline:
                        process.terminate()
                        process.wait(5)
                        raise RuntimeError("任务已中止，设备可能需要重新烧录" if self.cancelled.is_set() else "烧录超过 300 秒，已终止")
                    time.sleep(0.2)
                with self.lock:
                    self.job["engine_exitcode"] = process.returncode
                # Vendor 2.1.11.6 returns 1 even after a successful download.
                # Require all three markers from this task's fresh log, not just an exit code.
                if len(success_markers) != 3 or process.returncode not in (0, 1):
                    raise RuntimeError(f"烧录未确认成功，引擎退出码 {process.returncode}，请查看日志")
                with self.lock:
                    self.job.update(state="succeeded", stage="烧录成功", phase_progress=100)
        except Exception as exc:
            with self.lock:
                self.job.update(state="cancelled" if self.cancelled.is_set() else "failed", stage=str(exc))
            self.activity.emit(self.id, "error", str(exc))
        finally:
            with self.lock:
                if self.process is not None and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait(5)
                self.process = None
                self.job["finished"] = time.time()
                self.resources.release(port, self.id)
                self._save_state()
                self.activity.emit(self.id, "finished", self.job["stage"])

    def status(self):
        with self.lock:
            return dict(self.job)

    def cancel(self):
        with self.lock:
            if self.job["state"] != "running":
                raise ValueError("没有正在运行的烧录任务")
            self.cancelled.set()
            return dict(cancellation_requested=True)

    def close(self):
        if self.worker and self.worker.is_alive():
            self.cancelled.set()
            self.worker.join(8)
