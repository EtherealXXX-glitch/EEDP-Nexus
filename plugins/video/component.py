"""Video playback runs in a component-owned mpv process, never in the service UI thread."""
from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import uuid
from urllib.parse import urlsplit

from core import field


class VideoPlayer:
    id = "video"
    name = "视频播放"
    description = "在工作台视频窗口播放本地文件或网络流；原始视频需指定格式参数。"
    actions = {
        "status": dict(label="播放状态", read_only=True, destructive=False, fields=[]),
        "attach": dict(label="绑定播放窗口", read_only=False, destructive=False,
                       fields=[field("window_id", "窗口句柄", 0, kind="int", remember=False)]),
        "play": dict(label="播放", read_only=False, destructive=False, fields=[
            field("source", "本地路径或视频地址", "", remember=False),
            field("format", "输入格式", "auto", ["auto", "h264", "mjpeg", "mpegts", "rawvideo"]),
            field("width", "YUV 宽度", 640, kind="int"), field("height", "YUV 高度", 480, kind="int"),
            field("pixel_format", "YUV 像素格式", "yuv420p", ["yuv420p", "nv12", "nv21", "yuyv422", "uyvy422", "yuv422p", "yuv444p"]),
            field("fps", "YUV 帧率", 25.0, kind="float")]),
        "pause": dict(label="暂停或继续", read_only=False, destructive=False, fields=[]),
        "stop": dict(label="停止", read_only=False, destructive=False, fields=[]),
        "seek": dict(label="跳转秒数", read_only=False, destructive=False,
                     fields=[field("seconds", "绝对时间（秒）", 0.0, kind="float", remember=False)]),
        "volume": dict(label="音量", read_only=False, destructive=False,
                       fields=[field("level", "音量 0–100", 80, kind="int")]),
    }

    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources
        self.lock = threading.RLock()
        self.process = None
        self.window_id = 0
        self.pipe = ""
        self.last_error = ""
        self.paused = False
        self.engine = Path(__file__).resolve().parent / "bin" / "mpv.exe"

    def status(self):
        with self.lock:
            code = self.process.poll() if self.process is not None else None
            running = self.process is not None and code is None
            if code not in (None, 0): self.last_error = f"播放器退出（代码 {code}），请检查视频格式和地址"
            return dict(state="running" if running else "failed" if self.last_error else "idle", playing=running,
                        paused=self.paused if running else False, window_id=self.window_id,
                        engine_available=self.engine.is_file(), error=self.last_error)

    def attach(self, window_id=0):
        if os.name != "nt" or window_id <= 0 or not ctypes.windll.user32.IsWindow(int(window_id)):
            raise ValueError("无效的视频窗口，请先打开工作台的视频播放页面")
        with self.lock:
            if self.process and self.process.poll() is None and window_id != self.window_id:
                raise ValueError("视频正在播放，请先停止")
            self.window_id = int(window_id)
            return self.status()

    def play(self, source="", format="auto", width=640, height=480, pixel_format="yuv420p", fps=25.0):
        source = source.strip()
        if not source: raise ValueError("请选择视频文件或输入视频地址")
        if not self.engine.is_file(): raise FileNotFoundError("缺少视频播放引擎 mpv.exe")
        if format not in ("auto", "h264", "mjpeg", "mpegts", "rawvideo"): raise ValueError("不支持的输入格式")
        if pixel_format not in ("yuv420p", "nv12", "nv21", "yuyv422", "uyvy422", "yuv422p", "yuv444p"): raise ValueError("不支持的像素格式")
        if format in ("rawvideo", "h264", "mjpeg") and (not math.isfinite(float(fps)) or not 0 < float(fps) <= 240):
            raise ValueError("帧率超出范围")
        if format == "rawvideo" and (not 1 <= int(width) <= 8192 or not 1 <= int(height) <= 8192):
            raise ValueError("YUV 宽高或帧率超出范围")
        parsed = urlsplit(source)
        if len(parsed.scheme) > 1:
            if parsed.scheme.lower() not in ("http", "https", "rtsp", "udp", "rtp"): raise ValueError("不支持的视频地址协议")
            if parsed.username or parsed.password: raise ValueError("地址中不能包含账号密码")
        elif not Path(source).is_file():
            raise ValueError("视频文件不存在")
        with self.lock:
            if not self.window_id or os.name != "nt" or not ctypes.windll.user32.IsWindow(self.window_id):
                raise ValueError("请先打开工作台的视频播放页面")
        self.stop()
        with self.lock:
            self.pipe = r"\\.\pipe\eedp-video-" + uuid.uuid4().hex
            args = [str(self.engine), "--no-config", "--no-terminal", "--no-osc", "--keep-open=no",
                    "--input-ipc-server=" + self.pipe, "--wid=" + str(self.window_id)]
            if format == "rawvideo":
                args += ["--demuxer=rawvideo", f"--demuxer-rawvideo-w={int(width)}", f"--demuxer-rawvideo-h={int(height)}",
                         "--demuxer-rawvideo-mp-format=" + pixel_format, f"--demuxer-rawvideo-fps={float(fps)}"]
            elif format != "auto":
                args.append("--demuxer-lavf-format=" + format)
                if format in ("h264", "mjpeg"):
                    args += ["--no-correct-pts", f"--container-fps-override={float(fps)}"]
            args += ["--", source]
            self.process = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.paused = False
            self.last_error = ""
            return self.status()

    def _command(self, *command):
        with self.lock:
            if not self.process or self.process.poll() is not None: raise ValueError("当前没有播放中的视频")
            try:
                with open(self.pipe, "r+b", buffering=0) as channel:
                    channel.write((json.dumps({"command": list(command)}) + "\n").encode("utf-8"))
            except OSError as exc:
                raise ValueError("播放器尚未就绪或已关闭，请稍后重试") from exc

    def pause(self):
        self._command("cycle", "pause")
        self.paused = not self.paused
        return self.status()

    def seek(self, seconds=0.0):
        if not math.isfinite(float(seconds)) or seconds < 0: raise ValueError("时间不能为负数")
        self._command("seek", float(seconds), "absolute")
        return self.status()

    def volume(self, level=80):
        if not 0 <= int(level) <= 100: raise ValueError("音量必须为 0–100")
        self._command("set_property", "volume", int(level))
        return self.status()

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            self.paused = False
            self.last_error = ""
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        return self.status()

    def close(self):
        self.stop()
