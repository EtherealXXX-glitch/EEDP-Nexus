"""Bounded numeric samples for the data waveform workspace."""
from collections import deque
import math
import re
from core import field

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,31}\Z")
PREFIX = "@plot "
MAX_CHANNELS = 16
MAX_POINTS = 5000
MAX_LINE = 2048


def parse_line(line):
    """Parse one complete, explicitly marked sample; ignore unrelated text."""
    if not line.startswith(PREFIX):
        return None
    values = {}
    parts = line[len(PREFIX):].split(",")
    if len(parts) > MAX_CHANNELS:
        raise ValueError("最多支持 16 个通道")
    for part in parts:
        name, separator, value = part.strip().partition("=")
        name = name.strip()
        if not separator or not NAME.fullmatch(name) or name in values:
            raise ValueError("通道名称或数据格式无效")
        try:
            number = float(value.strip())
        except ValueError:
            raise ValueError("通道值必须是数字") from None
        if not math.isfinite(number) or abs(number)>1e100:
            raise ValueError("通道值超出支持范围")
        values[name] = number
    if not values:
        raise ValueError("没有通道数据")
    return values


class Plot:
    id = "plot"
    name = "数据波形"
    description = "按约定格式接收数值并保留有界波形数据，不直接访问设备。"
    actions = {
        "status": dict(label="波形状态", read_only=True, destructive=False, fields=[]),
        "feed": dict(label="输入波形文本", read_only=False, destructive=False,
                     fields=[field("text", "波形文本", "", remember=False),
                             field("reset_stream", "丢弃未完成的行", False, kind="bool", remember=False)]),
        "samples": dict(label="读取波形数据", read_only=True, destructive=False, log_result="omit",
                        fields=[field("limit", "最多返回点数", 500, kind="int", remember=False)]),
        "clear": dict(label="清除波形", read_only=False, destructive=False, fields=[]),
    }

    def __init__(self, activity, resources):
        self.activity = activity
        self.samples_buffer = deque(maxlen=MAX_POINTS)
        self.pending = ""
        self.sequence = 0
        self.rejected = 0
        self.channels = set()

    def status(self):
        return dict(state="idle", points=len(self.samples_buffer), rejected=self.rejected)

    def feed(self, text="", reset_stream=False):
        if len(text) > 65536:
            raise ValueError("单次输入不能超过 65536 字符")
        if reset_stream:
            self.pending = ""
        self.pending += text
        lines = self.pending.split("\n")
        self.pending = lines.pop()
        if len(self.pending) > MAX_LINE:
            self.pending = ""
            self.rejected += 1
        accepted = 0
        for line in lines:
            line = line.rstrip("\r")
            try:
                if len(line) > MAX_LINE:
                    raise ValueError("数据行过长")
                values = parse_line(line)
            except ValueError:
                self.rejected += 1
                continue
            if values is not None:
                names=self.channels | values.keys()
                if len(names)>MAX_CHANNELS:
                    self.rejected += 1
                    continue
                self.channels=names
                self.sequence += 1
                self.samples_buffer.append(dict(index=self.sequence, values=values))
                accepted += 1
        return dict(accepted=accepted, rejected=self.rejected)

    def samples(self, limit=500):
        if not 1 <= limit <= MAX_POINTS:
            raise ValueError("返回点数须为 1–5000")
        return dict(points=list(self.samples_buffer)[-limit:])

    def clear(self):
        self.samples_buffer.clear()
        self.pending = ""
        self.rejected = 0
        self.channels.clear()
        return self.status()

    def close(self):
        pass
