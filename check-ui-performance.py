"""Mapped, off-screen offline UI stress: log traffic, view switching, zoom and GC."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
from unittest.mock import patch

import desktop


def main():
    ticks,delays,requests=[],[],[]
    serial=0
    started=time.perf_counter()
    cpu=time.process_time()
    original=tk.Tk
    wave=dict(input="synthetic-stress.sr",total_samples=1000000,samplerate=10000000,
        start_sample=0,sample_count=1000000,bin_samples=1000,exact=False,
        channels=[dict(name=f"D{i}",ranges=[[0,1] if n%5 else [n%2,n%2] for n in range(1000)]) for i in range(8)])
    def request(method,args=None):
        nonlocal serial
        if method=="settings.get":return {}
        if method=="settings.update":return args["values"]
        if method=="tools":return []
        if method=="status":return dict(components={"serial":{"connected":False},"beken":{"state":"idle"},"slogic":{"state":"idle"}})
        if method=="events":
            page=[dict(id=serial+i,component="serial",kind="rx",text="stress log "*20+"\n",base64="",time="2026-11-11T00:00:00") for i in range(160)]
            serial+=160
            return dict(events=page,cursor=serial,dropped=False)
        if method=="call":
            requests.append(args["target"])
            if args["target"]=="slogic.waveform":return wave
            if args["target"]=="slogic.status":return dict(id="synthetic",state="succeeded",kind="capture",output="synthetic-stress.sr",finished=1)
            return []
        raise ValueError(method)
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    class Root(original):
        def __init__(self):
            super().__init__()
            self.after(50,lambda:self.geometry("1200x800+4000+100"))
            self.after(50,self.beat)
            for at,caption in ((400,"Beken 烧录"),(800,"串口监控"),(1400,"逻辑分析"),(2100,"放大 +"),(2600,"缩小 −"),
                               (3200,"串口监控"),(4000,"逻辑分析"),(4600,"放大 +"),(5400,"串口监控"),(6600,"Beken 烧录"),(7200,"串口监控"),(8800,"逻辑分析")):
                self.after(at,lambda text=caption:self.click(text))
            self.after(12000,lambda:self.tk.call(self.protocol("WM_DELETE_WINDOW")))
        def beat(self):
            ticks.append(time.perf_counter())
            self.after(20,self.beat)
        def click(self,caption):
            target=next(w for w in descendants(self) if isinstance(w,tk.Button) and caption in w.cget("text"))
            then=time.perf_counter()
            target.invoke()
            delays.append(time.perf_counter()-then)
    directory=Path(__file__).parent/"build/test-artifacts"
    directory.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary,patch.object(tk,"Tk",Root):
        desktop.launch(request,lambda:None,Path(temporary))
    class Memory(ctypes.Structure):
        _fields_=[("cb",wintypes.DWORD),("faults",wintypes.DWORD),*( (name,ctypes.c_size_t) for name in
            ("peak_working","working","peak_pool_paged","pool_paged","peak_pool_nonpaged","pool_nonpaged","pagefile","peak_pagefile"))]
    memory=Memory()
    memory.cb=ctypes.sizeof(memory)
    ctypes.windll.kernel32.GetCurrentProcess.restype=wintypes.HANDLE
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.c_void_p,wintypes.DWORD]
    assert ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(),ctypes.byref(memory),ctypes.sizeof(memory))
    elapsed=time.perf_counter()-started
    gaps=[b-a for a,b in zip(ticks,ticks[1:])]
    result=dict(duration_s=round(elapsed,2),heartbeat_ticks=len(ticks),max_heartbeat_gap_ms=round(max(gaps)*1000,2),
        max_click_ms=round(max(delays)*1000,2),cpu_single_core_percent=round((time.process_time()-cpu)/elapsed*100,2),
        cpu_host_percent=round((time.process_time()-cpu)/elapsed*100/os.cpu_count(),2),logical_cpus=os.cpu_count(),
        peak_working_mb=round(memory.peak_working/1024**2,2),remaining_threads=threading.active_count(),hardware_capture=False)
    assert not any(x=="slogic.start" for x in requests)
    assert result["max_heartbeat_gap_ms"]<350,result
    assert result["max_click_ms"]<250,result
    print(json.dumps(result))
    (Path(__file__).parent/"build/ui-performance.json").write_text(json.dumps(result,indent=2),encoding="utf-8")


if __name__=="__main__":main()
