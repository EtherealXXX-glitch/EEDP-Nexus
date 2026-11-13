from pathlib import Path
import tkinter as tk
import unittest

from logic_view import open_logic_view


class LogicViewTest(unittest.TestCase):
    def tearDown(self):
        import gc
        gc.collect()
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
                next(w for w in descendants(view) if isinstance(w,tk.Button) and w.cget("text")=="放大 +").invoke()
                view.consume_status(dict(id="agent-decode",state="succeeded",kind="decode",preview="OK",finished=2))
                texts=[w for w in descendants(view) if isinstance(w,tk.Text)]
                self.assertEqual(texts[0].get("1.0","end-1c"),"OK")
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
