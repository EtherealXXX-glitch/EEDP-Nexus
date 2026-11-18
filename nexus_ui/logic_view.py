"""Human-facing waveform viewer over the same SLogic component used by Agents."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, font as tkfont
from nexus_core.app_paths import ROOT
from nexus_ui.wave_cache import WaveCache


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
    label(top, "逻辑分析仪", font=("Microsoft YaHei UI", 12, "bold")).pack(side="left", padx=14, pady=8)
    label(top, "SLogic Combo8", muted=True).pack(side="left", padx=12)
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
    trigger = tk.StringVar(value="")
    state = dict(path="", data=None, start=0, count=0, total=0, request=0, pending=None, closed=False, task=None, last_status=None,
                 wave_busy=False,wave_requested=False,needs_wave=False)
    state.update(cache=WaveCache(),local_pending=None,markers=[],drag=None,height_scale=0.7,channel_names={})
    colors = ["#63dcf2", "#6fa7ff", "#65d5a9", "#e8c56b", "#b69dff", "#f18d97", "#93d6ce", "#dfb1e9"]
    marker_colors = ["#ffc86b", "#63dcf2", "#f18d97", "#65d5a9", "#b69dff", "#ff9d5c"]
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
    def edit_channel_names():
        dialog=tk.Toplevel(window)
        dialog.title("通道名称")
        dialog.transient(window)
        dialog.configure(bg="#252830")
        label(dialog,"通道名称",font=("Microsoft YaHei UI",11,"bold")).grid(row=0,column=0,columnspan=2,sticky="w",padx=16,pady=(12,8))
        names=[]
        for index in range(8):
            key=f"D{index}"
            label(dialog,key,muted=True).grid(row=index+1,column=0,sticky="w",padx=(16,12),pady=3)
            variable=tk.StringVar(value=state["channel_names"].get(key,""))
            names.append(variable)
            tk.Entry(dialog,textvariable=variable,width=20,bg="#30343e",fg="#e3e6ed",insertbackground="#e3e6ed",relief="flat").grid(row=index+1,column=1,sticky="ew",padx=(0,16),pady=3,ipady=3)
        def save():
            values={f"D{i}":value.get().strip() for i,value in enumerate(names)}
            if any(len(value)>12 or "\n" in value or "\r" in value for value in values.values()):
                messagebox.showerror("通道名称","名称最多 12 个字符。",parent=dialog)
                return
            state["channel_names"]={key:value for key,value in values.items() if value}
            draw()
            background_request("settings.update",{"scope":"slogic.display","values":{"channel_names":state["channel_names"]}},
                               lambda value:None,lambda error:failed("通道名称保存失败："+str(error)))
            dialog.destroy()
        actions=frame(dialog)
        actions.grid(row=9,column=0,columnspan=2,sticky="ew",padx=16,pady=12)
        button(actions,"保存",save,primary=True,small=True).pack(side="left")
        button(actions,"取消",dialog.destroy,small=True).pack(side="right")
        dialog.columnconfigure(1,weight=1)
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
    toolbar = frame(right, bg="#20232b")
    toolbar.grid(row=0,column=0,sticky="ew",padx=12,pady=6)
    toolbar_rows=[frame(toolbar,bg="#20232b") for _ in range(5)]
    files = frame(toolbar, bg="#20232b")
    timeline = frame(toolbar, bg="#20232b")
    heights = frame(toolbar, bg="#20232b")
    markers = frame(toolbar, bg="#20232b")
    channels_tool = frame(toolbar, bg="#20232b")
    groups=(files,timeline,heights,markers,channels_tool)
    def open_file():
        path=filedialog.askopenfilename(parent=window,filetypes=[("sigrok 波形","*.sr")])
        if path: load_file(path)
    button(files, "打开 .sr", open_file, small=True).pack(side="left")
    def demo():
        path=ROOT/"plugins/slogic/samples/synthetic-uart-100000.sr"
        if not path.is_file():
            failed("示例文件缺失，请安装完整组件包")
            return
        load_file(str(path))
        path_label.configure(text="离线示例 · UART 100000（非设备实采）")
    button(files,"示例波形",demo,small=True).pack(side="left",padx=(4,0))
    def zoom(factor, anchor=.5):
        if not state["data"]: return
        old_count=state["count"] or state["data"]["sample_count"]
        count=max(1,min(state["total"],max(16,int(old_count*factor))))
        state["start"]=max(0,min(state["total"]-count,int(state["start"]+old_count*anchor-count*anchor)))
        state["count"]=count
        request_wave()
    def full():
        state.update(start=0,count=0)
        request_wave()
    button(timeline,"全览",full,small=True).pack(side="left")
    def change_height(factor):
        state["height_scale"]=max(.3,min(1.0,state["height_scale"]*factor))
        draw()
    button(heights,"高度 +",lambda:change_height(1.2),small=True).pack(side="left",padx=(0,4))
    button(heights,"高度 −",lambda:change_height(1/1.2),small=True).pack(side="left")
    def add_marker():
        if not state["data"]:
            status.configure(text="请先打开波形")
            return
        if len(state["markers"])>=6:
            status.configure(text="最多添加 6 条标尺；右键标尺可删除")
            return
        data=state["data"]
        fraction=.35+len(state["markers"])*.06
        sample=min(state["total"]-1,round(data["start_sample"]+fraction*data["sample_count"]))
        used={marker["color"] for marker in state["markers"]}
        color=next(index for index in range(6) if index not in used)
        state["markers"].append(dict(sample=sample,color=color))
        draw()
    button(markers,"添加标尺",add_marker,small=True).pack(side="left",padx=(0,4))
    def clear_markers():
        state["markers"].clear()
        draw()
    button(markers,"清除标尺",clear_markers,small=True).pack(side="left")
    button(channels_tool,"通道名称",edit_channel_names,small=True).pack(side="left")
    layout={"rows":None}
    def arrange_toolbar(event=None):
        available=max(1,toolbar.winfo_width())
        rows=[]
        current=[]
        used=0
        for group in groups:
            width=group.winfo_reqwidth()
            if current and used+12+width>available:
                rows.append(current)
                current=[]
                used=0
            used+=width+(12 if current else 0)
            current.append(group)
        if current:rows.append(current)
        arrangement=tuple(tuple(groups.index(group) for group in row) for row in rows)
        if layout["rows"]==arrangement:return
        layout["rows"]=arrangement
        for group in groups:group.pack_forget()
        for row in toolbar_rows:row.pack_forget()
        for index,row_groups in enumerate(rows):
            row=toolbar_rows[index]
            row.pack(fill="x",pady=(4 if index else 0,0))
            for position,group in enumerate(row_groups):
                group.pack(in_=row,side="left",padx=(12 if position else 0,0))
    toolbar.bind("<Configure>",arrange_toolbar,add="+")
    toolbar.after_idle(arrange_toolbar)
    canvas=tk.Canvas(right,bg="#171c25",highlightthickness=1,highlightbackground="#393e49",height=400)
    canvas.grid(row=1,column=0,sticky="nsew",padx=12)
    scroll=ttk.Scrollbar(right,orient="horizontal")
    scroll.grid(row=2,column=0,sticky="ew",padx=12,pady=6)
    footer=frame(right,bg="#20232b")
    footer.grid(row=3,column=0,sticky="ew",padx=12)
    ruler=label(footer,"滚轮平移 · Ctrl+滚轮缩放 · 左键拖动 · 右键删除标尺",muted=True)
    ruler.pack(side="left")
    path_label=label(footer,"尚无波形",muted=True)
    path_label.pack(side="right",padx=(12,0))
    channel_font=tkfont.Font(root=window,family="Consolas",size=10,weight="bold")
    def channel_title(channel):
        name=channel["name"]
        custom=state["channel_names"].get(name,"")
        return f"{name} · {custom}" if custom else name
    def plot_geometry():
        channels=(state["data"] or {}).get("channels",[])
        label_width=max((channel_font.measure(channel_title(ch)) for ch in channels),default=38)
        left=max(62,min(200,label_width+22,max(62,canvas.winfo_width()-100)))
        return left,max(1,canvas.winfo_width()-18-left)
    def wave_pixels():
        return max(64,min(2000,plot_geometry()[1]))
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
        left,width=plot_geometry()
        right_edge=left+width
        top=42
        row=max(34,min(64,(canvas.winfo_height()-top-18)/max(1,len(data["channels"]))))
        for tick in range(9):
            x=left+width*tick/8
            timestamp=(data["start_sample"]+data["sample_count"]*tick/8)/data["samplerate"]
            canvas.create_line(x,28,x,canvas.winfo_height(),fill="#29313d",dash=(2,5))
            canvas.create_text(x,15,text=format_time(timestamp),fill="#929aaa",font=("Consolas",8))
        for index,channel in enumerate(data["channels"]):
            y=top+index*row
            center=y+row/2
            amplitude=max(3,(row-18)*state["height_scale"]/2)
            high,low=center-amplitude,center+amplitude
            color=colors[index%len(colors)]
            canvas.create_text(8,y+row/2,text=channel_title(channel),anchor="w",fill=color,font=channel_font)
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
        for index,marker in enumerate(state["markers"]):
            sample=marker["sample"]
            color=marker_colors[marker["color"]]
            fraction=(sample-data["start_sample"])/data["sample_count"]
            if 0 <= fraction <= 1:
                x=left+width*fraction
                canvas.create_line(x,36,x,canvas.winfo_height(),fill=color,dash=(3,3),tags=("marker","marker-line"))
                canvas.create_polygon(x-7,27,x+7,27,x,36,fill=color,outline="",tags=("marker","marker-flag"))
                canvas.create_text(x+7,27,anchor="nw",text=str(index+1),
                                   fill=color,font=("Consolas",8),tags=("marker","marker-label"))
        scroll.set(data["start_sample"]/data["total_samples"],min(1,(data["start_sample"]+data["sample_count"])/data["total_samples"]))
    def show_cached():
        state["local_pending"]=None
        if not alive():return False
        data,enough=state["cache"].window(state["start"],state["count"],wave_pixels())
        if data:
            state.update(data=data,total=data["total_samples"],start=data["start_sample"],count=data["sample_count"])
            detail="正在加载细节" if not enough else ("逐采样显示" if data["exact"] else "活动包络，放大可见边沿")
            status.configure(text=f"{data['samplerate']:,.0f} Hz · {data['total_samples']:,} 点 · 当前窗口 {format_time(data['sample_count']/data['samplerate'])} · "+detail)
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
            _,enough=state["cache"].window(state["start"],state["count"],wave_pixels())
            if enough:return
            if state["wave_busy"]:
                state["wave_requested"]=True
                return
            state["wave_busy"]=True
            state["wave_requested"]=False
            requested_path=state["path"]
            args=dict(input=state["path"],start_sample=state["start"],sample_count=state["count"],pixels=wave_pixels())
            def loaded(data):
                state["wave_busy"]=False
                if requested_path==state["path"]:
                    state["cache"].add(data)
                    if state["total"]==0:state["total"]=data["total_samples"]
                    enough=show_cached()
                    moved=(state["start"],state["count"],wave_pixels()) != (args["start_sample"],args["sample_count"],args["pixels"])
                    if not enough and moved: state["wave_requested"]=True
                    elif not enough: status.configure(text="波形细节暂不可用，请重新打开文件")
                if state["wave_requested"]: request_wave()
            def wave_failed(error):
                state["wave_busy"]=False
                failed(error)
                if state["wave_requested"]: request_wave()
            call("waveform",args,loaded,wave_failed)
        state["pending"]=window.after(24,request)
    def load_file(path):
        state.update(path=path,start=0,count=0,total=0,data=None,cache=WaveCache(),markers=[],drag=None)
        path_label.configure(text=Path(path).name)
        request_wave()
    def scrolled(operation,value,units=None):
        if not state["data"]: return
        if operation=="moveto": start=int(float(value)*state["total"])
        else: start=state["start"]+int(value)*max(1,state["count"]//(10 if units=="units" else 1))
        state["start"]=max(0,min(state["total"]-state["count"],start))
        request_wave()
    scroll.configure(command=scrolled)
    def resized(event):
        draw()
        if state["data"]:request_wave()
    canvas.bind("<Configure>",resized)
    window.bind("<Map>",lambda event:request_wave() if event.widget==window and state["needs_wave"] else None,add="+")
    def fraction_at(x):
        left,width=plot_geometry()
        return max(0, min(1, (x-left)/width))
    def marker_at(x):
        data=state["data"]
        if not data: return None
        left,width=plot_geometry()
        for index,marker in enumerate(state["markers"]):
            sample=marker["sample"]
            position=left+(sample-data["start_sample"])*width/data["sample_count"]
            if left <= position <= left+width and abs(position-x)<=8:
                return index
        return None
    def sample_at(x):
        data=state["data"]
        return min(state["total"]-1,max(0,round(data["start_sample"]+fraction_at(x)*data["sample_count"])))
    def show_marker_time(index):
        marker=state["markers"][index]
        timestamp=marker["sample"]/state["data"]["samplerate"]
        status.configure(text=f"标尺 {index+1} · {format_time(timestamp)}")
    def hover(event):
        index=marker_at(event.x)
        if index is not None: show_marker_time(index)
    def wheel(event):
        if not event.delta: return "break"
        if event.state & 0x4:
            zoom(.5 if event.delta>0 else 2,fraction_at(event.x))
        else:
            scrolled("scroll",-1 if event.delta>0 else 1,"units")
        return "break"
    def press(event):
        if not state["data"]: return
        state["drag"]=dict(x=event.x,start=state["start"],marker=marker_at(event.x),moved=False)
        if state["drag"]["marker"] is not None: show_marker_time(state["drag"]["marker"])
    def drag(event):
        gesture=state["drag"]
        if not gesture or not state["data"]: return
        if abs(event.x-gesture["x"])>=3: gesture["moved"]=True
        if not gesture["moved"]: return
        if gesture["marker"] is not None:
            state["markers"][gesture["marker"]]["sample"]=sample_at(event.x)
            draw()
            show_marker_time(gesture["marker"])
        else:
            delta=int((event.x-gesture["x"])*state["count"]/plot_geometry()[1])
            state["start"]=max(0,min(state["total"]-state["count"],gesture["start"]-delta))
            request_wave()
    def release(event):
        state["drag"]=None
    def remove_marker(event):
        index=marker_at(event.x)
        if index is not None:
            state["markers"].pop(index)
            draw()
    canvas.bind("<MouseWheel>",wheel)
    canvas.bind("<Motion>",hover)
    canvas.bind("<ButtonPress-1>",press)
    canvas.bind("<B1-Motion>",drag)
    canvas.bind("<ButtonRelease-1>",release)
    canvas.bind("<Button-3>",remove_marker)
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
    def side_wheel(event):
        if event.delta:
            side_canvas.yview_scroll(-1 if event.delta>0 else 1,"units")
        return "break"
    def bind_side_wheel(widget):
        widget.bind("<MouseWheel>",side_wheel,add="+")
        for child in widget.winfo_children():
            bind_side_wheel(child)
    bind_side_wheel(side)
    def preferences(saved):
        if not alive(): return
        capture=saved.get("start",saved.get("inspect",{}))
        for key,variable in (("device",device),("samplerate",rate),("duration_ms",duration),("trigger",trigger)):
            if key in capture: variable.set(str(capture[key]))
        if "channels" in capture:
            selected=set(capture["channels"].split(","))
            for index,var in enumerate(enabled): var.set(f"D{index}" in selected)
    background_request("settings.get",{"scope":"component.slogic"},lambda value:preferences(value) if alive() else None,lambda error:None)
    def display_preferences(saved):
        names=saved.get("channel_names",{})
        if not isinstance(names,dict): return
        state["channel_names"]={f"D{i}":names[f"D{i}"] for i in range(8)
                                if isinstance(names.get(f"D{i}"),str) and len(names[f"D{i}"])<=12}
        draw()
    background_request("settings.get",{"scope":"slogic.display"},lambda value:display_preferences(value) if alive() else None,lambda error:None)
    draw()
    return window
