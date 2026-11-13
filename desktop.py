"""Desktop client. Device operations remain in independent backend components."""
from __future__ import annotations

import base64
import json
import gc
from collections import deque
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from app_paths import APP_NAME, RESOURCES, FROZEN, CLI_EXE, ROOT
from ui_diagnostics import UIDiagnostics
from log_store import diagnostic_path
from log_center import open_log_center
from plugin_tools import open_plugin_tools
from logic_view import open_logic_view
from themes import ThemeManager
from buttons import ActionButton
from appearance import build_appearance
from component_plans import planned_components

BG = "#20232b"
PANEL = "#252830"
TERMINAL = "#23252b"
FIELD = "#30343e"
BORDER = "#393e49"
TEXT = "#e3e6ed"
MUTED = "#929aaa"
ACCENT = "#54c9ed"
GREEN = "#79d4ac"
RED = "#f18d97"
FONT = ("Microsoft YaHei UI", 10)
SERIAL_BAUDRATES = (110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200,
                   28800, 38400, 56000, 57600, 76800, 96000, 115200, 128000,
                   153600, 230400, 256000, 460800, 500000, 576000, 921600,
                   1000000, 1152000, 1500000, 2000000, 2500000, 3000000,
                   3500000, 4000000, 6000000, 8000000, 12000000)


def _io_worker(request, tasks, results, stopped):
    while not stopped.is_set():
        try: ticket,method,arguments=tasks.get(timeout=.2)
        except queue.Empty: continue
        try: results.put(("completion",(ticket,True,request(method,arguments))))
        except Exception as exc: results.put(("completion",(ticket,False,str(exc))))
        finally: tasks.task_done()


def launch(request, ensure_started, state_directory):
    # Tcl objects must be finalized by their creating thread, including cyclic garbage.
    enabled = gc.isenabled()
    gc.disable()
    try:
        gc.collect()
        return _launch(request, ensure_started, state_directory)
    finally:
        gc.collect()
        if enabled: gc.enable()


def _launch(request, ensure_started, state_directory):
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.SetProcessDPIAware()
        from windows_identity import set_process_identity
        set_process_identity()
    ensure_started()
    try: saved = request("settings.get", {"scope": "ui"})
    except Exception: saved = {}
    root = tk.Tk()
    root.withdraw()
    theme_manager = ThemeManager(root,saved)
    root.title(APP_NAME)
    native_icon = None
    icon = RESOURCES / "assets/nexus-hub.ico"
    if icon.exists():
        root.iconbitmap(str(icon))
        if os.name == "nt": root.iconbitmap(default=str(icon))
        # Store the same identity in Tk itself, so later wrapper recreation cannot
        # replace native WM_SETICON values with Tk's compiled-in feather.
        root._nexus_default_icons=[tk.PhotoImage(master=root,file=str(RESOURCES/f"assets/nexus-{size}.png")) for size in (16,20,24,32,40,48,64)]
        root.iconphoto(True,*root._nexus_default_icons)
    root.configure(bg=BG)
    width, height = min(1360, root.winfo_screenwidth() - 80), min(900, root.winfo_screenheight() - 140)
    root.geometry(f"{width}x{height}+70+50")
    root.minsize(900, 560)
    root.columnconfigure(0, weight=1)
    root.rowconfigure(1, weight=1)
    if os.name == "nt":
        try:
            root.update_idletasks()
            from window_icon import WindowIcon
            if icon.exists():
                native_icon = WindowIcon(root, icon)
                root._nexus_icon=native_icon
            handle = ctypes.windll.user32.GetParent(root.winfo_id())
            enabled = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle, 20, ctypes.byref(enabled), ctypes.sizeof(enabled))
        except Exception: pass
        def theme_child(event):
            child = event.widget
            if not isinstance(child, tk.Toplevel) or getattr(child,"_nexus_icon",None): return
            def apply():
                if not child.winfo_exists(): return
                try:
                    child._nexus_icon = WindowIcon(child, icon)
                except Exception: pass
            root.after_idle(apply)
        root.bind_class("Toplevel","<Map>",theme_child,add="+")
    root.option_add("*Font", FONT)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#40576a")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                    bordercolor=FIELD, arrowcolor=MUTED, lightcolor=FIELD, darkcolor=FIELD,
                    padding=5, selectbackground=FIELD, selectforeground=TEXT)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD), ("disabled", PANEL)],
              foreground=[("readonly", TEXT), ("disabled", MUTED)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", TEXT)],
              bordercolor=[("focus", ACCENT)], background=[("active", "#3d4350")])
    style.configure("Vertical.TScrollbar", background="#424650", troughcolor=TERMINAL,
                    bordercolor=TERMINAL, arrowcolor=MUTED, lightcolor=TERMINAL, darkcolor=TERMINAL,
                    gripcount=0, width=10)
    style.map("Vertical.TScrollbar", background=[("active", "#657084")])
    style.configure("Horizontal.TScrollbar", background="#424650", troughcolor=TERMINAL,
                    bordercolor=TERMINAL, arrowcolor=MUTED, lightcolor=TERMINAL, darkcolor=TERMINAL,
                    gripcount=0, width=10)
    style.map("Horizontal.TScrollbar", background=[("active", "#657084")])
    style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD,
                    bordercolor=FIELD, lightcolor=ACCENT, darkcolor=ACCENT)

    result_queue = queue.Queue()
    completion_callbacks = {}
    completion_sequence = 0
    stopped = threading.Event()
    io_tasks = queue.Queue(maxsize=16)
    for _ in range(4):
        threading.Thread(target=_io_worker,args=(request,io_tasks,result_queue,stopped),daemon=True).start()
    render_pending = deque(maxlen=2500)
    restore = {"active":False, "remaining":0, "generation":0}
    events = {"serial": deque(maxlen=2500), "beken": deque(maxlen=2500)}
    history = deque(maxlen=500)
    selected = "serial"
    states = {}
    backend_info = {}
    busy = False
    paused = tk.BooleanVar(value=False)
    hex_display = tk.BooleanVar(value=False)
    timestamps = tk.BooleanVar(value=False)
    autoscroll = tk.BooleanVar(value=True)
    hex_send = tk.BooleanVar(value=False)
    command_mode = tk.BooleanVar(value=bool(saved.get("command_mode", False)))
    presets = {str(k): v for k, v in saved.get("serial_presets", {}).items()
               if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("text"), str)} if isinstance(saved.get("serial_presets"), dict) else {}
    preset_name = tk.StringVar()
    command_history = []
    history_position = 0
    history_draft = ""
    variables = {
        "port": tk.StringVar(value="COM14"), "baudrate": tk.StringVar(value="1500000"),
        "flash_port": tk.StringVar(value="COM14"), "flash_baudrate": tk.StringVar(value="1500000"),
        "bytesize": tk.StringVar(value="8"), "parity": tk.StringVar(value="N"),
        "stopbits": tk.StringVar(value="1"), "encoding": tk.StringVar(value="utf-8"),
        "dtr": tk.BooleanVar(value=False), "rts": tk.BooleanVar(value=False),
        "newline": tk.StringVar(value="CRLF"),
        "firmware": tk.StringVar(value=str(__import__("pathlib").Path.home() / "Desktop/all-app.bin")),
        "address": tk.StringVar(value="0x0")}
    for name, value in saved.get("variables", {}).items():
        if name in variables and isinstance(value, (str, bool, int, float)):
            variables[name].set(value)
    for name, variable in (("hex_display", hex_display), ("timestamps", timestamps),
                           ("autoscroll", autoscroll), ("hex_send", hex_send)):
        if name in saved: variable.set(bool(saved[name]))
    if saved.get("geometry"):
        import re
        match = re.match(r"(\d+)x(\d+)", saved["geometry"])
        if match:
            root.geometry(f"{min(int(match[1]), root.winfo_screenwidth()-80)}x{min(int(match[2]), root.winfo_screenheight()-140)}+70+50")

    def frame(parent, bg=PANEL, **kwargs):
        return tk.Frame(parent, bg=bg, **kwargs)

    def label(parent, text="", muted=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=MUTED if muted else TEXT,
                        anchor="w", **kwargs)

    def button(parent, text, command, primary=False, small=False, _flat=False):
        bg = "#23576b" if primary else FIELD
        cls=tk.Button if _flat else ActionButton
        options={} if _flat else dict(primary=primary,small=small)
        item = cls(parent, text=text, command=command, bg=bg, fg=TEXT, **options,
                         activebackground="#326e84" if primary else "#424854", activeforeground="white",
                         disabledforeground=MUTED, relief="flat", borderwidth=0, cursor="hand2",
                         padx=10 if small else 14, pady=5 if small else 8,
                         highlightthickness=0, takefocus=True)
        item._nexus_primary=primary
        item._nexus_raw_text=text
        return item

    def check(parent, text, variable, command=None):
        return tk.Checkbutton(parent, text=text, variable=variable, command=command,
             bg=parent.cget("bg"), fg=TEXT, activebackground=parent.cget("bg"),
             activeforeground=TEXT, selectcolor=FIELD, highlightthickness=0,
             borderwidth=0, anchor="w", cursor="hand2", pady=5)

    def entry(parent, variable):
        return tk.Entry(parent, textvariable=variable, bg=FIELD, fg=TEXT, insertbackground=TEXT,
                        relief="flat", highlightthickness=1, highlightbackground=FIELD,
                        highlightcolor=ACCENT)

    top = frame(root, "#1c2029", height=58)
    top.grid(row=0, column=0, columnspan=2, sticky="ew")
    top.pack_propagate(False)
    logo_path = RESOURCES / "assets/nexus-40.png"
    if logo_path.exists():
        root.brand_logo = tk.PhotoImage(file=str(logo_path))
        tk.Label(top, image=root.brand_logo, bg="#1c2029").pack(side="left", padx=(16, 9))
    else:
        tk.Label(top, text="◈", fg=ACCENT, bg="#1c2029", font=("Segoe UI Symbol", 22)).pack(side="left", padx=(18, 8))
    brand = frame(top, "#1c2029")
    brand.pack(side="left", padx=(0, 24))
    label(brand, "EEDP Nexus", font=("Segoe UI", 12, "bold")).pack(anchor="w")
    label(brand, "Agent 协作中枢", muted=True, font=("Microsoft YaHei UI", 8)).pack(anchor="w")
    tabs = {}
    component_metadata = {}
    menu_bar=frame(top,"#1c2029")
    menu_bar.pack(side="left",fill="y",padx=14)
    management_nav={}
    settings_page={}
    activity_bar = frame(root, "#181d26", width=88, highlightthickness=1, highlightbackground=BORDER)
    activity_bar.grid(row=1, column=1, sticky="ns")
    activity_bar.pack_propagate(False)
    activity_components = frame(activity_bar, "#181d26")
    activity_components.pack(fill="x", pady=(8, 0))
    activity_management = frame(activity_bar, "#181d26")
    activity_management.pack(side="bottom", fill="x", pady=8)
    workspace_shell=frame(root,BORDER,padx=1,pady=1)
    workspace_shell.grid(row=1,column=0,sticky="nsew",padx=(10,8),pady=8)
    workspace_shell.rowconfigure(1,weight=1)
    workspace_shell.columnconfigure(0,weight=1)
    workspace_header=frame(workspace_shell,"#1c2029",height=38)
    workspace_header.grid(row=0,column=0,sticky="ew")
    workspace_header.pack_propagate(False)
    workspace_title=label(workspace_header,"组件 / 串口监控",font=("Microsoft YaHei UI",10,"bold"))
    workspace_title.pack(side="left",padx=14)
    frame(workspace_header,BORDER,height=1).pack(side="bottom",fill="x")
    workspace_body=frame(workspace_shell,BG)
    workspace_body.grid(row=1,column=0,sticky="nsew")
    workspace_body.rowconfigure(0,weight=1)
    workspace_body.columnconfigure(0,weight=1)
    logic_host = frame(workspace_body, BG)
    utility_host = frame(workspace_body, PANEL)
    utility_page = {"name":None, "refresh":None}
    empty_workspace = frame(workspace_body, BG)
    label(empty_workspace, "没有启用的组件\n从右侧组件管理安装或启用工具", muted=True, justify="center").pack(expand=True)
    logic_workspace = None

    def rail_button(parent, text, command, icon="blocks"):
        item = button(parent, text, command, small=True, _flat=True)
        item.configure(font=("Microsoft YaHei UI", 8), padx=3, pady=10, bg="#181d26")
        item._nexus_rail=True
        item._nexus_icon_name=icon
        return item

    def nav_selected(name):
        for key,item in {**tabs,**management_nav}.items():
            item.configure(bg="#2b3543" if key==name else "#1c2029",fg=ACCENT if key==name else MUTED)

    main = tk.PanedWindow(workspace_body, orient="horizontal", bg=BORDER, bd=0,
                          sashwidth=7, sashrelief="flat", opaqueresize=True)
    main.grid(row=0, column=0, sticky="nsew")
    sidebar = frame(main, PANEL)
    left_canvas = tk.Canvas(sidebar, bg=PANEL, highlightthickness=0, width=292)
    left_scrollbar = ttk.Scrollbar(sidebar, orient="vertical", command=left_canvas.yview)
    left_scrollbar.pack(side="right", fill="y")
    left_canvas.pack(side="left", fill="both", expand=True)
    left_canvas.configure(yscrollcommand=left_scrollbar.set)
    left = frame(left_canvas, PANEL)
    left_window = left_canvas.create_window(0, 0, window=left, anchor="nw")
    left.bind("<Configure>", lambda event: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
    left_canvas.bind("<Configure>", lambda event: left_canvas.itemconfigure(left_window, width=event.width))
    def sidebar_wheel(event):
        widget = event.widget
        while widget is not None:
            if widget == sidebar:
                left_canvas.yview_scroll(-int(event.delta / 120), "units")
                return "break"
            widget = getattr(widget, "master", None)
    root.bind("<MouseWheel>", sidebar_wheel, add="+")
    right = frame(main, BG)
    main.add(sidebar, minsize=250, width=max(250, min(int(saved.get("sidebar_width", 292)), 550)), stretch="never")
    main.add(right, minsize=500, stretch="always")
    right.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1, minsize=80)

    section_title = label(left, "连接设置", font=("Microsoft YaHei UI", 10, "bold"))
    section_title.pack(fill="x", padx=18, pady=(18, 12))
    parameter_area = frame(left)
    parameter_area.pack(fill="x", padx=18)
    parameter_area.columnconfigure(1, weight=1)
    port_box = None
    port_descriptions = {}
    port_labels = {}
    port_description = tk.StringVar(value="")

    def update_port_description(*_):
        port_description.set(port_descriptions.get(variables["port"].get(), ""))
    variables["port"].trace_add("write", update_port_description)

    def row(parent, index, caption, name, choices=None):
        label(parent, caption, muted=True).grid(row=index, column=0, sticky="w", padx=(0, 16), pady=4)
        var = variables[name]
        widget = ttk.Combobox(parent, textvariable=var, values=choices or [],
                    state="readonly" if choices else "normal", width=14) if choices is not None else entry(parent, var)
        widget.grid(row=index, column=1, sticky="ew", pady=4, ipady=4 if choices is None else 0)
        return widget

    serial_options = frame(left)
    flash_options = frame(left)

    terminal_bar = frame(right, BG, height=48)
    terminal_bar.grid(row=0, column=0, sticky="ew", padx=16)
    terminal_bar.pack_propagate(False)
    terminal_title = label(terminal_bar, "接收区", font=("Microsoft YaHei UI", 10, "bold"))
    terminal_title.pack(side="left")
    connection_label = label(terminal_bar, "未连接", muted=True)
    connection_label.pack(side="left", padx=16)
    terminal_border = frame(right, BORDER, padx=1, pady=1)
    terminal_border.grid(row=1, column=0, sticky="nsew", padx=14)
    terminal = tk.Text(terminal_border, bg=TERMINAL, fg=TEXT, insertbackground=TEXT,
                       selectbackground="#39516a", relief="flat", borderwidth=0, padx=12, pady=12,
                       wrap="word", font=("Cascadia Mono", 11), state="disabled", undo=False)
    terminal._nexus_log_terminal=True
    scrollbar = ttk.Scrollbar(terminal_border, orient="vertical", command=terminal.yview)
    terminal.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    terminal.pack(side="left", fill="both", expand=True)
    terminal.tag_configure("tx", foreground="#e9b860")
    terminal.tag_configure("error", foreground=RED)
    terminal.tag_configure("finished", foreground=GREEN)
    terminal.tag_configure("notice", foreground=MUTED)
    terminal.tag_configure("output", foreground=TEXT)
    restore_cover = tk.Label(terminal_border, text="加载日志…", bg=TERMINAL, fg=MUTED, font=FONT)

    send_area = frame(right, BG)
    send_options = frame(send_area, BG)
    send_options.pack(fill="x", pady=(8, 5))
    label(send_options, "发送区", muted=True).pack(side="left")
    send_row = frame(send_area, BG)
    send_row.pack(fill="x", pady=(0, 10))
    send_text = tk.Text(send_row, bg=TERMINAL, fg=TEXT, insertbackground=TEXT,
                         font=("Cascadia Mono", 11), height=3, relief="flat", padx=12, pady=10,
                         highlightthickness=1, highlightbackground=BORDER, highlightcolor=ACCENT, wrap="word")
    # Reserve the action button before allocating the remaining width to the editor.
    send_button = button(send_row, "➤  发送", lambda: send(), primary=True)
    send_button.pack(side="right", padx=(8, 0))
    send_text.pack(side="left", fill="both", expand=True)

    flash_footer = frame(right, BG)
    flash_stage = label(flash_footer, "等待任务", muted=True)
    flash_stage.pack(anchor="w", pady=10)
    progress = ttk.Progressbar(flash_footer, mode="determinate", length=200)
    progress.pack(fill="x", pady=(0, 12))
    statusbar = frame(root, "#1c2029", height=31)
    statusbar._nexus_statusbar=True
    statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")
    statusbar.pack_propagate(False)
    service_label=button(statusbar,"● Agent 桥接：连接中",lambda:show_service(),small=True,_flat=True)
    service_label.configure(bg="#1c2029",fg=MUTED,pady=3)
    service_label.pack(side="left",padx=(8,12),fill="y")
    status_text = label(statusbar, "后台服务已就绪", muted=True)
    status_text.pack(side="left", padx=16)
    counter = label(statusbar, "RX 0 B   /   TX 0 B", muted=True)
    counter.pack(side="right", padx=16)

    def append_batch(chunks):
        if not chunks: return
        mapped = terminal.winfo_ismapped()
        bottom = mapped and not restore["active"] and terminal.yview()[1] > .95
        terminal.configure(state="normal")
        for text, kind in chunks:
            terminal.insert("end", text.replace("\x00", "␀"), kind)
        if int(terminal.index("end-1c").split(".")[0]) > 5000:
            terminal.delete("1.0", "1500.0")
        if (terminal.count("1.0", "end-1c", "chars") or (0,))[0] > 1_500_000:
            terminal.delete("1.0", "end-1000000c")
        terminal.configure(state="disabled")
        if not restore["active"] and autoscroll.get() and bottom: terminal.see("end")

    def append(text, kind=""):
        append_batch([(text, kind)])

    def event_text(item):
        kind = item["kind"]
        prefix = f"[{item['time'][11:23]}] " if timestamps.get() else ""
        if kind == "rx":
            text = (bytes.hex(base64.b64decode(item["base64"]), " ") + "\n") if hex_display.get() else item["text"]
            return prefix + text[-32768:], kind
        elif kind == "tx":
            return "\n" + prefix + "» " + item["text"][-32768:] + "\n", kind
        elif kind in ("error", "output", "finished", "notice"):
            return prefix + item["text"][-32768:] + "\n", kind
        return None

    def render_event(item):
        value = event_text(item)
        if value: append_batch([value])

    def clear_display():
        restore.update(active=False, remaining=0, generation=restore["generation"]+1)
        restore_cover.place_forget()
        events[selected].clear()
        render_pending.clear()
        terminal.configure(state="normal")
        terminal.delete("1.0", "end")
        terminal.configure(state="disabled")

    def redraw():
        if selected not in events: return
        restore.update(active=True, remaining=len(events[selected]), generation=restore["generation"]+1)
        restore_cover.place(x=0,y=0,relwidth=1,relheight=1)
        restore_cover.lift()
        terminal.configure(state="normal")
        terminal.delete("1.0", "end")
        terminal.configure(state="disabled")
        render_pending.clear()
        render_pending.extend(events[selected])

    def save_display():
        path = filedialog.asksaveasfilename(parent=root, defaultextension=".log", filetypes=[("日志", "*.log"), ("文本", "*.txt")])
        if path:
            from pathlib import Path
            Path(path).write_text(terminal.get("1.0", "end-1c"), encoding="utf-8")
            status_text.configure(text="已保存日志：" + path)

    def call(target, arguments=None):
        nonlocal busy
        if busy:
            status_text.configure(text="上一项操作仍在执行，请稍候")
            return
        busy = True
        status_text.configure(text="正在执行 " + target)
        def worker():
            try:
                result = request("call", dict(target=target, arguments=arguments or {}))
                result_queue.put(("result", (target, result)))
            except Exception as exc: result_queue.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def background_request(method, arguments, success=None, failure=None):
        nonlocal completion_sequence
        completion_sequence += 1
        ticket = completion_sequence
        completion_callbacks[ticket] = (success,failure)
        try: io_tasks.put_nowait((ticket,method,arguments))
        except queue.Full:
            completion_callbacks.pop(ticket,None)
            if failure: failure("后台请求队列已满，请稍候")

    def connection_click():
        if states.get("serial", {}).get("connected"):
            call("serial.disconnect")
        else:
            try:
                args = {k: v.get() for k, v in variables.items() if k in ("port", "baudrate", "bytesize", "parity", "stopbits", "encoding", "dtr", "rts")}
                args["baudrate"], args["bytesize"], args["stopbits"] = int(args["baudrate"]), int(args["bytesize"]), float(args["stopbits"])
                call("serial.connect", args)
            except ValueError as exc: messagebox.showerror("参数错误", str(exc), parent=root)

    def send(_=None):
        nonlocal history_position, history_draft
        if busy: return "break"
        text = send_text.get("1.0", "end-1c")
        call("serial.send", dict(text=text, hex_mode=False if command_mode.get() else hex_send.get(), newline=variables["newline"].get()))
        if command_mode.get():
            if text and (not command_history or command_history[-1] != text):
                command_history.append(text)
                del command_history[:-100]
            history_position = len(command_history)
            history_draft = ""
            send_text.delete("1.0", "end")
        return "break"

    def command_key(event):
        nonlocal history_position, history_draft
        if not command_mode.get(): return
        if event.keysym in ("Return", "KP_Enter"):
            return send()
        if event.keysym in ("Up", "Down"):
            if not command_history: return "break"
            if history_position == len(command_history):
                history_draft = send_text.get("1.0", "end-1c")
            history_position = max(0, min(len(command_history), history_position + (-1 if event.keysym == "Up" else 1)))
            send_text.delete("1.0", "end")
            send_text.insert("1.0", command_history[history_position] if history_position < len(command_history) else history_draft)
            return "break"

    def mode_changed():
        if command_mode.get(): hex_send.set(False)
        send_text.configure(height=1 if command_mode.get() else 3)

    def hex_changed():
        if hex_send.get() and command_mode.get():
            command_mode.set(False)
            mode_changed()

    preset_bar = frame(send_area, BG)
    preset_bar.pack(fill="x", before=send_row, pady=(0, 5))
    def refresh_presets():
        preset_box.configure(values=sorted(presets))
    def load_preset(_=None):
        preset = presets.get(preset_name.get())
        if not preset: return
        send_text.delete("1.0", "end")
        send_text.insert("1.0", preset["text"])
        hex_send.set(bool(preset.get("hex_mode", False)))
        if hex_send.get() and command_mode.get():
            command_mode.set(False)
            mode_changed()
        if preset.get("newline") in ("CRLF", "CR", "LF", "NONE"):
            variables["newline"].set(preset["newline"])
    def save_preset():
        name = simpledialog.askstring("保存命令", "命令名称：", initialvalue=preset_name.get(), parent=root)
        if name is None: return
        name = name.strip()
        if not name:
            messagebox.showerror("保存命令", "请输入命令名称。", parent=root)
            return
        if name in presets and not messagebox.askyesno("保存命令", "该名称已存在，覆盖它吗？", parent=root): return
        presets[name] = dict(text=send_text.get("1.0", "end-1c"), hex_mode=hex_send.get(), newline=variables["newline"].get())
        preset_name.set(name)
        refresh_presets()
        save_preferences()
    def delete_preset():
        name = preset_name.get()
        if name not in presets: return
        if not messagebox.askyesno("删除命令", f"删除命令“{name}”？", parent=root): return
        del presets[name]
        preset_name.set("")
        refresh_presets()
        save_preferences()
    button(preset_bar, "删除", delete_preset, small=True).pack(side="right", padx=(4, 0))
    button(preset_bar, "保存命令", save_preset, small=True).pack(side="right", padx=(4, 0))
    label(preset_bar, "常用命令", muted=True).pack(side="left", padx=(0, 6))
    preset_box = ttk.Combobox(preset_bar, textvariable=preset_name, state="readonly", width=12)
    preset_box.pack(side="left", fill="x", expand=True)
    preset_box.bind("<<ComboboxSelected>>", load_preset)
    refresh_presets()

    for key in ("Return", "KP_Enter", "Up", "Down"):
        send_text.bind(f"<{key}>", command_key)
    mode_changed()

    def flash_arguments():
        return dict(firmware=variables["firmware"].get(), port=variables["flash_port"].get(),
                    baudrate=variables["flash_baudrate"].get(), address=variables["address"].get())

    def flash_start():
        args = flash_arguments()
        if messagebox.askokcancel("开始烧录", f"设备：{args['port']}\n固件：{args['firmware']}\n起始地址：{args['address']}\n\n将写入设备 Flash，是否继续？", parent=root):
            call("beken.start", args)

    def flash_cancel():
        if messagebox.askokcancel("中止烧录", "中止后设备可能需要重新烧录。确定中止？", parent=root): call("beken.cancel")

    def separator(parent):
        frame(parent, BORDER, height=1).pack(fill="x", padx=18, pady=14)

    def select(component):
        nonlocal selected, port_box, logic_workspace
        selected = component
        workspace_title.configure(text="组件 / "+component_metadata.get(component,{}).get("name",{"serial":"串口监控","beken":"Beken 烧录","slogic":"逻辑分析仪"}.get(component,component)))
        nav_selected(component)
        empty_workspace.grid_remove()
        utility_host.grid_remove()
        if component not in ("serial","beken","slogic"):
            if show_utility("plugin:"+component):
                view = open_plugin_tools(utility_host, component, background_request, frame, label, button, embedded=True)
                view.pack(fill="both",expand=True)
            return
        if component == "slogic":
            main.grid_remove()
            logic_host.grid(row=0,column=0,sticky="nsew")
            if logic_workspace is None or not logic_workspace.winfo_exists():
                logic_workspace = open_logic_view(logic_host, background_request, frame, label, button, embedded=True)
                logic_workspace.pack(fill="both",expand=True)
            refresh_states()
            return
        logic_host.grid_remove()
        main.grid(row=0,column=0,sticky="nsew")
        for child in parameter_area.winfo_children(): child.destroy()
        serial_options.pack_forget()
        flash_options.pack_forget()
        send_area.grid_remove()
        flash_footer.grid_remove()
        section_title.configure(text="连接设置" if selected == "serial" else "烧录设置")
        port_box = row(parameter_area, 0, "端口名", "port" if selected == "serial" else "flash_port", [])
        port_box.configure(state="normal", values=list(port_labels))
        def port_selected(_):
            variable = variables["port" if component == "serial" else "flash_port"]
            variable.set(port_labels.get(variable.get(), variable.get()))
        port_box.bind("<<ComboboxSelected>>", port_selected)
        row(parameter_area, 1, "波特率", "baudrate" if selected == "serial" else "flash_baudrate",
            SERIAL_BAUDRATES if selected == "serial" else [9600, 115200, 460800, 921600, 1500000, 2000000]).configure(state="normal")
        if selected == "serial":
            row(parameter_area, 2, "数据位", "bytesize", [5, 6, 7, 8])
            row(parameter_area, 3, "校验位", "parity", ["N", "E", "O", "M", "S"])
            row(parameter_area, 4, "停止位", "stopbits", [1, 1.5, 2])
            row(parameter_area, 5, "编码", "encoding", ["utf-8", "gb18030", "ascii"])
            serial_options.pack(fill="x", pady=(8, 0))
            send_area.grid(row=2, column=0, sticky="ew", padx=14)
            terminal_title.configure(text="串口输出")
        else:
            row(parameter_area, 2, "起始地址", "address")
            flash_options.pack(fill="x", pady=(12, 0))
            flash_footer.grid(row=2, column=0, sticky="ew", padx=14)
            terminal_title.configure(text="烧录日志")
        redraw()
        refresh_states()

    known_ports = []
    for key, caption in [("serial", "⌁\n串口监控"), ("beken", "⇩\nBeken 烧录"), ("slogic", "▥\n逻辑分析")]:
        tabs[key] = rail_button(activity_components, caption, lambda c=key: select(c),icon={"serial":"usb","beken":"zap","slogic":"square-activity"}[key])

    lines = frame(serial_options)
    label(serial_options, "设备描述", muted=True).pack(anchor="w", padx=18)
    description_label = label(serial_options, "", muted=True, wraplength=230, justify="left")
    description_label.configure(textvariable=port_description)
    description_label.pack(fill="x", padx=18, pady=(0, 5))
    lines.pack(fill="x", padx=18)
    check(lines, "DTR", variables["dtr"]).pack(side="left")
    check(lines, "RTS", variables["rts"]).pack(side="left", padx=16)
    connect_button = button(serial_options, "打开串口", connection_click, primary=True)
    connect_button.pack(fill="x", padx=18, pady=(8, 0))
    button(serial_options, "↻  刷新端口", lambda: call("serial.ports"), small=True).pack(fill="x", padx=18, pady=6)
    separator(serial_options)
    label(serial_options, "发送设置", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=18, pady=(0, 5))
    check(serial_options, "命令行模式", command_mode, mode_changed).pack(fill="x", padx=16)
    check(serial_options, "HEX 发送", hex_send, hex_changed).pack(fill="x", padx=16)
    ending_row = frame(serial_options)
    ending_row.pack(fill="x", padx=18, pady=(5, 0))
    label(ending_row, "结尾", muted=True).pack(side="left", padx=(0, 12))
    ttk.Combobox(ending_row, textvariable=variables["newline"], values=["CRLF", "LF", "CR", "NONE"],
                 state="readonly", width=8).pack(side="left", fill="x", expand=True)
    separator(serial_options)
    label(serial_options, "接收设置", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", padx=18, pady=(0, 5))
    for caption, var, callback in [("十六进制显示", hex_display, redraw), ("显示时间戳", timestamps, redraw),
                                  ("自动滚动", autoscroll, None), ("暂停显示", paused, lambda: redraw() if not paused.get() else None)]:
        check(serial_options, caption, var, callback).pack(fill="x", padx=16)
    actions = frame(serial_options)
    actions.pack(fill="x", padx=18, pady=(10, 0))
    button(actions, "保存显示", save_display, small=True).pack(side="left")
    button(actions, "清空显示", clear_display, small=True).pack(side="right")
    separator(serial_options)
    label(serial_options, "接收数据自动写入后台日志。\n关闭窗口后连接继续保留。", muted=True, justify="left").pack(anchor="w", padx=18)

    label(flash_options, "固件文件", muted=True).pack(anchor="w", padx=18, pady=(0, 6))
    firmware_path = entry(flash_options, variables["firmware"])
    firmware_path.pack(fill="x", padx=18, ipady=8)
    def choose_firmware():
        path = filedialog.askopenfilename(parent=root, filetypes=[("固件", "*.bin")])
        if path: variables["firmware"].set(path)
    button(flash_options, "选择 .bin 文件", choose_firmware, small=True).pack(fill="x", padx=18, pady=8)
    separator(flash_options)
    label(flash_options, "写入选定地址与固件区间\n不写入 Efuse / OTP\n引擎：本机 bk_loader", muted=True, justify="left").pack(anchor="w", padx=18, pady=(0, 14))
    button(flash_options, "预检固件", lambda: call("beken.inspect", flash_arguments())).pack(fill="x", padx=18, pady=5)
    start_button = button(flash_options, "开始烧录", flash_start, primary=True)
    start_button.pack(fill="x", padx=18, pady=5)
    cancel_button = button(flash_options, "中止任务", flash_cancel)
    cancel_button.pack(fill="x", padx=18, pady=5)
    separator(flash_options)
    label(flash_options, "烧录与串口监控独立调用。\n占用冲突时由 Agent 选择释放。", muted=True, justify="left").pack(anchor="w", padx=18)

    send_text.bind("<Control-Return>", send)
    button(terminal_bar, "清空", clear_display, small=True).pack(side="right", pady=8)
    button(terminal_bar, "保存", save_display, small=True).pack(side="right", padx=6, pady=8)

    log_window = None
    def journal():
        nonlocal log_window
        if log_window is not None and log_window.winfo_exists():
            log_window.deiconify()
            log_window.lift()
            return
        log_window = open_log_center(root, background_request, state_directory, frame, label, button)
    rail_button(activity_management, "≡\n日志中心", journal,icon="file-text").pack(fill="x", pady=2)

    def show_utility(name):
        main.grid_remove()
        logic_host.grid_remove()
        empty_workspace.grid_remove()
        utility_host.grid(row=0,column=0,sticky="nsew")
        workspace_title.configure(text=utility_title(name))
        nav_selected(name.partition(":")[2] if name.startswith("plugin:") else name)
        if utility_page["name"] == name and utility_host.winfo_children(): return False
        for child in utility_host.winfo_children(): child.destroy()
        utility_page.update(name=name,refresh=None)
        return True

    def utility_title(name):
        return {"settings":"设置 / 工作台偏好","plugins":"组件管理","service":"后台 / Agent 桥接状态",
                "doc:standard":"帮助 / 组件开发标准手册","doc:usage":"帮助 / 使用说明","about":"帮助 / 关于"}.get(name,"组件 / "+name.partition(":")[2])

    def integration(section="appearance"):
        if not show_utility("settings"):
            if settings_page.get("notebook") and settings_page["notebook"].winfo_exists():
                settings_page["notebook"].select(settings_page[section])
            return
        window = utility_host
        notebook=ttk.Notebook(window,style="Nexus.TNotebook")
        notebook.pack(fill="both",expand=True,padx=16,pady=(0,12))
        appearance=frame(notebook)
        connection=frame(notebook)
        notebook.add(appearance,text="外观")
        notebook.add(connection,text="Agent 连接")
        settings_page.update(notebook=notebook,appearance=appearance,agent=connection)
        if section=="agent":notebook.select(connection)
        build_appearance(appearance,theme_manager,lambda:save_preferences(),frame,label,button)
        window=connection
        label(window, "同一服务 · Windows / WSL Agent 共用", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=20, pady=16)
        label(window, "支持标准 MCP stdio，也可通过技能使用 CLI。接口令牌由客户端管理。", muted=True).pack(anchor="w", padx=20)
        root_path = state_directory.parent
        windows = {"mcpServers": {"agent-workbench": {"command": str(root_path / CLI_EXE), "args": ["mcp"]}}} if FROZEN else {"mcpServers": {"agent-workbench": {"command": str(root_path / ".venv/Scripts/python.exe"), "args": [str(root_path / "mcp-bridge.py")]}}}
        drive = str(root_path).replace("\\", "/")
        wsl_path = "/mnt/" + drive[0].lower() + drive[2:] if len(drive) > 1 and drive[1] == ":" else drive
        linux = {"mcpServers": {"agent-workbench": {"command": "python3", "args": [wsl_path + ("/agent_bridge/mcp-bridge.py" if FROZEN else "/mcp-bridge.py")]}}}
        view = tk.Text(window, bg=TERMINAL, fg=TEXT, font=("Consolas", 10), padx=16, pady=16, relief="flat")
        view.pack(fill="both", expand=True, padx=20, pady=16)
        view.insert("end", "Windows MCP\n" + json.dumps(windows, ensure_ascii=False, indent=2) + "\n\nWSL MCP\n" + json.dumps(linux, ensure_ascii=False, indent=2))
        view.configure(state="disabled")
        button(window, "复制接口配置", lambda: (root.clipboard_clear(), root.clipboard_append(view.get("1.0", "end-1c")))).pack(anchor="e", padx=20, pady=(0, 16))

    def plugin_dialog():
        if not show_utility("plugins"):
            if utility_page["refresh"]: utility_page["refresh"]()
            return
        window = utility_host
        label(window, "已安装组件", font=("Microsoft YaHei UI", 13, "bold")).pack(anchor="w", padx=20, pady=16)
        label(window, "插件独立加载。禁用会移除其 Agent 工具；使用中的设备须先释放。", muted=True).pack(anchor="w", padx=20)
        listing = frame(window)
        listing.pack(fill="both", expand=True, padx=20, pady=16)
        feedback = label(window, "", muted=True)
        feedback.pack(fill="x", padx=20)
        def populate(plugins):
            if not window.winfo_exists() or not listing.winfo_exists(): return
            for child in listing.winfo_children(): child.destroy()
            try:
                existing={p["id"] for p in plugins}
                plugins=[*plugins,*[p for p in planned_components() if p["id"] not in existing]]
                for plugin in plugins:
                    line = frame(listing, FIELD)
                    line.pack(fill="x", pady=4, ipady=6)
                    icon_name={"serial":"usb","beken":"zap","slogic":"square-activity","mcu":"cpu"}.get(plugin["id"],"blocks")
                    thumbnail=theme_manager.icon(icon_name,32)
                    if thumbnail:
                        icon_label=tk.Label(line,image=thumbnail,bg=FIELD)
                        icon_label._nexus_icon_name=icon_name
                        icon_label.pack(side="left",padx=(10,0))
                    label(line, plugin['name'] if plugin.get("planned") else f"{plugin['name']}  v{plugin['version']}").pack(side="left", padx=12)
                    if plugin.get("planned"):
                        label(line,"规划中 · "+" / ".join(plugin.get("capabilities",[])),muted=True).pack(side="left",padx=8)
                        reserved=button(line,"预留位置",lambda:None,small=True)
                        reserved.configure(state="disabled")
                        reserved.pack(side="right",padx=8)
                        continue
                    label(line, "已启用" if plugin["enabled"] else "已禁用", muted=not plugin["enabled"]).pack(side="left", padx=12)
                    if plugin.get("error"): label(line, plugin["error"], muted=True).pack(side="left")
                    def toggle(p=plugin):
                        background_request("plugins.set", {"id": p["id"], "enabled": not p["enabled"]}, populate, failed)
                    button(line, "禁用" if plugin["enabled"] else "启用", toggle, small=True).pack(side="right", padx=8)
                    if plugin["enabled"]:
                        button(line, "操作", lambda p=plugin: select(p["id"]), small=True).pack(side="right", padx=4)
            except Exception as exc: feedback.configure(text=str(exc), fg=RED)
        def failed(error):
            if window.winfo_exists() and feedback.winfo_exists(): feedback.configure(text=str(error), fg=RED)
        def render():
            background_request("plugins.list", {}, populate, failed)
        def rescan():
            background_request("plugins.rescan", {}, populate, failed)
        actions = frame(window)
        actions.pack(fill="x", padx=20, pady=16)
        button(actions, "扫描插件目录", rescan).pack(side="left")
        button(actions, "打开插件目录", lambda: os.startfile(state_directory.parent / "plugins")).pack(side="right")
        utility_page["refresh"] = render
        render()
    management_nav["plugins"]=rail_button(activity_management, "▦\n组件管理", plugin_dialog,icon="blocks")
    management_nav["plugins"].pack(fill="x",pady=2)
    management_nav["settings"]=rail_button(activity_management, "⚙\n设置", integration,icon="settings")
    management_nav["settings"].pack(fill="x",pady=2)

    def shutdown():
        save_preferences()
        def worker():
            try:
                request("shutdown")
                result_queue.put(("shutdown", None))
            except Exception as exc: result_queue.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    menu = tk.Menu(root, tearoff=False, bg=PANEL, fg=TEXT)
    menu.add_command(label="停止后台服务并退出", command=shutdown)
    menu.add_command(label="仅关闭窗口（后台继续运行）", command=lambda: root.tk.call(root.protocol("WM_DELETE_WINDOW")))
    rail_button(activity_management, "⋯\n更多", lambda: menu.tk_popup(root.winfo_pointerx(), root.winfo_pointery()),icon="ellipsis").pack(fill="x", pady=2)

    def open_waveform():
        if "slogic" not in states:
            status_text.configure(text="请先在组件管理启用逻辑分析仪")
            return
        select("slogic")
        logic_workspace.open_waveform()

    def scan_logic():
        if "slogic" not in states:
            status_text.configure(text="逻辑分析仪组件未启用")
            return
        select("slogic")
        logic_workspace.scan_devices()

    def show_service():
        if not show_utility("service"):
            if utility_page["refresh"]:utility_page["refresh"]()
            return
        label(utility_host,"Agent 桥接后台",font=("Microsoft YaHei UI",15,"bold")).pack(anchor="w",padx=20,pady=18)
        label(utility_host,"它在本机管理设备，让界面、Windows 与 WSL Agent 共用连接和日志。\n关闭窗口后后台仍可工作；停止后台会释放设备连接。",muted=True,justify="left").pack(anchor="w",padx=20)
        summary=label(utility_host,"查询中…",font=("Microsoft YaHei UI",11,"bold"))
        summary.pack(anchor="w",padx=20,pady=16)
        details=tk.Text(utility_host,bg=TERMINAL,fg=TEXT,font=("Consolas",10),relief="flat",wrap="word",state="disabled")
        details.pack(fill="both",expand=True,padx=20,pady=(0,12))
        def render(info):
            if not details.winfo_exists():return
            summary.configure(text=f"后台版本 {info.get('version','未知')} · 已启用 {len(info['components'])} 个组件 · 连接正常")
            rows=["资源占用："+(json.dumps(info["resources"],ensure_ascii=False) if info["resources"] else "无"),"日志目录："+info["logs"],""]
            for identifier,status in info["components"].items():
                rows.append(component_metadata.get(identifier,{}).get("name",identifier)+"："+str(status.get("stage", "已连接 "+str(status.get("port")) if status.get("connected") else status.get("state","空闲"))))
            details.configure(state="normal")
            details.delete("1.0","end")
            details.insert("end","\n".join(rows))
            details.configure(state="disabled")
        def refresh():background_request("status",{},render,lambda error:summary.configure(text=str(error)) if summary.winfo_exists() else None)
        actions=frame(utility_host)
        actions.pack(fill="x",padx=20,pady=14)
        button(actions,"刷新状态",refresh).pack(side="left")
        button(actions,"Agent 连接配置",lambda:integration("agent")).pack(side="left",padx=8)
        button(actions,"停止后台并退出",shutdown).pack(side="right")
        utility_page["refresh"]=refresh
        refresh()

    def open_doc(kind):
        if not show_utility("doc:"+kind):return
        path=ROOT/(("组件开发标准手册.md" if FROZEN else "COMPONENT-STANDARD.md") if kind=="standard" else ("使用说明.txt" if FROZEN else "README.md"))
        content=path.read_text(encoding="utf-8-sig") if path.is_file() else "当前安装缺少此文档，请使用完整软件目录。"
        view=tk.Text(utility_host,bg=TERMINAL,fg=TEXT,font=("Microsoft YaHei UI",10),wrap="word",padx=20,pady=16)
        scroll=ttk.Scrollbar(utility_host,command=view.yview)
        scroll.pack(side="right",fill="y")
        view.configure(yscrollcommand=scroll.set)
        view.pack(fill="both",expand=True)
        view.insert("end",content)
        view.configure(state="disabled")

    def about():
        if not show_utility("about"):return
        label(utility_host,"EEDP Nexus",font=("Segoe UI",24,"bold")).pack(anchor="w",padx=28,pady=(30,12))
        label(utility_host,"Agent 设备与系统协作工作台",font=("Microsoft YaHei UI",13)).pack(anchor="w",padx=28)
        label(utility_host,"后台版本："+backend_info.get("version","连接中")+"\n可用组件："+" / ".join(states)+"\n界面与后台通过本机接口协作，窗口关闭后任务可继续运行。",muted=True,justify="left").pack(anchor="w",padx=28,pady=20)
        label(utility_host,"图标：Lucide 0.468.0（ISC）\n配色参考：Catppuccin、Nord；其余为工作台自定义方案。",muted=True,justify="left").pack(anchor="w",padx=28,pady=(0,18))
        button(utility_host,"查看桥接状态",show_service).pack(anchor="w",padx=28)

    def dropdown(name):
        trigger=tk.Menubutton(menu_bar,text=name,bg="#1c2029",fg=TEXT,activebackground=FIELD,activeforeground=TEXT,relief="flat",padx=10,pady=10)
        trigger.pack(side="left",fill="y")
        choices=tk.Menu(trigger,tearoff=False,bg=PANEL,fg=TEXT,activebackground="#39516a",activeforeground=TEXT)
        trigger.configure(menu=choices)
        return choices
    files=dropdown("文件")
    files.add_command(label="打开波形 .sr…",command=open_waveform,accelerator="Ctrl+O")
    files.add_command(label="保存终端日志…",command=save_display,accelerator="Ctrl+Shift+S")
    files.add_command(label="日志中心 / 导出归档",command=journal)
    files.add_command(label="打开日志目录",command=lambda:os.startfile(state_directory/"logs"))
    files.add_separator()
    files.add_command(label="关闭窗口（后台继续）",command=lambda:root.tk.call(root.protocol("WM_DELETE_WINDOW")))
    views=dropdown("视图")
    def view_entries():
        views.delete(0,"end")
        for identifier in states:
            views.add_command(label=component_metadata.get(identifier,{}).get("name",identifier),command=lambda key=identifier:select(key))
        views.add_separator()
        views.add_command(label="组件管理",command=plugin_dialog)
        views.add_command(label="日志中心",command=journal)
        views.add_command(label="外观与按钮文字",command=integration)
    views.configure(postcommand=view_entries)
    devices=dropdown("设备")
    devices.add_command(label="刷新串口列表",command=lambda:call("serial.ports") if "serial" in states else status_text.configure(text="串口组件未启用"))
    devices.add_command(label="扫描逻辑分析仪（不采样）",command=scan_logic)
    devices.add_command(label="设备占用 / 桥接状态",command=show_service)
    tools_menu=dropdown("工具")
    tools_menu.add_command(label="组件管理",command=plugin_dialog)
    tools_menu.add_command(label="Agent 连接配置",command=lambda:integration("agent"))
    tools_menu.add_command(label="外观设置",command=integration)
    help_menu=dropdown("帮助")
    help_menu.add_command(label="组件开发标准手册",command=lambda:open_doc("standard"))
    help_menu.add_command(label="使用说明",command=lambda:open_doc("usage"))
    help_menu.add_command(label="关于 EEDP Nexus",command=about)
    def shortcut(action):
        def run(event):
            action()
            return "break"
        return run
    root.bind("<Control-o>",shortcut(open_waveform))
    root.bind("<Control-Shift-S>",shortcut(save_display))
    root.bind("<Control-comma>",shortcut(integration))

    def refresh_states():
        if logic_workspace is not None and logic_workspace.winfo_exists() and "slogic" in states:
            logic_workspace.consume_status(states["slogic"])
        serial_state = states.get("serial", {})
        connected = serial_state.get("connected", False)
        connect_button.configure(state="normal" if "serial" in states else "disabled")
        connect_button.configure(text="关闭串口" if connected else "打开串口", bg="#354b48" if connected else "#23576b")
        if selected == "serial":
            connection_label.configure(text=(f"● {serial_state.get('port')}  ·  {serial_state.get('baudrate')}" if connected else "○ 未连接"), fg=GREEN if connected else MUTED)
            counter.configure(text=f"RX {serial_state.get('rx_bytes', 0):,} B    /    TX {serial_state.get('tx_bytes', 0):,} B")
        elif selected == "beken":
            job = states.get("beken", {})
            running = job.get("state") == "running"
            start_button.configure(state="disabled" if running or "beken" not in states else "normal")
            cancel_button.configure(state="normal" if running else "disabled")
            percent = job.get("phase_progress")
            flash_stage.configure(text=job.get("stage", "等待任务") +
                (f"  ·  阶段进度 {percent}%" if percent is not None else "  ·  等待设备响应" if running else ""))
            connection_label.configure(text="● 任务运行中" if running else job.get("stage", "等待任务"), fg=ACCENT if running else MUTED)
            counter.configure(text="独立组件  /  CH340 · Beken")
            if percent is not None:
                progress.stop()
                progress.animating = False
                progress.configure(mode="determinate", value=percent)
            else:
                progress.stop()
                progress.configure(mode="determinate", value=0)
                progress.animating = False
        else:
            counter.configure(text=component_metadata.get(selected,{}).get("name",selected)+" · "+states.get(selected,{}).get("stage","等待任务"))

    known_enabled = None
    def sync_components():
        nonlocal known_enabled, logic_workspace
        for identifier in states:
            if identifier not in tabs:
                tabs[identifier] = rail_button(activity_components, "◇\n"+identifier[:8], lambda c=identifier:select(c))
        enabled = tuple(key for key in tabs if key in states)
        if enabled == known_enabled: return
        first_load = known_enabled is None
        utility_open = bool(utility_host.grid_info()) and not str(utility_page["name"]).startswith("plugin:")
        known_enabled = enabled
        def described(components):
            for component in components:
                component_metadata[component["id"]] = component
                if component["id"] not in ("serial","beken","slogic") and component["id"] in tabs:
                    tabs[component["id"]].configure(text="◇\n"+component["name"][:8])
        background_request("tools",{},described,lambda error:None)
        for tab in tabs.values(): tab.pack_forget()
        for key in enabled: tabs[key].pack(fill="x", pady=2)
        if "slogic" not in enabled and logic_workspace is not None:
            if logic_workspace.winfo_exists(): logic_workspace.destroy()
            logic_workspace = None
        desired = saved.get("selected") if first_load else None
        if desired in enabled and desired != selected: select(desired)
        elif selected not in enabled:
            if enabled: select(enabled[0])
            else:
                main.grid_remove()
                logic_host.grid_remove()
                empty_workspace.grid(row=0,column=0,sticky="nsew")
                workspace_title.configure(text="工作区 / 暂无启用组件")
        if utility_open:
            main.grid_remove()
            logic_host.grid_remove()
            empty_workspace.grid_remove()
            utility_host.grid(row=0,column=0,sticky="nsew")
            workspace_title.configure(text=utility_title(utility_page["name"]))
            nav_selected(utility_page["name"])
        if first_load and "serial" in enabled: call("serial.ports")

    def poll():
        cursor = 0
        try:
            initial = request("status")
            cursor = max(0, initial.get("event_cursor", 0) - 1000)
            result_queue.put(("status", initial))
        except Exception: pass
        while not stopped.is_set():
            try:
                page = request("events", dict(after=cursor))
                cursor = page["cursor"]
                result_queue.put(("events", page))
                result_queue.put(("status", request("status")))
            except Exception as exc: result_queue.put(("offline", str(exc)))
            stopped.wait(.4)

    def update_contents():
        nonlocal states, busy, known_ports
        for _ in range(12):
            try: kind, value = result_queue.get_nowait()
            except queue.Empty: break
            if kind == "events":
                if value["dropped"]: append("显示缓存已轮换，完整记录保存在日志目录。\n", "notice")
                for item in value["events"]:
                    if item["kind"] in ("call", "result", "error", "finished"): history.append(item)
                    component = item["component"]
                    if component not in events: continue
                    events[component].append(item)
                    if component == selected and not paused.get(): render_pending.append(item)
            elif kind == "status":
                backend_info.clear()
                backend_info.update(value)
                states = value["components"]
                service_label.configure(text="● Agent 桥接：已连接", fg=GREEN)
                sync_components()
                refresh_states()
            elif kind == "result":
                busy = False
                target, result = value
                status_text.configure(text=target + "  已完成")
                if target == "serial.ports":
                    known_ports = [p["port"] for p in result]
                    port_descriptions.clear()
                    port_labels.clear()
                    for port in result:
                        name = port["port"]
                        description = str(port.get("description") or "").strip()
                        port_descriptions[name] = description
                        port_labels[f"{name} — {description}" if description and description != name else name] = name
                    update_port_description()
                    if port_box is not None: port_box.configure(values=list(port_labels))
                    status_text.configure(text="可用端口：" + "、".join(known_ports))
                elif target == "beken.inspect":
                    text = f"预检通过\n文件：{result['firmware']}\n大小：{result['length']:,} 字节\nSHA-256：{result['sha256']}\n地址：{result['address']}\n"
                    item = dict(kind="notice", text=text, time="0000-00-00T00:00:00.000", component="beken")
                    events["beken"].append(item)
                    if selected == "beken": render_event(item)
            elif kind == "error":
                busy = False
                status_text.configure(text=value)
                append("错误：" + value + "\n", "error")
            elif kind == "offline":
                service_label.configure(text="○ Agent 桥接：未连接", fg=RED)
                status_text.configure(text=value)
            elif kind == "shutdown":
                finish_window()
                return
            elif kind == "completion":
                ticket, succeeded, result = value
                callbacks = completion_callbacks.pop(ticket,(None,None))
                callback = callbacks[0 if succeeded else 1]
                if callback: callback(result)
                if stopped.is_set(): return
        chunks = []
        characters = 0
        deadline = time.perf_counter() + .008
        while render_pending and len(chunks) < 80 and characters < 65536 and time.perf_counter() < deadline:
            value = event_text(render_pending.popleft())
            if restore["active"]: restore["remaining"] = max(0,restore["remaining"]-1)
            if value:
                chunks.append(value)
                characters += len(value[0])
        append_batch(chunks)
        if restore["active"] and restore["remaining"] == 0:
            generation = restore["generation"]
            restore["active"] = False
            def reveal():
                if generation != restore["generation"] or stopped.is_set(): return
                if terminal.winfo_ismapped(): terminal.see("end")
                restore_cover.place_forget()
            root.after_idle(reveal)

    def update():
        if diagnostics: diagnostics.tick()
        try: update_contents()
        except Exception as exc: callback_error(type(exc), exc, exc.__traceback__)
        finally:
            if not stopped.is_set(): root.after(20, update)

    last_saved_preferences = saved
    def save_preferences(done=None):
        nonlocal last_saved_preferences
        preferences = dict(variables={k: v.get() for k, v in variables.items()}, selected=selected,
                           geometry=root.geometry(), hex_display=hex_display.get(), timestamps=timestamps.get(),
                           autoscroll=autoscroll.get(), hex_send=hex_send.get(), command_mode=command_mode.get(),
                           serial_presets=dict(presets),
                           sidebar_width=main.sash_coord(0)[0])
        preferences.update(theme_manager.settings())
        if preferences == last_saved_preferences:
            if done: done(None)
            return
        def saved_preferences(_):
            nonlocal last_saved_preferences
            last_saved_preferences = preferences
            if done: done(None)
        def failed_preferences(error):
            if done: done(None)
        background_request("settings.update", {"scope": "ui", "values": preferences}, saved_preferences, failed_preferences)
    closing = False
    def finish_window():
        if stopped.is_set(): return
        root.withdraw()
        stopped.set()
        completion_callbacks.clear()
        for identifier in root.tk.call("after", "info"):
            try: root.after_cancel(identifier)
            except tk.TclError: pass
        root.destroy()
    def close_window():
        nonlocal closing
        if closing: return
        closing = True
        def finish(_=None):
            finish_window()
        save_preferences(finish)
        if not stopped.is_set(): root.after(1000, finish)
    root.protocol("WM_DELETE_WINDOW", close_window)
    select(saved.get("selected") if saved.get("selected") in ("serial", "beken") else "serial")
    threading.Thread(target=poll, daemon=True).start()
    root.after(100, update)
    def periodic_save():
        save_preferences()
        root.after(5000, periodic_save)
    root.after(5000, periodic_save)
    def collect_ui_garbage():
        if stopped.is_set(): return
        gc.collect()
        root.after(10000,collect_ui_garbage)
    root.after(10000,collect_ui_garbage)
    def callback_error(kind, value, trace):
        import traceback
        with diagnostic_path(state_directory, "gui.log").open("a", encoding="utf-8") as log:
            log.write("".join(traceback.format_exception(kind, value, trace)))
        status_text.configure(text="界面操作失败：" + str(value))
    root.report_callback_exception = callback_error
    try: diagnostics = UIDiagnostics(diagnostic_path(state_directory, "gui-diagnostics.log"))
    except OSError: diagnostics = None
    theme_manager.apply(force=True)
    if native_icon:root.after_idle(native_icon.reapply)
    root.deiconify()
    if theme_manager.typography["startup"]:
        from startup_view import StartupReveal
        root._nexus_startup=StartupReveal(root)
    try:
        root.mainloop()
    finally:
        stopped.set()
        if diagnostics: diagnostics.close()
        if native_icon: native_icon.close()
