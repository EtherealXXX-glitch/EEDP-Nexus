"""Exercise GUI callbacks without showing a window or touching a physical port."""
import base64
from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import desktop


class DesktopTemp(tempfile.TemporaryDirectory):
    def __init__(self):
        directory = Path(__file__).parent / "build/test-artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        super().__init__(dir=directory)

    def cleanup(self):
        # Windows scanners can briefly keep a newly-created diagnostic directory open.
        for attempt in range(30):
            try:
                return super().cleanup()
            except PermissionError:
                if attempt == 29: raise
                time.sleep(.1)


class DesktopTest(unittest.TestCase):
    def test_real_menu_entries_open_inline_help_about_and_service_status(self):
        original=tk.Tk
        failures=[]
        with DesktopTemp() as temporary:
            directory=Path(temporary)
            def request(method,args=None):
                if method=="settings.get":return {}
                if method=="settings.update":return args["values"]
                if method=="tools":return []
                if method=="events":return dict(events=[],cursor=0,dropped=False)
                if method=="status":return dict(version="test",logs=str(directory),resources={},components={"serial":{"connected":False},"beken":{"state":"idle"}})
                if method=="call":return []
                raise ValueError(method)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            class Root(original):
                def __init__(self):
                    super().__init__()
                    self.after(300,self.first)
                    self.after(4000,self.finish)
                def first(self):
                    try:
                        native=self._nexus_icon
                        for kind in (0,1):
                            actual=native.user.SendMessageW(native.handle,0x7f,kind,0)
                            if actual not in native.icons.values():raise AssertionError("Startup replaced native Nexus icon")
                        if not self._nexus_default_icons:raise AssertionError("Tk default icon missing")
                        names={w.cget("text"):w for w in descendants(self) if isinstance(w,tk.Menubutton)}
                        self.assert_names(names)
                        menu=self.nametowidget(names["帮助"].cget("menu"))
                        menu.invoke(0)
                        menu.invoke(2)
                        next(w for w in descendants(self) if isinstance(w,tk.Button) and "Agent 桥接" in w.cget("text")).invoke()
                        self.after(200,self.second)
                    except Exception as exc:failures.append(exc);self.finish()
                def assert_names(self,names):
                    if set(names)!={"文件","视图","设备","工具","帮助"}:raise AssertionError(names)
                def second(self):
                    try:
                        if any(isinstance(w,tk.Toplevel) for w in descendants(self)):raise AssertionError("Menus opened popups")
                        if not any(isinstance(w,tk.Label) and "后台版本 test" in w.cget("text") for w in descendants(self)):raise AssertionError("Service data missing")
                    except Exception as exc:failures.append(exc)
                    self.finish()
                def finish(self):
                    if self.winfo_exists():self.tk.call(self.protocol("WM_DELETE_WINDOW"))
            with patch.object(tk,"Tk",Root):desktop.launch(request,lambda:None,directory)
        if failures:raise failures[0]

    def test_components_disappear_pages_reuse_and_logs_open_at_bottom(self):
        original_tk=tk.Tk
        failures=[]
        enabled={"serial":True,"beken":True}
        delivered=False
        def request(method,arguments=None):
            nonlocal delivered
            if method=="settings.get":return {}
            if method=="settings.update":return arguments["values"]
            if method=="status":return {"components":{key:{"state":"idle"} for key,value in enabled.items() if value}}
            if method=="plugins.list":return [dict(id=key,name=key,version="1.1.0",enabled=value) for key,value in enabled.items()]
            if method=="tools":return []
            if method=="events":
                page=[] if delivered else [dict(id=n,component="serial",kind="rx",text=f"line {n}\n",base64="",time="2026-11-11T00:00:00") for n in range(600)]
                delivered=True
                return dict(events=page,cursor=600,dropped=False)
            if method=="call":return []
            raise ValueError(method)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        class Root(original_tk):
            def __init__(self):
                super().__init__()
                self.after(600,self.first)
                self.after(6000,self.finish)
            def button(self,caption):return next(w for w in descendants(self) if isinstance(w,tk.Button) and caption in w.cget("text"))
            def guarded(self,fn):
                try:fn()
                except Exception as exc:failures.append(exc);self.finish()
            def first(self):
                def action():
                    for _ in range(3):self.button("组件管理").invoke()
                    for _ in range(3):self.button("设置").invoke()
                    if any(isinstance(w,tk.Toplevel) for w in descendants(self)):raise AssertionError("Repeated clicks created popups")
                    enabled["beken"]=False
                    self.after(600,self.second)
                self.guarded(action)
            def second(self):
                def action():
                    if self.button("Beken 烧录").winfo_manager():raise AssertionError("Disabled component still shown")
                    self.button("串口监控").invoke()
                    self.after(700,self.third)
                self.guarded(action)
            def third(self):
                def action():
                    terminal=next(w for w in descendants(self) if isinstance(w,tk.Text) and str(w.cget("state"))=="disabled")
                    terminal=next(w for w in descendants(self) if getattr(w,"_nexus_log_terminal",False))
                    if terminal.yview()[1] < .99:raise AssertionError("Switch did not settle at log tail")
                    self.finish()
                self.guarded(action)
            def finish(self):
                if self.winfo_exists():self.tk.call(self.protocol("WM_DELETE_WINDOW"))
        with DesktopTemp() as temp,patch.object(tk,"Tk",Root):desktop.launch(request,lambda:None,Path(temp))
        if failures:raise failures[0]

    def test_small_window_keeps_sender_visible_and_sidebar_resizes(self):
        original_tk = tk.Tk
        failures = []
        def request(method, arguments=None):
            if method == "settings.get": return {}
            if method == "settings.update": return arguments["values"]
            if method == "events": return dict(events=[], cursor=0, dropped=False)
            if method == "status": return {"components": {"serial": {}, "beken": {}}}
            return []
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        class TestRoot(original_tk):
            def __init__(self):
                super().__init__()
                self.after(200, self.check_layout)
            def check_layout(self):
                try:
                    self.geometry("1000x560")
                    self.update_idletasks()
                    pane = next(w for w in descendants(self) if isinstance(w, tk.PanedWindow))
                    pane.sash_place(0, 360, 0)
                    self.update_idletasks()
                    if abs(pane.sash_coord(0)[0] - 360) > 2:
                        raise AssertionError("sidebar did not resize")
                    editor = next(w for w in descendants(self) if isinstance(w, tk.Text) and str(w.cget("state")) == "normal")
                    if not editor.winfo_viewable() or editor.winfo_height() < 50:
                        raise AssertionError("sender was squeezed out")
                    if editor.winfo_rooty() + editor.winfo_height() > self.winfo_rooty() + self.winfo_height():
                        raise AssertionError("sender extends below window")
                except Exception as exc:
                    failures.append(exc)
                self.tk.call(self.protocol("WM_DELETE_WINDOW"))
        with DesktopTemp() as temp, patch.object(tk, "Tk", TestRoot):
            desktop.launch(request, lambda: None, Path(temp))
        if failures: raise failures[0]

    def test_serial_presets_and_narrow_send_button(self):
        original = tk.Tk
        failures, writes, calls = [], [], []
        def request(method, args=None):
            if method == "settings.get": return {}
            if method == "settings.update":
                writes.append(args["values"])
                return args["values"]
            if method == "status": return {"components": {"serial": {"connected": False}}}
            if method == "events": return dict(events=[], cursor=0, dropped=False)
            if method == "call":
                calls.append(args)
                if args.get("target") == "serial.ports": return [dict(port="COM16", description="USB-SERIAL CH340 (COM16)")]
                return []
            if method in ("tools", "plugins.list"): return []
            raise ValueError(method)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        class Root(original):
            def __init__(self):
                super().__init__()
                self.after(400, self.exercise)
                self.after(5000, self.finish)
            def exercise(self):
                try:
                    widgets = list(descendants(self))
                    port_box = next(w for w in widgets if isinstance(w, desktop.ttk.Combobox) and any("CH340" in value for value in w.cget("values")))
                    port_box.current(0)
                    port_box.event_generate("<<ComboboxSelected>>")
                    if port_box.get() != "COM16": raise AssertionError("port selection included device description")
                    if not any(isinstance(w, tk.Label) and "CH340" in w.cget("text") for w in widgets): raise AssertionError("device description missing")
                    modes = [w for w in widgets if isinstance(w, tk.Checkbutton) and w.cget("text") in ("命令行模式", "HEX 发送")]
                    if len(modes) != 2 or modes[0].master != modes[1].master: raise AssertionError("send settings are not together")
                    ending = next(w for w in widgets if isinstance(w, desktop.ttk.Combobox) and "CRLF" in w.cget("values"))
                    if ending.master.master != modes[0].master: raise AssertionError("ending is outside send settings")
                    if any(isinstance(w, tk.Label) and "Ctrl + Enter 发送" in w.cget("text") for w in widgets): raise AssertionError("send hint remains")
                    command = next(w for w in modes if w.cget("text") == "命令行模式")
                    hex_mode = next(w for w in modes if w.cget("text") == "HEX 发送")
                    command.invoke()
                    hex_mode.invoke()
                    if self.getboolean(self.getvar(command.cget("variable"))) or not self.getboolean(self.getvar(hex_mode.cget("variable"))): raise AssertionError("send modes were not made exclusive")
                    hex_mode.invoke()
                    if any(isinstance(w, tk.Button) and w.cget("text") in ("Ctrl+C", "Ctrl+D", "Ctrl+Z") for w in widgets): raise AssertionError("control buttons remain")
                    editor = next(w for w in widgets if isinstance(w, tk.Text) and int(w.cget("height")) == 3)
                    buttons = [w for w in widgets if isinstance(w, tk.Button) and "发送" in w.cget("text")]
                    if len(buttons) != 1: raise AssertionError("expected one send button")
                    button = buttons[0]
                    row = editor.master
                    row.configure(width=250)
                    row.pack_propagate(False)
                    self.update_idletasks()
                    if button.winfo_width() < button.winfo_reqwidth(): raise AssertionError("send button clipped")
                    editor.insert("1.0", "AT+TEST")
                    next(w for w in widgets if isinstance(w, tk.Button) and w.cget("text") == "保存命令").invoke()
                    editor.delete("1.0", "end")
                    box = next(w for w in widgets if isinstance(w, desktop.ttk.Combobox) and "sample" in w.cget("values"))
                    box.set("sample")
                    box.event_generate("<<ComboboxSelected>>")
                    if editor.get("1.0", "end-1c") != "AT+TEST": raise AssertionError("preset not loaded")
                    if any(c.get("target") == "serial.send" for c in calls): raise AssertionError("preset sent automatically")
                    self.after(300, self.finish)
                except Exception as exc:
                    failures.append(exc)
                    self.finish()
            def finish(self):
                if self.winfo_exists(): self.tk.call(self.protocol("WM_DELETE_WINDOW"))
        with DesktopTemp() as temp, patch.object(tk, "Tk", Root), patch.object(desktop.simpledialog, "askstring", return_value="sample"):
            desktop.launch(request, lambda: None, Path(temp))
        if failures: raise failures[0]
        self.assertTrue(any(p.get("serial_presets", {}).get("sample", {}).get("text") == "AT+TEST" for p in writes))

    def test_component_navigation_send_save_clear_and_inspect(self):
        calls, failures = [], []
        lock = threading.Lock()
        original_tk = tk.Tk
        temp = DesktopTemp()
        log_path = Path(temp.name) / "saved.log"
        delivered = False

        def fake_request(method, arguments=None):
            nonlocal delivered
            arguments = arguments or {}
            if method == "status":
                return {"components": {"serial": {"connected": True, "port": "loop://", "baudrate": 1500000,
                        "rx_bytes": 5, "tx_bytes": 0}, "beken": {"state": "idle", "stage": "等待任务"}}}
            if method == "events":
                with lock:
                    page = [] if delivered else [dict(id=1, component="serial", kind="rx", text="hello\n",
                        base64=base64.b64encode(b"hello\n").decode(), time="2026-11-10T16:00:00.000")]
                    delivered = True
                return dict(events=page, cursor=1, dropped=False)
            if method == "call":
                with lock: calls.append(arguments)
                target = arguments["target"]
                if target == "serial.ports": return [{"port": "loop://"}]
                if target == "serial.send": return dict(sent=6)
                if target == "beken.inspect": return dict(firmware="test.bin", length=512, sha256="abc", address="0x0")
            raise ValueError(method)

        def children(widget):
            result = []
            for child in widget.winfo_children():
                result.append(child)
                result.extend(children(child))
            return result

        class HiddenRoot(original_tk):
            def __init__(self):
                super().__init__()
                self.withdraw()
                self.after(500, self.first)
                self.after(5000, self.finish)

            def guarded(self, action):
                try: action()
                except Exception as exc:
                    failures.append(exc)
                    self.finish()

            def find_button(self, text):
                return next(w for w in children(self) if isinstance(w, tk.Button) and text in str(w.cget("text")))

            def first(self):
                def action():
                    texts = [w for w in children(self) if isinstance(w, tk.Text)]
                    terminal = next(w for w in texts if str(w.cget("state")) == "disabled")
                    self.assert_in("hello", terminal.get("1.0", "end"))
                    self.find_button("保存显示").invoke()
                    self.assert_in("hello", log_path.read_text(encoding="utf-8"))
                    self.find_button("清空显示").invoke()
                    if terminal.get("1.0", "end").strip():
                        raise AssertionError("clear display left visible data")
                    editor = next(w for w in texts if int(w.cget("height")) == 3)
                    next(w for w in children(self) if isinstance(w, tk.Checkbutton) and w.cget("text") == "命令行模式").invoke()
                    editor.insert("1.0", "ping")
                    self.find_button("发送").invoke()
                    if editor.get("1.0", "end-1c"):
                        raise AssertionError("command editor was not cleared")
                    self.after(300, self.second)
                self.guarded(action)

            def second(self):
                def action():
                    self.find_button("Beken 烧录").invoke()
                    self.find_button("预检固件").invoke()
                    self.after(300, self.third)
                self.guarded(action)

            def third(self):
                def action():
                    terminal = next(w for w in children(self) if isinstance(w, tk.Text) and str(w.cget("state")) == "disabled")
                    self.assert_in("SHA-256", terminal.get("1.0", "end"))
                    self.find_button("串口监控").invoke()
                    self.after(200, self.finish)
                self.guarded(action)

            def assert_in(self, fragment, value):
                if fragment not in value: raise AssertionError(f"missing {fragment!r} in {value!r}")

            def finish(self):
                self.tk.call(self.protocol("WM_DELETE_WINDOW"))

        with patch.object(tk, "Tk", HiddenRoot), patch.object(desktop.filedialog, "asksaveasfilename", return_value=str(log_path)):
            desktop.launch(fake_request, lambda: None, Path(temp.name))
        temp.cleanup()
        if failures: raise failures[0]
        targets = [x["target"] for x in calls]
        self.assertIn("serial.send", targets)
        self.assertIn("beken.inspect", targets)
        sent = next(x for x in calls if x["target"] == "serial.send")
        self.assertEqual(sent["arguments"]["text"], "ping")
        self.assertNotIn("beken.start", targets)

    def test_clicks_and_close_stay_responsive_with_logs_and_slow_settings(self):
        original_tk = tk.Tk
        delivered = False
        ticks = []
        delays = []
        completed = threading.Event()
        temp = DesktopTemp()
        def fake_request(method, arguments=None):
            nonlocal delivered
            if method == "settings.get": return {}
            if method == "settings.update":
                time.sleep(.6)
                completed.set()
                return arguments["values"]
            if method == "status":
                return {"components":{"serial":{"connected":False},"beken":{"state":"idle"}}}
            if method == "events":
                page = [] if delivered else [dict(id=n, component="serial", kind="rx", text=("log "*200)+"\n",
                    base64="",time="2026-11-10T17:00:00.000") for n in range(3000)]
                delivered = True
                return dict(events=page,cursor=3000,dropped=False)
            if method == "call": return []
            raise ValueError(method)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        class HiddenRoot(original_tk):
            def __init__(self):
                super().__init__()
                self.withdraw()
                self.after(50,self.beat)
                self.after(200,lambda:self.click("Beken"))
                self.after(400,lambda:self.click("串口监控"))
                self.after(700,lambda:self.tk.call(self.protocol("WM_DELETE_WINDOW")))
            def beat(self):
                ticks.append(time.perf_counter())
                self.after(20,self.beat)
            def click(self, caption):
                button=next(w for w in descendants(self) if isinstance(w,tk.Button) and caption in w.cget("text"))
                start=time.perf_counter()
                button.invoke()
                delays.append(time.perf_counter()-start)
        with patch.object(tk,"Tk",HiddenRoot):
            desktop.launch(fake_request,lambda:None,Path(temp.name))
        self.assertTrue(completed.wait(2))
        temp.cleanup()
        self.assertGreater(len(ticks),20)
        self.assertLess(max(delays),.25,delays)
        self.assertLess(max(b-a for a,b in zip(ticks,ticks[1:])),.35)


if __name__ == "__main__":
    unittest.main()
