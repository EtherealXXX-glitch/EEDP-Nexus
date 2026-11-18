from pathlib import Path
import tkinter as tk
import unittest

from nexus_ui.logic_view import open_logic_view


class LogicViewTest(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()
    def test_coarse_overview_is_replaced_after_rapid_zoom(self):
        import time
        root=tk.Tk()
        root.geometry("1000x700")
        requests=[]
        def background(method,params,success=None,failure=None):
            if method=="settings.get":value={}
            elif params["target"]=="slogic.status":value={"state":"idle"}
            elif params["target"]=="slogic.waveform":
                args=params["arguments"]
                requests.append(args.copy())
                start=args["start_sample"]
                count=args["sample_count"] or 1600000
                step=max(1,(count+args["pixels"]-1)//args["pixels"])
                level=[0,1] if count==1600000 else [0,0]
                value=dict(input="synthetic.sr",total_samples=1600000,samplerate=16000000,
                           start_sample=start,sample_count=count,bin_samples=step,exact=step==1,
                           channels=[dict(name="D0",ranges=[level]*((count+step-1)//step))])
            else:raise AssertionError("Unexpected hardware action")
            if success:root.after(80,lambda:success(value))
        def frame(parent,bg="#252830",**kwargs):return tk.Frame(parent,bg=bg,**kwargs)
        def label(parent,text="",muted=False,**kwargs):return tk.Label(parent,text=text,**kwargs)
        def button(parent,text,command,**kwargs):return tk.Button(parent,text=text,command=command)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def settle(seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                root.update()
                time.sleep(.005)
        try:
            view=open_logic_view(root,background,frame,label,button,embedded=True)
            view.pack(fill="both",expand=True)
            settle(.2)
            view.consume_status(dict(id="test",state="succeeded",kind="capture",output="synthetic.sr",finished=1))
            settle(.3)
            canvas=next(w for w in descendants(view) if isinstance(w,tk.Canvas) and any(w.type(i)=="rectangle" for i in w.find_all()))
            for _ in range(8):canvas.event_generate("<MouseWheel>",x=300,y=100,delta=120,state=4)
            settle(.8)
            self.assertGreaterEqual(len(requests),2)
            self.assertGreater(requests[-1]["sample_count"],0)
            self.assertFalse(any(canvas.type(i)=="rectangle" for i in canvas.find_all()),"Coarse overview remained after detailed data arrived")
        finally:root.destroy()

    def test_waveform_navigation_and_six_time_markers(self):
        import time
        root=tk.Tk()
        root.geometry("1200x800")
        waveform=dict(input="synthetic.sr",total_samples=500,samplerate=1000000,start_sample=0,
            sample_count=500,bin_samples=1,exact=True,channels=[dict(name="D0",ranges=[[i%2,i%2] for i in range(500)])])
        saved=[]
        def background(method,params,success=None,failure=None):
            if method=="settings.get": value={}
            elif method=="settings.update":
                saved.append(params)
                value=params["values"]
            elif params["target"]=="slogic.status": value=dict(state="idle")
            elif params["target"]=="slogic.waveform": value=waveform
            else: raise AssertionError("Unexpected hardware action")
            if success: root.after(1,lambda:success(value))
        def frame(parent,bg="#252830",**kwargs): return tk.Frame(parent,bg=bg,**kwargs)
        def label(parent,text="",muted=False,**kwargs): return tk.Label(parent,text=text,**kwargs)
        def button(parent,text,command,**kwargs): return tk.Button(parent,text=text,command=command)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def settle():
            until=time.monotonic()+.12
            while time.monotonic()<until:
                root.update()
                time.sleep(.005)
        try:
            view=open_logic_view(root,background,frame,label,button,embedded=True)
            view.pack(fill="both",expand=True)
            settle()
            view.consume_status(dict(id="test",state="succeeded",kind="capture",output="synthetic.sr",finished=1))
            settle()
            widgets=list(descendants(view))
            canvas=next(w for w in widgets if isinstance(w,tk.Canvas) and len(w.find_all())>10)
            buttons={w.cget("text"):w for w in widgets if isinstance(w,tk.Button)}
            from tkinter import ttk
            side_box=next(w for w in widgets if isinstance(w,ttk.Combobox))
            old_value=side_box.get()
            side_box.event_generate("<MouseWheel>",delta=-120)
            self.assertEqual(side_box.get(),old_value)
            buttons["通道名称"].invoke()
            dialog=next(w for w in descendants(root) if isinstance(w,tk.Toplevel))
            entries=[w for w in descendants(dialog) if isinstance(w,tk.Entry)]
            entries[0].insert(0,"TX")
            next(w for w in descendants(dialog) if isinstance(w,tk.Button) and w.cget("text")=="保存").invoke()
            settle()
            self.assertEqual(saved[-1]["values"]["channel_names"],{"D0":"TX"})
            self.assertTrue(any(canvas.itemcget(item,"text")=="D0 · TX" for item in canvas.find_all() if canvas.type(item)=="text"))
            self.assertFalse(any(isinstance(w,tk.Label) and "协议 / 引脚映射" in w.cget("text") for w in widgets))
            canvas.event_generate("<ButtonPress-1>",x=100,y=100)
            canvas.event_generate("<ButtonRelease-1>",x=100,y=100)
            self.assertEqual(len(canvas.find_withtag("marker")),0)
            for _ in range(7): buttons["添加标尺"].invoke()
            self.assertEqual(len(canvas.find_withtag("marker-line")),6)
            self.assertEqual(len(canvas.find_withtag("marker-flag")),6)
            self.assertEqual(len({canvas.itemcget(item,"fill") for item in canvas.find_withtag("marker-flag")}),6)
            marker=canvas.find_withtag("marker-line")[0]
            before=canvas.coords(marker)[0]
            canvas.event_generate("<ButtonPress-1>",x=round(before),y=120)
            canvas.event_generate("<B1-Motion>",x=round(before)+30,y=120)
            canvas.event_generate("<ButtonRelease-1>",x=round(before)+30,y=120)
            self.assertGreater(canvas.coords(canvas.find_withtag("marker-line")[0])[0],before+20)
            marker_text=canvas.itemcget(canvas.find_withtag("marker-label")[0],"text")
            status=next(w for w in widgets if isinstance(w,tk.Label) and w.cget("text").startswith("标尺 1"))
            marker_time=status.cget("text")
            canvas.event_generate("<MouseWheel>",x=200,y=120,delta=120,state=4)
            settle()
            self.assertEqual(canvas.itemcget(canvas.find_withtag("marker-label")[0],"text"),marker_text)
            zoomed=canvas.coords(canvas.find_withtag("marker-line")[0])[0]
            canvas.event_generate("<Motion>",x=round(zoomed),y=100)
            self.assertEqual(status.cget("text"),marker_time)
            canvas.event_generate("<MouseWheel>",x=200,y=120,delta=-120)
            settle()
            self.assertNotEqual(canvas.coords(canvas.find_withtag("marker-line")[0])[0],zoomed)
            canvas.event_generate("<ButtonPress-1>",x=600,y=150)
            canvas.event_generate("<B1-Motion>",x=500,y=150)
            canvas.event_generate("<ButtonRelease-1>",x=500,y=150)
            settle()
            marker=canvas.find_withtag("marker-line")[0]
            x=round(canvas.coords(marker)[0])
            canvas.event_generate("<Button-3>",x=x,y=100)
            self.assertLess(len(canvas.find_withtag("marker-line")),6)
            buttons["清除标尺"].invoke()
            self.assertEqual(len(canvas.find_withtag("marker")),0)
            buttons["高度 +"].invoke()
            buttons["高度 −"].invoke()
        finally:
            root.destroy()

    def test_embedded_waveform_zoom_and_external_agent_results(self):
        root=tk.Tk()
        root.geometry("1200x800")
        requests,failures=[],[]
        waveform=dict(input="synthetic.sr",total_samples=500,samplerate=1000000,start_sample=0,
            sample_count=500,bin_samples=1,exact=True,channels=[dict(name="D0",ranges=[[i%2,i%2] for i in range(500)])])
        def background(method,params,success=None,failure=None):
            requests.append((method,params))
            if method=="settings.get": value={}
            elif params["target"]=="slogic.status": value=dict(state="idle")
            elif params["target"]=="slogic.waveform": value=waveform
            else: raise AssertionError("Viewer tried to change hardware")
            if success: root.after(5,lambda:success(value))
        def frame(parent,bg="#252830",**kwargs):return tk.Frame(parent,bg=bg,**kwargs)
        def label(parent,text="",muted=False,**kwargs):return tk.Label(parent,text=text,**kwargs)
        def button(parent,text,command,**kwargs):return tk.Button(parent,text=text,command=command)
        view=open_logic_view(root,background,frame,label,button,embedded=True)
        view.pack(fill="both",expand=True)
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        def first():
            view.consume_status(dict(id="agent-capture",state="succeeded",kind="capture",output="synthetic.sr",finished=1,stage="done"))
            root.after(200,second)
        def second():
            try:
                canvas=next(w for w in descendants(view) if isinstance(w,tk.Canvas) and len(w.find_all())>10)
                self.assertGreater(len(canvas.find_all()),10)
                canvas.event_generate("<MouseWheel>",x=200,y=100,delta=120,state=4)
                view.consume_status(dict(id="agent-decode",state="succeeded",kind="decode",preview="OK",finished=2))
                self.assertFalse(any(isinstance(w,tk.Text) for w in descendants(view)))
                self.assertFalse(any(isinstance(w,tk.Toplevel) for w in descendants(root)))
                self.assertFalse(any(params.get("target")=="slogic.start" for method,params in requests))
            except Exception as exc:failures.append(exc)
            def finish():
                try:self.assertEqual(sum(params.get("target")=="slogic.waveform" for method,params in requests),1)
                except Exception as exc:failures.append(exc)
                root.destroy()
            root.after(200,finish)
        root.after(100,first)
        root.mainloop()
        if failures:raise failures[0]
