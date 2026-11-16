"""Embedded video workspace; media decoding remains in the video component."""
import tkinter as tk
from tkinter import filedialog, ttk


def open_video_view(parent, background_request, frame, label, button):
    view = frame(parent)
    view.columnconfigure(0, weight=1)
    view.rowconfigure(1, weight=1)
    controls = frame(view)
    controls.grid(row=0, column=0, sticky="ew", padx=16, pady=12)
    controls.columnconfigure(1, weight=1)
    source = tk.StringVar()
    form = tk.StringVar(value="自动检测")
    formats = {"自动检测": "auto", "H.264 裸流": "h264", "MJPEG 裸流": "mjpeg", "MPEG-TS": "mpegts", "原始 YUV": "rawvideo"}
    width, height, pixel, fps = (tk.StringVar(value=x) for x in ("640", "480", "yuv420p", "25"))
    state = tk.StringVar(value="选择文件或输入网络视频地址")
    label(controls, "文件 / 地址").grid(row=0, column=0, sticky="w", padx=(0, 8))
    ttk.Entry(controls, textvariable=source).grid(row=0, column=1, sticky="ew")
    def browse():
        path = filedialog.askopenfilename(parent=view, filetypes=[("视频文件", "*.mp4 *.mkv *.avi *.mov *.ts *.h264 *.264 *.mjpeg *.mjpg *.yuv *.sdp"), ("所有文件", "*.*")])
        if path: source.set(path)
    button(controls, "选择文件", browse, small=True).grid(row=0, column=2, padx=(8, 0))
    options = frame(controls)
    options.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    label(options, "输入格式").pack(side="left", padx=(0, 5))
    ttk.Combobox(options, textvariable=form, values=list(formats), state="readonly", width=12).pack(side="left", padx=(0, 12))
    for caption, var, size in (("宽", width, 5), ("高", height, 5), ("帧率", fps, 4)):
        label(options, caption, muted=True).pack(side="left", padx=(0, 4))
        ttk.Entry(options, textvariable=var, width=size).pack(side="left", padx=(0, 8))
    ttk.Combobox(options, textvariable=pixel, values=["yuv420p", "nv12", "nv21", "yuyv422", "uyvy422", "yuv422p", "yuv444p"], state="readonly", width=10).pack(side="left")
    surface = tk.Frame(view, bg="black", highlightthickness=0)
    surface.grid(row=1, column=0, sticky="nsew", padx=16)
    footer = frame(view)
    footer.grid(row=2, column=0, sticky="ew", padx=16, pady=12)
    def request_action(action, args=None, success=None):
        def ok(result):
            if not view.winfo_exists(): return
            state.set("正在播放" if result.get("playing") and not result.get("paused") else "已暂停" if result.get("paused") else "已停止")
            if success: success(result)
        def failed(error):
            if view.winfo_exists(): state.set(str(error))
        background_request("call", {"target": "video." + action, "arguments": args or {}}, ok, failed)
    def play():
        try:
            args = dict(source=source.get(), format=formats[form.get()], width=int(width.get()), height=int(height.get()), pixel_format=pixel.get(), fps=float(fps.get()))
        except (ValueError, KeyError):
            state.set("请检查视频格式、宽高和帧率")
            return
        request_action("attach", {"window_id": surface.winfo_id()}, lambda _: request_action("play", args))
    button(footer, "播放", play, primary=True).pack(side="left", padx=(0, 8))
    button(footer, "暂停 / 继续", lambda: request_action("pause")).pack(side="left", padx=(0, 8))
    button(footer, "停止", lambda: request_action("stop")).pack(side="left", padx=(0, 12))
    position = tk.StringVar(value="0")
    label(footer, "跳转秒数", muted=True).pack(side="left", padx=(0, 4))
    ttk.Entry(footer, textvariable=position, width=6).pack(side="left")
    def seek():
        try: seconds = float(position.get())
        except ValueError:
            state.set("请输入有效的秒数")
            return
        request_action("seek", {"seconds": seconds})
    button(footer, "跳转", seek, small=True).pack(side="left", padx=(4, 12))
    volume = tk.StringVar(value="80")
    label(footer, "音量", muted=True).pack(side="left", padx=(0, 4))
    ttk.Combobox(footer, textvariable=volume, values=["0", "25", "50", "75", "80", "100"], width=4, state="readonly").pack(side="left")
    def set_volume(_=None): request_action("volume", {"level": int(volume.get())})
    footer.winfo_children()[-1].bind("<<ComboboxSelected>>", set_volume)
    status_label = label(footer, "", muted=True)
    status_label.configure(textvariable=state)
    status_label.pack(side="left", fill="x", expand=True)
    def consume_status(value):
        if value.get("error"): state.set(value["error"])
        elif not value.get("playing") and state.get() in ("正在播放", "已暂停"): state.set("已停止")
    view.consume_status = consume_status
    view.attach_window = lambda: request_action("attach", {"window_id": surface.winfo_id()})
    return view
