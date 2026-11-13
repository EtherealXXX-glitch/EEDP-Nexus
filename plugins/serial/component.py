from __future__ import annotations

import codecs
import threading
import serial
from serial.tools import list_ports
from core import field


class SerialMonitor:
    id = "serial"
    name = "串口监控"
    description = "独立串口组件：连接、收发和后台接收。原始数据以 Base64 写入活动日志，可无损还原。"
    actions = {
        "ports": dict(label="扫描串口", fields=[]),
        "status": dict(label="连接状态", fields=[]),
        "connect": dict(label="连接", fields=[
            field("port", "串口", "COM14"), field("baudrate", "波特率", 1500000, kind="int"),
            field("bytesize", "数据位", 8, [5, 6, 7, 8], "int"),
            field("parity", "校验位", "N", ["N", "E", "O", "M", "S"]),
            field("stopbits", "停止位", 1, [1, 1.5, 2], "float"),
            field("encoding", "编码", "utf-8", ["utf-8", "gb18030", "ascii"]),
            field("dtr", "DTR", False, kind="bool"), field("rts", "RTS", False, kind="bool")]),
        "disconnect": dict(label="断开并释放串口", fields=[]),
        "send": dict(label="发送", destructive=True, fields=[field("text", "发送内容"),
            field("hex_mode", "十六进制", False, kind="bool"),
            field("newline", "结尾", "CRLF", ["CRLF", "LF", "CR", "NONE"])])}

    for _action, _definition in actions.items():
        _definition["read_only"] = _action in ("ports", "status")
        _definition.setdefault("destructive", False)
    actions["connect"]["destructive"] = True
    del _action, _definition

    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources
        self.lock = threading.RLock()
        self.device = None
        self.worker = None
        self.rx = self.tx = 0
        self.last_error = ""
        self.encoding = "utf-8"
        self.configuration = {}

    def ports(self):
        return [dict(port=p.device, description=p.description, hwid=p.hwid) for p in list_ports.comports()]

    def status(self):
        with self.lock:
            return dict(connected=self.device is not None and self.device.is_open,
                        port=self.device.port if self.device else None,
                        baudrate=self.device.baudrate if self.device else None,
                        rx_bytes=self.rx, tx_bytes=self.tx, error=self.last_error, configuration=dict(self.configuration))

    def connect(self, port="COM14", baudrate=1500000, bytesize=8, parity="N", stopbits=1,
                encoding="utf-8", dtr=False, rts=False):
        with self.lock:
            if self.device is not None:
                raise ValueError("请先断开当前串口")
            codecs.lookup(encoding)
            self.resources.acquire(port, self.id)
            device = None
            try:
                device = serial.serial_for_url(port, do_not_open=True, baudrate=int(baudrate),
                    bytesize=int(bytesize), parity=parity, stopbits=float(stopbits),
                    timeout=0.1, write_timeout=2)
                device.dtr, device.rts = bool(dtr), bool(rts)
                device.open()
                self.device, self.encoding = device, encoding
                self.configuration = dict(port=port, baudrate=int(baudrate), bytesize=int(bytesize), parity=parity,
                                          stopbits=float(stopbits), encoding=encoding, dtr=bool(dtr), rts=bool(rts))
                self.rx = self.tx = 0
                self.last_error = ""
                self.worker = threading.Thread(target=self._receive, args=(device,), daemon=True)
                self.worker.start()
                return self.status()
            except Exception:
                if device:
                    device.close()
                self.resources.release(port, self.id)
                raise

    def _receive(self, device):
        decoder = codecs.getincrementaldecoder(self.encoding)(errors="replace")
        try:
            while device.is_open:
                data = device.read(min(device.in_waiting or 1, 16384))
                if data:
                    with self.lock:
                        self.rx += len(data)
                        self.activity.emit(self.id, "rx", decoder.decode(data), data)
        except Exception as exc:
            with self.lock:
                if self.device is device:
                    self.last_error = str(exc)
                    self.activity.emit(self.id, "error", str(exc))
        finally:
            with self.lock:
                if self.device is device:
                    self.device = None
                device.close()
                self.resources.release(device.port, self.id)

    def disconnect(self):
        with self.lock:
            device, worker = self.device, self.worker
            self.device = None
            if device:
                device.close()
        if worker and worker is not threading.current_thread():
            worker.join(3)
        if device:
            self.resources.release(device.port, self.id)
        return self.status()

    def send(self, text="", hex_mode=False, newline="CRLF"):
        endings = {"CRLF": "\r\n", "LF": "\n", "CR": "\r", "NONE": ""}
        if newline not in endings:
            raise ValueError("无效的结尾选项")
        with self.lock:
            if not self.device:
                raise ValueError("串口尚未连接")
            data = bytes.fromhex(text) if hex_mode else (text + endings[newline]).encode(self.encoding)
            sent = self.device.write(data)
            self.tx += sent
            self.activity.emit(self.id, "tx", data.decode(self.encoding, errors="replace"), data)
            if sent != len(data):
                raise IOError(f"仅发送 {sent}/{len(data)} 字节")
            return dict(sent=sent)

    def close(self):
        self.disconnect()
