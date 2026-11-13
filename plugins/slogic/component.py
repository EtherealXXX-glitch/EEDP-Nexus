"""Agent-first SLogic adapter. No device access occurs during plugin loading."""
import copy
import configparser
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
import zipfile

from core import field

DRIVER = "sipeed-slogic-analyzer"


def capture_fields():
    return [field("device", "设备（扫描返回的标识）", DRIVER),
            field("channels", "通道，逗号分隔", "D0"),
            field("samplerate", "采样率 Hz", 10000000, kind="int"),
            field("duration_ms", "采样时长 ms", 100, kind="int"),
            field("trigger", "触发，例如 D0=r；空为立即采集", ""),
            field("timeout_s", "含等待触发的最长任务秒数", 30, kind="int")]


class SLogic:
    id = "slogic"
    name = "SLogic 逻辑分析仪"
    description = "SLogic Combo8：设备发现、有界采集、离线协议解码及波形导出。采集前确认接线、电压及通道。"
    actions = {
        "status": dict(label="任务状态", fields=[]),
        "devices": dict(label="扫描设备", fields=[]),
        "capabilities": dict(label="设备能力", fields=[field("device", "设备标识", DRIVER)]),
        "decoder": dict(label="解码器说明", fields=[field("name", "解码器 ID", "uart")]),
        "inspect": dict(label="预检采集（不采样）", fields=capture_fields()),
        "start": dict(label="开始采集", destructive=True, fields=capture_fields()+[
            field("signal_voltage", "已确认的信号电压 V", 0.0, kind="float", remember=False),
            field("common_ground", "已确认共地", False, kind="bool", remember=False)]),
        "cancel": dict(label="取消当前任务", destructive=True, fields=[]),
        "decode": dict(label="离线协议解码", fields=[
            field("input", "输入 .sr 波形绝对路径", remember=False),
            field("decoder", "解码器和引脚映射，如 uart:rx=D0:baudrate=115200", "uart:rx=D0:baudrate=115200"),
            field("timeout_s", "最长任务秒数", 60, kind="int")]),
        "export": dict(label="离线导出波形", fields=[
            field("input", "输入 .sr 波形绝对路径", remember=False),
            field("format", "导出格式", "vcd", ["vcd", "csv"]),
            field("timeout_s", "最长任务秒数", 60, kind="int")]),
        "waveform": dict(label="读取波形窗口（不采样）", log_result="summary", fields=[
            field("input", "输入 .sr 波形绝对路径", remember=False),
            field("start_sample", "窗口起始采样点", 0, kind="int"),
            field("sample_count", "窗口采样点数，0 为全部", 0, kind="int"),
            field("pixels", "时间轴桶数上限", 1200, kind="int")]),
    }

    for _action, _definition in actions.items():
        _definition["read_only"] = _action in ("status", "devices", "capabilities", "decoder", "inspect", "waveform")
        _definition.setdefault("destructive", False)
    del _action, _definition

    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources
        self.engine = Path(__file__).parent / "bin/sigrok-cli.exe"
        self.directory = activity.directory / "slogic"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.runtime = activity.directory.parent / "runtime/slogic"
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.cancelled = threading.Event()
        self.worker = None
        self.job = dict(state="idle", stage="等待任务")
        state = self.directory / "last-task.json"
        if state.exists():
            try:
                self.job = json.loads(state.read_text(encoding="utf-8"))
                if self.job.get("state") == "running": self.job.update(state="interrupted", stage="服务重启，任务已中断")
            except (ValueError, OSError): pass

    def _env(self):
        return {**os.environ, "TEMP": str(self.runtime), "TMP": str(self.runtime)}

    def _command(self, args):
        if not self.engine.is_file(): raise ValueError("缺少插件 bin/sigrok-cli.exe，请安装完整 SLogic 工具包")
        return [str(self.engine.resolve()), *args]

    def _run_query(self, args):
        process = subprocess.Popen(self._command(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=self._env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try: output,error = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self._kill(process)
            raise TimeoutError("设备/解码器查询超时，已停止本组件的查询进程树")
        if process.returncode: raise RuntimeError((error or output)[-8000:])
        return output

    def _idle(self):
        with self.lock:
            if self.job.get("state") == "running": raise ValueError("逻辑分析仪任务正在运行，请先等待完成或取消")

    @staticmethod
    def _device(device):
        if not re.fullmatch(r"sipeed-slogic-analyzer(?::conn=[A-Za-z0-9_.-]+)?", device):
            raise ValueError("设备标识须来自 SLogic 扫描；只接受驱动名或 :conn=连接标识")
        return device

    def devices(self):
        self._idle()
        output = self._run_query(["--driver", DRIVER, "--scan"])
        devices = [dict(spec=match[0], description=match[1]) for match in re.findall(
            r"^(sipeed-slogic-analyzer[^\s]*) - (.+)$", output, re.M)]
        return dict(devices=devices, raw=output)

    def capabilities(self, device=DRIVER):
        self._idle()
        output = self._run_query(["--driver", self._device(device), "--show"])
        if not re.search(r"sipeed-slogic-analyzer[^\n]*with \d+ channels", output):
            raise ValueError("未识别到目标设备：" + output[-2000:])
        rates = [int(float(number) * {"Hz":1,"kHz":1000,"MHz":1000000}[unit])
                 for number, unit in re.findall(r"^\s+(\d+(?:\.\d+)?) (Hz|kHz|MHz)(?: \(current\))?\s*$", output, re.M)]
        return dict(device=device, channels=sorted(set(re.findall(r"\bD[0-7]\b", output))), samplerates=rates, raw=output)

    def decoder(self, name="uart"):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name): raise ValueError("无效解码器 ID")
        return dict(name=name, raw=self._run_query(["--protocol-decoders", name, "--show"]))

    def inspect(self, device=DRIVER, channels="D0", samplerate=10000000, duration_ms=100, trigger="", timeout_s=30):
        self._idle()
        selected = [x.strip() for x in channels.split(",")]
        if not selected or len(set(selected)) != len(selected) or any(not re.fullmatch(r"D[0-7]", x) for x in selected):
            raise ValueError("通道须为 D0 至 D7，不可重复")
        if not 1 <= duration_ms <= 60000 or not duration_ms/1000 + 2 <= timeout_s <= 120:
            raise ValueError("时长须为 1–60000ms，超时须覆盖采样时长加 2 秒，且不超过 120 秒")
        if not 1 <= samplerate <= 80000000: raise ValueError("无效采样率")
        if samplerate * duration_ms / 1000 > 100000000: raise ValueError("单次最多采集一亿个采样点，请缩短时长")
        if samplerate * len(selected) > 160000000: raise ValueError("Combo8 Windows 采样带宽按 160Mb/s 限制，请减少通道或采样率")
        if trigger and (not re.fullmatch(r"D[0-7]=[01rfe]", trigger) or trigger.split("=")[0] not in selected):
            raise ValueError("触发应为已启用通道，例如 D0=r / D1=f")
        self._device(device)
        found = self.devices()["devices"]
        if not found: raise ValueError("未发现 SLogic，请连接设备并切到蓝灯逻辑分析仪模式")
        if len(found) != 1 and device == DRIVER: raise ValueError("发现多个设备，请指定 :conn= 选择目标")
        capability = self.capabilities(device)
        if not set(selected).issubset(capability["channels"]): raise ValueError("选择了设备不支持的通道")
        if samplerate not in capability["samplerates"]: raise ValueError("采样率不在当前设备支持的档位中")
        args = ["--driver", device, "--config", f"samplerate={samplerate}", "--channels", ",".join(selected),
                "--time", str(duration_ms), "-O", "srzip"]
        if trigger: args += ["--triggers", trigger, "--wait-trigger"]
        return dict(kind="capture", args=args, timeout_s=timeout_s, device=device, channels=selected,
                    samplerate=samplerate, duration_ms=duration_ms, trigger=trigger,
                    estimated_samples=samplerate*duration_ms//1000)

    def start(self, signal_voltage=0.0, common_ground=False, **kwargs):
        if not 0 < signal_voltage <= 3.6 or common_ground is not True:
            raise ValueError("采样前须确认 TX/信号电压在 0–3.6V 范围内并已共地；未知电压不能采样")
        plan = self.inspect(**kwargs)
        plan.update(signal_voltage=signal_voltage, common_ground=common_ground)
        return self._spawn(plan, "capture.sr", hardware=True)

    @staticmethod
    def _input(input):
        path = Path(input).resolve()
        if path.suffix.lower() != ".sr" or not path.is_file(): raise ValueError("请选择存在的 .sr 波形文件")
        if path.stat().st_size > 256*1024**2: raise ValueError("本版单文件最大 256MB")
        with zipfile.ZipFile(path) as archive:
            if "metadata" not in archive.namelist(): raise ValueError("无效 sigrok 波形：缺少 metadata")
        return path

    def decode(self, input="", decoder="uart:rx=D0:baudrate=115200", timeout_s=60):
        self._idle()
        path = self._input(input)
        if not re.fullmatch(r"[A-Za-z0-9_-]+(?::[A-Za-z0-9_-]+=[A-Za-z0-9_.+-]+)+", decoder):
            raise ValueError("须指定解码器及引脚映射，如 uart:rx=D0:baudrate=115200")
        if not re.search(r":[A-Za-z0-9_-]+=D[0-7](?=:|$)", decoder):
            raise ValueError("必须明确指定至少一条解码引脚到 D0–D7 的映射")
        self.decoder(decoder.split(":")[0])
        return self._spawn(dict(kind="decode", args=["-i", str(path), "-P", decoder, "-A", decoder.split(":")[0],
            "--protocol-decoder-samplenum", "--protocol-decoder-ann-class"], timeout_s=timeout_s,
            input=str(path), decoder=decoder), "decoded.txt")

    def export(self, input="", format="vcd", timeout_s=60):
        self._idle()
        path = self._input(input)
        if format not in ("vcd", "csv"): raise ValueError("仅支持 vcd / csv")
        return self._spawn(dict(kind="export", args=["-i", str(path), "-O", format], timeout_s=timeout_s,
            input=str(path), format=format), "waveform."+format)

    def waveform(self, input="", start_sample=0, sample_count=0, pixels=1200):
        path = self._input(input)
        if start_sample < 0 or sample_count < 0 or not 64 <= pixels <= 4000:
            raise ValueError("采样窗口不可为负；时间轴桶数须为 64–4000")
        with zipfile.ZipFile(path) as archive:
            metadata_info = archive.getinfo("metadata")
            if metadata_info.file_size > 65536: raise ValueError("异常波形元信息")
            config = configparser.ConfigParser()
            config.read_string(archive.read("metadata").decode("utf-8"))
            device = config["device 1"]
            rate_text = device.get("samplerate", "")
            match = re.fullmatch(r"\s*([\d.]+)\s*([kMGT]?)Hz\s*", rate_text)
            if not match: raise ValueError("无法读取波形采样率")
            rate = float(match[1]) * {"":1,"k":1000,"M":1000000,"G":1000000000,"T":1000000000000}[match[2]]
            unit = int(device.get("unitsize", "1"))
            if unit != 1: raise ValueError("当前 Combo8 查看器仅支持每采样点 1 字节的数字波形")
            chunks = sorted((x for x in archive.infolist() if re.fullmatch(r"logic-1-\d+", x.filename)),
                            key=lambda x:int(x.filename.rsplit("-",1)[1]))
            total = sum(x.file_size for x in chunks)
            if not total or total > 100000000: raise ValueError("波形为空或超过一亿采样点查看上限")
            start = min(start_sample, total-1)
            count = min(sample_count or total, total-start)
            selected, offset = bytearray(), 0
            for chunk in chunks:
                begin, end = max(start-offset, 0), min(start+count-offset, chunk.file_size)
                if end > begin:
                    with archive.open(chunk) as stream:
                        stream.seek(begin)
                        selected.extend(stream.read(end-begin))
                offset += chunk.file_size
                if offset >= start+count: break
            step = max(1, (count+pixels-1)//pixels)
            probes = [(int(key[5:])-1, value) for key,value in device.items() if re.fullmatch(r"probe[1-8]",key)]
            if not probes: raise ValueError("波形缺少通道名")
            channels = []
            for bit, name in sorted(probes):
                levels = selected.translate(bytes(1 if x & (1<<bit) else 0 for x in range(256)))
                ranges = []
                for index in range(0,count,step):
                    bucket = levels[index:index+step]
                    ranges.append([0 if 0 in bucket else 1, 1 if 1 in bucket else 0])
                channels.append(dict(name=name, ranges=ranges))
        return dict(input=str(path), total_samples=total, samplerate=rate, start_sample=start,
            sample_count=count, bin_samples=step, exact=step==1, channels=channels)

    def _save(self):
        temporary = self.directory / "last-task.tmp"
        temporary.write_text(json.dumps(self.job, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.directory / "last-task.json")

    def _spawn(self, plan, filename, hardware=False):
        if not 1 <= plan["timeout_s"] <= 120: raise ValueError("任务超时须为 1 至 120 秒")
        with self.lock:
            self._idle()
            if hardware: self.resources.acquire("USB:SLOGIC", self.id)
            try:
                directory = self.directory / (datetime.now().strftime("%Y%m%d-%H%M%S-")+uuid.uuid4().hex[:6])
                directory.mkdir()
                args = list(plan["args"])
                if plan.get("input"):
                    source = Path(plan["input"])
                    before = source.stat()
                    snapshot = directory / "input.sr"
                    shutil.copyfile(source, snapshot)
                    after = source.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError("波形输入在快照期间变化，请等待采集完成后重试")
                    args[args.index("-i")+1] = str(snapshot)
                output = directory / filename
                if hardware: args += ["-o", str(output)]
                elif plan["kind"] == "export": args += ["-o", str(output)]
                command = self._command(args)
                self.cancelled.clear()
                self.job = dict(id=directory.name, state="running", stage="等待触发 / 采集" if hardware else "离线处理",
                    kind=plan["kind"], started=time.time(), output=str(output), command=command, plan=plan,
                    log=str(directory / "engine.log"))
                self._save()
                self.worker = threading.Thread(target=self._work, args=(directory, hardware), daemon=True)
                self.worker.start()
            except Exception:
                if hardware: self.resources.release("USB:SLOGIC", self.id)
                raise
            return self.status()

    @staticmethod
    def _kill(process):
        if process.poll() is not None: return
        if os.name == "nt":
            subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        else: process.kill()
        process.wait(timeout=10)

    def _work(self, directory, hardware):
        process = None
        try:
            output = Path(self.job["output"])
            stdout = output if self.job["kind"] == "decode" else directory / "stdout.log"
            with stdout.open("wb") as out, (directory / "engine.log").open("wb") as err:
                process = subprocess.Popen(self.job["command"], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                    env=self._env(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                deadline = time.monotonic()+self.job["plan"]["timeout_s"]
                while process.poll() is None:
                    if self.cancelled.wait(.1):
                        self._kill(process)
                        raise InterruptedError("用户取消任务")
                    if time.monotonic() > deadline:
                        self._kill(process)
                        raise TimeoutError("任务超时，已停止采集/解码进程树")
                    if any(p.exists() and p.stat().st_size > 256*1024**2 for p in (stdout, output, directory / "engine.log")):
                        self._kill(process)
                        raise ValueError("任务输出超过 256MB 上限")
            error = (directory / "engine.log").read_text(encoding="utf-8", errors="replace")[-8000:]
            if process.returncode: raise RuntimeError(f"sigrok-cli 退出码 {process.returncode}: {error}")
            if not output.exists(): raise ValueError("工具未生成预期输出文件")
            if hardware:
                with zipfile.ZipFile(output) as archive:
                    if "metadata" not in archive.namelist() or not any(x.startswith("logic-") for x in archive.namelist()):
                        raise ValueError("波形缺少实际逻辑采样数据")
            with output.open("rb") as stream: digest = hashlib.file_digest(stream, "sha256").hexdigest()
            preview = ""
            if self.job["kind"] == "decode":
                with output.open("r", encoding="utf-8", errors="replace") as stream: preview = stream.read(16000)
            with self.lock:
                self.job.update(state="succeeded", stage="处理完成", bytes=output.stat().st_size,
                    sha256=digest, preview=preview, warning=error, annotations=bool(preview.strip()) if self.job["kind"] == "decode" else None)
        except InterruptedError as exc:
            with self.lock: self.job.update(state="cancelled", stage=str(exc))
        except Exception as exc:
            if process is not None and process.poll() is None: self._kill(process)
            with self.lock: self.job.update(state="failed", stage=str(exc))
            self.activity.emit(self.id, "error", str(exc))
        finally:
            if hardware: self.resources.release("USB:SLOGIC", self.id)
            with self.lock:
                self.job["finished"] = time.time()
                self._save()
                (directory / "manifest.json").write_text(json.dumps(self.job, ensure_ascii=False, indent=2), encoding="utf-8")
                self.activity.emit(self.id, "finished", json.dumps(self.job, ensure_ascii=False))

    def status(self):
        with self.lock:
            return {**copy.deepcopy(self.job), "engine_available": self.engine.is_file(), "engine":str(self.engine)}

    def cancel(self):
        self.cancelled.set()
        return self.status()

    def close(self):
        self.cancelled.set()
        if self.worker: self.worker.join(15)
