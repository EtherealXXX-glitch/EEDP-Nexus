"""Human-facing waveform viewer over the same SLogic component used by Agents."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from app_paths import ROOT
from wave_cache import WaveCache


def open_logic_view(root, background_request, frame, label, button, embedded=False):
    window = tk.Frame(root) if embedded else tk.Toplevel(root)
    if not embedded:
        window.title("EEDP Nexus · 逻辑分析仪")
        window.geometry("1240x820")
        window.minsize(1000, 700)
    window.configure(bg="#20232b")
    window.rowconfigure(1, weight=1)
    window.columnconfigure(1, weight=1)
    top = frame(window, bg="#1c2029")
    top.grid(row=0, column=0, columnspan=2, sticky="ew")
    label(top, "逻辑分析仪", font=("Microsoft YaHei UI", 13, "bold")).pack(side="left", padx=16, pady=12)
    label(top, "SLogic Combo8 · 同一采集文件，人与 Agent 共享", muted=True).pack(side="left", padx=12)
    side_container = frame(window)
    side_container.grid(row=1, column=0, sticky="ns", padx=(0, 1))
    side_canvas = tk.Canvas(side_container, width=285, bg="#252830", highlightthickness=0)
    side_scroll = ttk.Scrollbar(side_container, orient="vertical", command=side_canvas.yview)
    side_scroll.pack(side="right", fill="y")
    side_canvas.pack(side="left", fill="both", expand=True)
    side_canvas.configure(yscrollcommand=side_scroll.set)
    side = frame(side_canvas)
    side_window = side_canvas.create_window(0, 0, window=side, anchor="nw")
    side.bind("<Configure>", lambda event:side_canvas.configure(scrollregion=side_canvas.bbox("all")))
    side_canvas.bind("<Configure>", lambda event:side_canvas.itemconfigure(side_window,width=event.width))
    right = frame(window, bg="#20232b")
    right.grid(row=1, column=1, sticky="nsew")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)
    status = label(window, "等待连接；查看波形不会重新采样", muted=True)
    status.grid(row=2, column=0, columnspan=2, sticky="ew", padx=14, pady=8)
    device, rate, duration = tk.StringVar(value="sipeed-slogic-analyzer"), tk.StringVar(value="10000000"), tk.StringVar(value="100")
    trigger, decoder = tk.StringVar(value=""), tk.StringVar(value="uart:rx=D0:baudrate=115200")
    state = dict(path="", data=None, start=0, count=0, total=0, request=0, pending=None, closed=False, task=None, last_status=None,
                 wave_busy=False,wave_requested=False,needs_wave=False)
    state.update(cache=WaveCache(),local_pending=None)
    colors = ["#63dcf2", "#6fa7ff", "#65d5a9", "#e8c56b", "#b69dff", "#f18d97", "#93d6ce", "#dfb1e9"]
    def alive(): return not state["closed"] and bool(window.winfo_exists())
    def failed(error):
        if alive(): status.configure(text="操作失败："+str(error))
    def call(action, args, done, failure=None):
        background_request("call", {"target":"slogic."+action,"arguments":args}, lambda value: done(value) if alive() else None,
                           lambda error:(failure or failed)(error) if alive() else None)
    label(side, "采集设置", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=14, pady=12)
    def parameter(caption, variable, choices=None):
        label(side, caption, muted=True, wraplength=250, justify="left").pack(anchor="w", padx=14, pady=(6, 3))
        widget = ttk.Combobox(side, textvariable=variable, values=choices or [], width=25) if choices is not None else tk.Entry(side, textvariable=variable, bg="#30343e", fg="#e3e6ed", insertbackground="#e3e6ed", width=27, relief="flat")
        widget.pack(fill="x", padx=14, ipady=4)
        return widget
    device_box = parameter("设备标识", device, [])
    def discovered(value):
        devices = value["devices"]
        device_box.configure(values=[x["spec"] for x in devices])
        if len(devices)==1:
            device.set(devices[0]["spec"])
            status.configure(text=devices[0]["description"])
            call("capabilities", {"device":device.get()}, capabilities)
        else: status.configure(text=f"发现 {len(devices)} 台设备，请选择目标")
    button(side, "扫描设备", lambda:call("devices", {}, discovered), small=True).pack(fill="x", padx=14, pady=6)
    rates = parameter("采样率 Hz", rate, [1000000, 2000000, 5000000, 10000000, 20000000])
    def capabilities(value):
        rates.configure(values=value["samplerates"])
        if int(rate.get()) not in value["samplerates"] and value["samplerates"]: rate.set(str(value["samplerates"][0]))
    parameter("采样时长 ms", duration)
    voltage = tk.StringVar(value="")
    grounded = tk.BooleanVar(value=False)
    parameter("已确认的信号电压 V（未知请留空）", voltage)
    tk.Checkbutton(side, text="已确认信号与分析仪共地", variable=grounded, fg="#e3e6ed", bg="#252830", selectcolor="#30343e").pack(anchor="w", padx=14, pady=6)
    label(side, "启用通道", muted=True).pack(anchor="w", padx=14, pady=(12, 3))
    channels = frame(side)
    channels.pack(fill="x", padx=14)
    enabled = []
    for number in range(8):
        var = tk.BooleanVar(value=number==0)
        enabled.append(var)
        tk.Checkbutton(channels, text=f"D{number}", variable=var, fg=colors[number], bg="#252830", selectcolor="#30343e", activebackground="#252830").grid(row=number//4, column=number%4, sticky="w")
    parameter("触发条件（留空立即采集）", trigger, ["", *[f"D{i}=r" for i in range(8)], *[f"D{i}=f" for i in range(8)]])
    def arguments():
        return dict(device=device.get(), channels=",".join(f"D{i}" for i,var in enumerate(enabled) if var.get()),
                    samplerate=int(rate.get()), duration_ms=int(duration.get()), trigger=trigger.get(),
                    timeout_s=max(30, int(duration.get())//1000+5))
    def start():
        try:
            args=arguments()
            verified_voltage=float(voltage.get())
        except ValueError:
            failed("请填写采样率、时长及已确认的信号电压，未知电压不能采样")
            return
        if not 0 < verified_voltage <= 3.6 or not grounded.get():
            failed("仅支持已确认 0–3.6V 且共地的信号")
            return
        def checked(plan):
            if not messagebox.askyesno("确认开始采集", f"通道 {args['channels']} · {args['samplerate']:,} Hz · {args['duration_ms']} ms\n\n已确认信号在 0–3.6V 范围并已共地？", parent=window): return
            call("start", {**args,"signal_voltage":verified_voltage,"common_ground":grounded.get()}, task_started)
        status.configure(text="预检设备与采样范围…")
        call("inspect", args, checked)
    capture_actions=frame(side_container)
    side_scroll.pack_forget()
    side_canvas.pack_forget()
    capture_actions.pack(side="bottom",fill="x")
    side_scroll.pack(side="right",fill="y")
    side_canvas.pack(side="left",fill="both",expand=True)
    button(capture_actions, "开始采集", start, primary=True).pack(fill="x", padx=14, pady=(10, 6))
    button(capture_actions, "停止当前任务", lambda:call("cancel", {}, task_started)).pack(fill="x", padx=14,pady=(0,10))
    label(side, "任务在后台运行，关窗口不会取消。\n缩放和平移只读已有文件。", muted=True, justify="left").pack(anchor="w", padx=14, pady=12)
    def decode():
        if not state["path"]:
            failed("请先采集或打开 .sr 文件")
            return
        call("decode", {"input":state["path"],"decoder":decoder.get()}, task_started)
    tools = frame(right, bg="#20232b")
    tools.grid(row=0,column=0,sticky="ew",padx=12,pady=8)
    def open_file():
        path=filedialog.askopenfilename(parent=window,filetypes=[("sigrok 波形","*.sr")])
        if path: load_file(path)
    button(tools, "打开 .sr", open_file, small=True).pack(side="left")
    def demo():
        path=ROOT/"plugins/slogic/samples/synthetic-uart-100000.sr"
        if not path.is_file():
            failed("示例文件缺失，请安装完整组件包")
            return
        load_file(str(path))
        path_label.configure(text="离线示例 · UART 100000（非设备实采）")
    button(tools,"示例波形",demo,small=True).pack(side="left",padx=4)
    def zoom(factor, anchor=.5):
        if not state["data"]: return
        old_count=state["count"] or state["data"]["sample_count"]
        count=max(1,min(state["total"],max(16,int(old_count*factor))))
        state["start"]=max(0,min(state["total"]-count,int(state["start"]+old_count*anchor-count*anchor)))
        state["count"]=count
        request_wave()
    button(tools,"放大 +",lambda:zoom(.5),small=True).pack(side="left",padx=4)
    button(tools,"缩小 −",lambda:zoom(2),small=True).pack(side="left")
    def full():
        state.update(start=0,count=0)
        request_wave()
    button(tools,"全览",full,small=True).pack(side="left",padx=4)
    path_label=label(tools,"尚无波形",muted=True)
    path_label.pack(side="left",padx=12)
    canvas=tk.Canvas(right,bg="#171c25",highlightthickness=1,highlightbackground="#393e49",height=400)
    canvas.grid(row=1,column=0,sticky="nsew",padx=12)
    scroll=ttk.Scrollbar(right,orient="horizontal")
    scroll.grid(row=2,column=0,sticky="ew",padx=12,pady=6)
    ruler=label(right,"滚轮缩放 · 横向滚动条平移 · 点击读取时间；色带表示桶内发生电平变化，放大可看边沿。",muted=True)
    ruler.grid(row=3,column=0,sticky="ew",padx=12)
    decode_tools=frame(right,bg="#20232b")
    decode_tools.grid(row=4,column=0,sticky="ew",padx=12,pady=(8,0))
    label(decode_tools,"协议 / 引脚映射",muted=True).pack(side="left",padx=(0,8))
    ttk.Combobox(decode_tools,textvariable=decoder,values=["uart:rx=D0:baudrate=115200","i2c:scl=D0:sda=D1","spi:clk=D0:mosi=D1:cs=D2"]).pack(side="left",fill="x",expand=True)
    button(decode_tools,"解码当前波形",decode,small=True).pack(side="right",padx=(8,0))
    annotations=tk.Text(right,height=7,bg="#23252b",fg="#e3e6ed",font=("Consolas",10),wrap="word",state="disabled")
    annotations.grid(row=5,column=0,sticky="ew",padx=12,pady=10)
    def format_time(seconds):
        if abs(seconds)<.001: return f"{seconds*1e6:.2f} µs"
        if abs(seconds)<1: return f"{seconds*1e3:.2f} ms"
        return f"{seconds:.3f} s"
    def draw(_=None):
        canvas.delete("all")
        data=state["data"]
        if not data:
            canvas.create_text(canvas.winfo_width()/2,canvas.winfo_height()/2,text="开始有界采集，或打开已有 .sr 波形",fill="#929aaa",font=("Microsoft YaHei UI",12))
            return
        left,right_edge=62,max(90,canvas.winfo_width()-18)
        width=right_edge-left
        top=42
        row=max(34,min(64,(canvas.winfo_height()-top-18)/max(1,len(data["channels"]))))
        for tick in range(9):
            x=left+width*tick/8
            timestamp=(data["start_sample"]+data["sample_count"]*tick/8)/data["samplerate"]
            canvas.create_line(x,28,x,canvas.winfo_height(),fill="#29313d",dash=(2,5))
            canvas.create_text(x,15,text=format_time(timestamp),fill="#929aaa",font=("Consolas",8))
        for index,channel in enumerate(data["channels"]):
            y=top+index*row
            high,low=y+8,y+row-10
            color=colors[index%len(colors)]
            canvas.create_text(12,y+row/2,text=channel["name"],anchor="w",fill=color,font=("Consolas",10,"bold"))
            ranges=channel["ranges"]
            points=[]
            bucket=0
            while bucket < len(ranges):
                minimum,maximum=ranges[bucket]
                stop=bucket+1
                while stop<len(ranges) and ranges[stop]==ranges[bucket]:stop+=1
                offset=data.get("bucket_start_sample",data["start_sample"])-data["start_sample"]
                x=max(left,left+width*(offset+bucket*data["bin_samples"])/data["sample_count"])
                end=min(right_edge,left+width*(offset+stop*data["bin_samples"])/data["sample_count"])
                if minimum!=maximum:
                    if len(points)>=4:canvas.create_line(*points,fill=color,width=2)
                    points=[]
                    canvas.create_rectangle(x,high,end,low,fill=color,outline="",stipple="gray50")
                else:
                    level=high if minimum else low
                    points.extend((x,level,end,level))
                bucket=stop
            if len(points)>=4:canvas.create_line(*points,fill=color,width=2)
        scroll.set(data["start_sample"]/data["total_samples"],min(1,(data["start_sample"]+data["sample_count"])/data["total_samples"]))
    def show_cached():
        state["local_pending"]=None
        if not alive():return False
        data,enough=state["cache"].window(state["start"],state["count"],max(64,canvas.winfo_width()-80))
        if data:
            state.update(data=data,total=data["total_samples"],start=data["start_sample"],count=data["sample_count"])
            status.configure(text=f"{data['samplerate']:,.0f} Hz · {data['total_samples']:,} 点 · 当前窗口 {format_time(data['sample_count']/data['samplerate'])} · "+("逐采样显示" if data["exact"] else "活动包络，放大可见边沿"))
            draw()
        return enough

    def request_wave():
        if not state["path"] or not alive(): return
        if not window.winfo_ismapped():
            state["needs_wave"]=True
            return
        state["needs_wave"]=False
        state["request"]+=1
        if state["local_pending"] is None:state["local_pending"]=window.after(16,show_cached)
        if state["pending"] is not None:return
        def request():
            state["pending"]=None
            _,enough=state["cache"].window(state["start"],state["count"],max(64,canvas.winfo_width()-80))
            if enough:return
            if state["wave_busy"]:
                state["wave_requested"]=True
                return
            state["wave_busy"]=True
            state["wave_requested"]=False
            requested_path=state["path"]
            args=dict(input=state["path"],start_sample=state["start"],sample_count=state["count"],pixels=max(64,min(2000,canvas.winfo_width()-80)))
            def loaded(data):
                state["wave_busy"]=False
                if requested_path==state["path"]:
                    state["cache"].add(data)
                    if state["total"]==0:state["total"]=data["total_samples"]
                    show_cached()
                if state["wave_requested"]: request_wave()
            def wave_failed(error):
                state["wave_busy"]=False
                failed(error)
                if state["wave_requested"]: request_wave()
            call("waveform",args,loaded,wave_failed)
        state["pending"]=window.after(24,request)
    def load_file(path):
        state.update(path=path,start=0,count=0,total=0,data=None,cache=WaveCache())
        path_label.configure(text=Path(path).name)
        request_wave()
    def scrolled(operation,value,units=None):
        if not state["data"]: return
        if operation=="moveto": start=int(float(value)*state["total"])
        else: start=state["start"]+int(value)*max(1,state["count"]//(10 if units=="units" else 1))
        state["start"]=max(0,min(state["total"]-state["count"],start))
        request_wave()
    scroll.configure(command=scrolled)
    canvas.bind("<Configure>",draw)
    window.bind("<Map>",lambda event:request_wave() if event.widget==window and state["needs_wave"] else None,add="+")
    canvas.bind("<MouseWheel>",lambda event:zoom(.5 if event.delta>0 else 2,max(0,min(1,(event.x-62)/max(1,canvas.winfo_width()-80)))))
    def cursor(event):
        data=state["data"]
        if not data: return
        fraction=max(0,min(1,(event.x-62)/max(1,canvas.winfo_width()-80)))
        timestamp=(data["start_sample"]+fraction*data["sample_count"])/data["samplerate"]
        canvas.delete("cursor")
        canvas.create_line(event.x,28,event.x,canvas.winfo_height(),fill="white",dash=(3,3),tags="cursor")
        ruler.configure(text="游标时间："+format_time(timestamp)+" · 滚轮缩放，拖动下方滚动条平移")
    canvas.bind("<Button-1>",cursor)
    def task_started(value):
        state["task"]=value.get("id")
        poll_result(value)
    def poll_result(value):
        if value.get("state")=="running":
            status.configure(text=value.get("stage","处理中")+" · 后台任务运行中（不显示估算百分比）")
            if not embedded: window.after(400,lambda:call("status",{},poll_result) if alive() else None)
            return
        if value.get("state")=="succeeded":
            if value.get("kind")=="capture": load_file(value["output"])
            elif value.get("kind")=="decode":
                annotations.configure(state="normal")
                annotations.delete("1.0","end")
                annotations.insert("end",value.get("preview","") or "解码完成，但没有产生注释；请核对协议、接线和参数。")
                annotations.configure(state="disabled")
            status.configure(text=value.get("stage","")+" · "+value.get("output",""))
        elif value.get("state") not in ("idle",None): status.configure(text=value.get("stage","任务结束"))
    def attach(value):
        signature=(value.get("id"),value.get("state"),value.get("finished"))
        if signature==state["last_status"]: return
        state["last_status"]=signature
        if value.get("kind")=="decode" and not state["path"] and "-i" in value.get("command",[]):
            source=value["command"][value["command"].index("-i")+1]
            if Path(source).is_file(): load_file(source)
        poll_result(value)
    def close():
        state["closed"]=True
        for key in ("pending","local_pending"):
            if state[key]:window.after_cancel(state[key]);state[key]=None
        window.destroy()
    if not embedded: window.protocol("WM_DELETE_WINDOW",close)
    else:
        def destroyed(event):
            if event.widget!=window:return
            state["closed"]=True
            for key in ("pending","local_pending"):
                if state[key]:window.after_cancel(state[key]);state[key]=None
        window.bind("<Destroy>",destroyed)
    call("status",{},attach)
    window.consume_status=attach
    window.open_waveform=open_file
    window.scan_devices=lambda:call("devices",{},discovered)
    window.on_theme_changed=draw
    def preferences(saved):
        if not alive(): return
        capture=saved.get("start",saved.get("inspect",{}))
        for key,variable in (("device",device),("samplerate",rate),("duration_ms",duration),("trigger",trigger)):
            if key in capture: variable.set(str(capture[key]))
        if "channels" in capture:
            selected=set(capture["channels"].split(","))
            for index,var in enumerate(enabled): var.set(f"D{index}" in selected)
        if saved.get("decode",{}).get("decoder"): decoder.set(saved["decode"]["decoder"])
    background_request("settings.get",{"scope":"component.slogic"},lambda value:preferences(value) if alive() else None,lambda error:None)
    draw()
    return window
