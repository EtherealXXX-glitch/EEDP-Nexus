"""Asynchronous log-center view; all history is fetched from the shared backend."""
import json
import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from themes import palette


def open_log_center(root, background_request, state_directory, frame, label, button):
    window = tk.Toplevel(root)
    window.title("EEDP Nexus · 日志中心")
    window.geometry("1100x760")
    window.minsize(880, 620)
    window.configure(bg="#252830")
    style = ttk.Style(window)
    p=palette()
    style.configure("Nexus.Treeview", background=p["terminal"], fieldbackground=p["terminal"], foreground=p["text"], rowheight=27, borderwidth=0)
    style.configure("Nexus.Treeview.Heading", background=p["field"], foreground=p["text"], relief="flat")
    style.map("Nexus.Treeview", background=[("selected",p["selection"])], foreground=[("selected",p["text"])])
    style.configure("Nexus.TNotebook", background=p["panel"], borderwidth=0)
    style.configure("Nexus.TNotebook.Tab", background=p["field"], foreground=p["text"], padding=(16,8))
    style.map("Nexus.TNotebook.Tab", background=[("selected",p["primary"])], foreground=[("selected",p["primary_text"])])
    window.columnconfigure(0, weight=1)
    window.rowconfigure(2, weight=1)
    label(window, "日志中心", font=("Microsoft YaHei UI", 15, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=12)
    filters = frame(window)
    filters.grid(row=1, column=0, sticky="ew", padx=18)
    variables = {}
    for index, (key, caption, choices) in enumerate((
        ("start", "开始日期", None), ("end", "结束日期", None),
        ("component", "插件", ["", "serial", "beken", "slogic", "workbench"]),
        ("kind", "事件", ["", "call", "result", "error", "rx", "tx", "finished", "output"]),
        ("client", "来源", None))):
        label(filters, caption, muted=True).grid(row=0, column=index, sticky="w")
        variable = variables[key] = tk.StringVar()
        widget = ttk.Combobox(filters, textvariable=variable, values=choices, width=14) if choices is not None else tk.Entry(
            filters, textvariable=variable, bg="#30343e", fg="#e3e6ed", insertbackground="#e3e6ed", width=16, relief="flat")
        widget.grid(row=1, column=index, sticky="ew", padx=(0, 8), pady=6)
        filters.columnconfigure(index, weight=1)
    label(filters, "日期 YYYY-MM-DD；来源填写 desktop / mcp-windows / wsl-skill 等完整标签。日期与来源可留空。", muted=True).grid(row=2, column=0, columnspan=5, sticky="w")
    notebook = ttk.Notebook(window, style="Nexus.TNotebook")
    notebook.grid(row=2, column=0, sticky="nsew", padx=18, pady=12)
    listing = frame(notebook)
    storage = frame(notebook)
    notebook.add(listing, text="在线历史")
    notebook.add(storage, text="存储与归档")
    listing.rowconfigure(0, weight=1)
    listing.columnconfigure(0, weight=1)
    tree = ttk.Treeview(listing, columns=("time", "component", "kind", "client", "text"), show="headings", selectmode="browse", style="Nexus.Treeview")
    for key, title, width in (("time", "时间", 180), ("component", "插件", 75), ("kind", "事件", 65), ("client", "来源", 110), ("text", "内容", 450)):
        tree.heading(key, text=title)
        tree.column(key, width=width, minwidth=50, stretch=key == "text")
    tree.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(listing, command=tree.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=scroll.set)
    detail = tk.Text(listing, height=7, bg="#23252b", fg="#e3e6ed", wrap="word", font=("Consolas", 10), state="disabled")
    detail.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    items, pagination = {}, {"next": None, "filters": {}, "generation": 0, "loading": False}
    feedback = label(window, "", muted=True)
    feedback.grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 12))
    def alive(): return bool(window.winfo_exists())
    def failed(error):
        pagination["loading"] = False
        if alive(): feedback.configure(text="操作失败：" + str(error))
    def arguments(): return {key: variable.get().strip() for key, variable in variables.items()}
    def show_detail(_=None):
        selected = tree.selection()
        if not selected: return
        detail.configure(state="normal")
        detail.delete("1.0", "end")
        detail.insert("end", json.dumps(items[selected[0]], ensure_ascii=False, indent=2))
        detail.configure(state="disabled")
    tree.bind("<<TreeviewSelect>>", show_detail)
    def load(reset=True):
        if pagination["loading"]: return
        if not reset and pagination["next"] is None: return
        if reset:
            pagination["filters"] = arguments()
            pagination["generation"] += 1
        generation = pagination["generation"]
        pagination["loading"] = True
        payload = dict(pagination["filters"], limit=200)
        if not reset: payload["before"] = pagination["next"]
        feedback.configure(text="正在查询共享历史…")
        def render(page):
            pagination["loading"] = False
            if not alive() or generation != pagination["generation"]: return
            if reset:
                tree.delete(*tree.get_children())
                items.clear()
            for item in page["events"]:
                identifier = str(item["id"])
                items[identifier] = item
                tree.insert("", "end", iid=identifier, values=(item["time"], item["component"], item["kind"], item.get("client", ""), item["text"].replace("\n", " ")[:300]))
            pagination["next"] = page["next_before"]
            feedback.configure(text=f"已显示 {len(items)} 条 · 在线历史按新到旧排列；更早记录见归档目录")
        background_request("logs.query", payload, render, failed)
    controls = frame(window)
    controls.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 8))
    button(controls, "查询", lambda: load(True), primary=True).pack(side="left")
    button(controls, "更早记录", lambda: load(False)).pack(side="left", padx=6)
    def calls_only():
        variables["kind"].set("call")
        load(True)
    button(controls, "调用记录", calls_only).pack(side="left")
    firmware = tk.BooleanVar(value=False)
    tk.Checkbutton(controls, text="导出含固件", variable=firmware, bg="#252830", fg="#e3e6ed", selectcolor="#30343e").pack(side="left", padx=12)
    def export():
        destination = filedialog.asksaveasfilename(parent=window, defaultextension=".zip", initialfile="EEDP-Nexus-日志.zip", filetypes=[("ZIP 归档", "*.zip")])
        if not destination: return
        feedback.configure(text="正在后台生成 ZIP；事件使用当前筛选，诊断和已完成烧录附件不使用筛选…")
        def completed(result):
            if alive(): feedback.configure(text="已导出：" + result.get("destination",result["path"]))
        background_request("logs.export", {"filters": arguments(), "include_firmware": firmware.get(), "destination":destination}, completed, failed)
    button(controls, "导出 ZIP", export).pack(side="right")
    summary = tk.Text(storage, height=9, bg="#23252b", fg="#e3e6ed", relief="flat", wrap="word", state="disabled")
    summary.pack(fill="both", expand=True, padx=12, pady=12)
    policy_row = frame(storage)
    policy_row.pack(fill="x", padx=12)
    policies = {}
    for index, (key, caption) in enumerate((("history_days", "在线保留天数"), ("archive_days", "归档保留天数"), ("max_mb", "总容量上限 MB"))):
        variable = policies[key] = tk.StringVar()
        label(policy_row, caption, muted=True).grid(row=0, column=index*2, padx=4)
        tk.Entry(policy_row, textvariable=variable, width=7).grid(row=0, column=index*2+1, padx=4)
    protected_history, protected_firmware = tk.BooleanVar(), tk.BooleanVar()
    for caption, variable in (("保护历史归档（不自动删除）", protected_history), ("保护固件快照（不自动删除）", protected_firmware)):
        tk.Checkbutton(storage, text=caption, variable=variable, bg="#252830", fg="#e3e6ed", selectcolor="#30343e").pack(anchor="w", padx=12)
    label(storage, "在线记录最多约 10 万条，超出先归档；容量清理仅处理未保护归档。\n运行中/最近烧录、在线数据库及导出包不自动删除。导出包由用户管理。", muted=True, justify="left").pack(anchor="w", padx=12, pady=6)
    storage_controls = frame(storage)
    storage_controls.pack(fill="x", padx=12, pady=12)
    def render_inventory(info):
        if not alive(): return
        lines = [f"日志根目录：{info['directory']}", f"在线事件：{info['events']:,} 条    总占用：{info['bytes']/1024**2:.2f} MB", f"时间范围：{info['first'] or '无'} — {info['last'] or '无'}"]
        names = dict(events="事件库及文本", flash="烧录任务", slogic="逻辑波形与解码", diagnostics="诊断", archives="归档", exports="导出包", other="其他")
        lines.extend(f"{names[key]}：{value['files']} 个文件，{value['bytes']/1024**2:.2f} MB" for key, value in info["categories"].items())
        if info["over_limit"]: lines.append("容量已超限：" + info["note"])
        summary.configure(state="normal")
        summary.delete("1.0", "end")
        summary.insert("end", "\n".join(lines))
        summary.configure(state="disabled")
    def refresh(): background_request("logs.inventory", {}, render_inventory, failed)
    def initialize_policy(policy):
        if not alive(): return
        for key, variable in policies.items(): variable.set(str(policy[key]))
        protected_history.set(policy["protect_history"])
        protected_firmware.set(policy["protect_firmware"])
    def save_policy():
        try: values = {key:int(variable.get()) for key, variable in policies.items()}
        except ValueError:
            failed("保留天数与容量请输入整数")
            return
        values.update(protect_history=protected_history.get(), protect_firmware=protected_firmware.get())
        if not values["protect_history"] or not values["protect_firmware"]:
            if not messagebox.askyesno("保存清理策略", "取消保护后，对应归档可能在到期或容量超限时自动删除。保存此策略？", parent=window): return
        background_request("logs.policy", values, lambda _: (refresh(), feedback.configure(text="策略已保存；后台每小时维护")) if alive() else None, failed)
    def maintain():
        def done(result):
            if not alive(): return
            render_inventory(result["inventory"])
            feedback.configure(text=f"归档事件 {result['archived_events']} 条、烧录任务 {result['archived_jobs']} 个；清理未保护归档 {result['deleted_archive_files']} 个文件")
        background_request("logs.maintain", {}, done, failed)
    button(storage_controls, "保存策略", save_policy, primary=True).pack(side="left")
    button(storage_controls, "执行归档维护", maintain).pack(side="left", padx=6)
    button(storage_controls, "刷新占用", refresh).pack(side="left")
    button(storage_controls, "打开日志目录", lambda: os.startfile(state_directory / "logs")).pack(side="right")
    def open_archives():
        path = state_directory / "logs/archives"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)
    button(storage_controls, "打开归档", open_archives).pack(side="right", padx=6)
    background_request("logs.policy", {}, initialize_policy, failed)
    refresh()
    load()
    return window
