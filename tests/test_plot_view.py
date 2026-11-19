import importlib.util
from pathlib import Path
import time
import tkinter as tk
import unittest
from unittest.mock import patch
from nexus_ui.plot_view import open_plot_view
from nexus_ui import desktop

path=Path(__file__).resolve().parents[1]/"plugins/plot/component.py"
spec=importlib.util.spec_from_file_location("plot_view_component",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PlotViewTest(unittest.TestCase):
    def test_desktop_opens_component_and_routes_serial_events(self):
        component=module.Plot(None,None)
        errors=[]
        original=tk.Tk
        delivered=[]
        def request(method,args=None):
            args=args or {}
            if method=="settings.get":return {"selected":"plot"} if args.get("scope")=="ui" else {}
            if method=="settings.update":return args.get("values",{})
            if method=="status":return {"components":{"plot":{},"serial":{}}}
            if method=="tools":return [dict(id="plot",name="数据波形"),dict(id="serial",name="串口")]
            if method=="events":
                if delivered:return dict(events=[],cursor=1,dropped=False)
                delivered.append(True)
                return dict(events=[dict(id=1,component="serial",kind="rx",text="@plot v=1\n@plot v=2\n")],cursor=1,dropped=False)
            if method=="call":
                if args["target"]=="serial.ports":return []
                if args["target"].startswith("plot."):
                    return getattr(component,args["target"].split(".")[1])(**args["arguments"])
            raise ValueError(method)
        class Root(original):
            def __init__(self):
                super().__init__()
                self.after(1500,self.check)
                self.after(5000,self.finish)
            def check(self):
                try:
                    self.update_idletasks()
                    if len(component.samples()["points"])!=2:raise AssertionError("Serial data did not reach the plot")
                except Exception as exc:errors.append(exc)
                self.finish()
            def finish(self):
                if self.winfo_exists():self.tk.call(self.protocol("WM_DELETE_WINDOW"))
        import tempfile
        artifacts=Path(__file__).resolve().parents[1]/"build/test-artifacts"
        artifacts.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=artifacts) as directory,patch.object(tk,"Tk",Root):
            desktop.launch(request,lambda:None,Path(directory))
        if errors:raise errors[0]

    def test_serial_chunks_are_plotted_without_opening_hardware(self):
        root=tk.Tk()
        root.geometry("900x600")
        component=module.Plot(None,None)
        calls=[]
        def background(method,params,success=None,failure=None):
            calls.append(params["target"])
            action=params["target"].split(".")[1]
            value=getattr(component,action)(**params["arguments"])
            if success:root.after(5,lambda:success(value))
        def frame(parent,bg="#252830",**kw):return tk.Frame(parent,bg=bg,**kw)
        def label(parent,text="",muted=False,**kw):return tk.Label(parent,text=text,**kw)
        def button(parent,text,command,**kw):return tk.Button(parent,text=text,command=command)
        try:
            view=open_plot_view(root,background,frame,label,button)
            view.pack(fill="both",expand=True)
            view.consume_event(dict(component="serial",kind="rx",text="@plot v=1"))
            view.consume_event(dict(component="serial",kind="rx",text="\n@plot v=2\n"))
            end=time.monotonic()+.5
            while time.monotonic()<end:
                root.update()
                time.sleep(.005)
            canvas=next(w for w in view.winfo_children() if isinstance(w,tk.Canvas))
            self.assertEqual(len(component.samples()["points"]),2)
            self.assertTrue(any(canvas.type(item)=="line" and canvas.itemcget(item,"width")=="2.0" for item in canvas.find_all()))
            self.assertTrue(set(calls)<={"plot.feed","plot.samples"})
        finally:root.destroy()
