from pathlib import Path
import tkinter as tk
from tkinter import ttk
import unittest

from api import dispatch
from core import Activity, Registry, Resources
from log_center import open_log_center
from settings import Settings
from test_desktop import DesktopTemp


class LogCenterTest(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()
    def test_history_calls_filter_pagination_and_storage_load(self):
        with DesktopTemp() as temporary:
            directory = Path(temporary)
            registry = Registry(Activity(directory / "logs"), Resources(), Settings(directory / "settings.json"))
            registry.activity.emit("serial", "call", "historical call", client="wsl-test")
            registry.activity.emit("serial", "rx", "received")
            root = tk.Tk()
            root.withdraw()
            failures, requests = [], []
            def background(method, params, success=None, failure=None):
                requests.append((method, params))
                def deliver():
                    try:
                        result = dispatch(registry, method, params)
                        if success: success(result)
                    except Exception as exc:
                        failures.append(exc)
                        if failure: failure(str(exc))
                root.after(10, deliver)
            def frame(parent, **kwargs): return tk.Frame(parent, **kwargs)
            def label(parent, text="", muted=False, **kwargs): return tk.Label(parent, text=text, **kwargs)
            def button(parent, text, command, **kwargs): return tk.Button(parent, text=text, command=command)
            window = open_log_center(root, background, directory, frame, label, button)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            def first():
                try:
                    tree = next(w for w in descendants(window) if isinstance(w, ttk.Treeview))
                    self.assertEqual(len(tree.get_children()), 2)
                    next(w for w in descendants(window) if isinstance(w, tk.Button) and w.cget("text") == "调用记录").invoke()
                except Exception as exc: failures.append(exc)
                root.after(100, second)
            def second():
                try:
                    tree = next(w for w in descendants(window) if isinstance(w, ttk.Treeview))
                    self.assertEqual(len(tree.get_children()), 1)
                    self.assertEqual(tree.item(tree.get_children()[0])["values"][2], "call")
                    self.assertTrue(any(method == "logs.inventory" for method, _ in requests))
                    self.assertFalse(any(method == "logs.maintain" for method, _ in requests))
                except Exception as exc: failures.append(exc)
                root.destroy()
            root.after(150, first)
            try: root.mainloop()
            finally: registry.close()
            if failures: raise failures[0]
