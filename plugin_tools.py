"""Schema-driven plugin panel. New components do not need a hardcoded main tab."""
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def open_plugin_tools(root, identifier, background_request, frame, label, button, embedded=False):
    window = tk.Frame(root) if embedded else tk.Toplevel(root)
    if not embedded:
        window.title("EEDP Nexus · 组件操作")
        window.geometry("850x740")
    window.configure(bg="#252830")
    label(window, "组件操作 · " + identifier, font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=18, pady=12)
    label(window, "按插件公开的参数调用；状态与结果在 Windows / WSL Agent 间共享。", muted=True).pack(anchor="w", padx=18)
    selector = tk.StringVar()
    combo = ttk.Combobox(window, textvariable=selector, state="readonly")
    combo.pack(fill="x", padx=18, pady=12)
    parameters = frame(window)
    parameters.pack(fill="x", padx=18)
    parameters.columnconfigure(1, weight=1)
    feedback = label(window, "正在加载组件接口…", muted=True)
    feedback.pack(fill="x", padx=18, pady=8)
    controls = frame(window)
    controls.pack(fill="x", padx=18)
    result = tk.Text(window, bg="#23252b", fg="#e3e6ed", font=("Consolas", 10), wrap="word", state="disabled")
    result.pack(fill="both", expand=True, padx=18, pady=12)
    actions, fields = {}, {}
    busy = False
    timer = None
    def alive(): return bool(window.winfo_exists())
    def render(value):
        nonlocal busy
        busy = False
        if not alive(): return
        result.configure(state="normal")
        result.delete("1.0", "end")
        result.insert("end", json.dumps(value, ensure_ascii=False, indent=2))
        result.configure(state="disabled")
        feedback.configure(text="任务仍在运行，可刷新状态" if isinstance(value, dict) and value.get("state") == "running" else "操作完成")
    def failed(error):
        nonlocal busy
        busy = False
        if alive(): feedback.configure(text="操作失败："+str(error))
    def form(_=None):
        fields.clear()
        for child in parameters.winfo_children(): child.destroy()
        action = actions.get(selector.get())
        if not action: return
        for row, definition in enumerate(action[1].get("fields", [])):
            name = definition["name"]
            label(parameters, definition["label"], muted=True).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            variable = tk.BooleanVar(value=definition["default"]) if definition["type"] == "bool" else tk.StringVar(value=str(definition["default"]))
            fields[name] = (variable, definition)
            if definition["type"] == "bool":
                widget = tk.Checkbutton(parameters, variable=variable, bg="#252830", selectcolor="#30343e")
            elif definition.get("choices"):
                widget = ttk.Combobox(parameters, textvariable=variable, values=definition["choices"], state="readonly")
            else:
                widget = tk.Entry(parameters, textvariable=variable, bg="#30343e", fg="#e3e6ed", insertbackground="#e3e6ed", relief="flat")
            widget.grid(row=row, column=1, sticky="ew", pady=4, ipady=5)
            if name in ("input", "firmware", "engine"):
                def choose(value=variable):
                    path = filedialog.askopenfilename(parent=window)
                    if path: value.set(path)
                button(parameters, "浏览", choose, small=True).grid(row=row, column=2, padx=(6, 0))
    def execute():
        nonlocal busy
        if busy or selector.get() not in actions: return
        name, definition = actions[selector.get()]
        try:
            values = {}
            for key, (variable, field) in fields.items():
                value = variable.get()
                values[key] = int(value) if field["type"] == "int" else float(value) if field["type"] == "float" else value
        except ValueError:
            failed("数字参数格式错误")
            return
        if definition.get("destructive"):
            if not messagebox.askyesno("确认组件操作", f"执行 {identifier}.{name}？\n\n" + json.dumps(values, ensure_ascii=False, indent=2), parent=window): return
        busy = True
        feedback.configure(text="正在执行 " + name)
        background_request("call", {"target":identifier+"."+name, "arguments":values}, render, failed)
    def status():
        if not alive(): return
        background_request("call", {"target":identifier+".status", "arguments":{}}, render, failed)
    def loaded(components):
        if not alive(): return
        component = next((c for c in components if c["id"] == identifier), None)
        if component is None:
            failed("组件已禁用或移除")
            return
        for key, definition in component["actions"].items(): actions[definition["label"]+" · "+key] = (key, definition)
        combo.configure(values=list(actions))
        if actions:
            selector.set(next(iter(actions)))
            form()
        feedback.configure(text=component["description"])
    combo.bind("<<ComboboxSelected>>", form)
    button(controls, "执行", execute, primary=True).pack(side="left")
    button(controls, "刷新任务状态", status).pack(side="left", padx=8)
    background_request("tools", {}, loaded, failed)
    return window
