"""Bounded, nonblocking first-frame brand reveal; no device calls or fake progress."""
import math
import time
import tkinter as tk
from themes import palette


class StartupReveal:
    def __init__(self,root,duration=1.0):
        self.root=root
        self.duration=duration
        self.started=time.perf_counter()
        self.timer=None
        self.closed=False
        p=palette()
        self.canvas=tk.Canvas(root,bg=p["bg"],highlightthickness=0,takefocus=False)
        self.canvas._nexus_preview=True
        self.canvas.place(relx=0,rely=0,relwidth=1,relheight=1)
        self.canvas.tk.call("raise",self.canvas._w)
        self.canvas.bind("<Button-1>",lambda event:self.close())
        self.canvas.bind("<Destroy>",lambda event:self.close() if event.widget==self.canvas else None)
        self.tick()

    def tick(self):
        if self.closed:return
        elapsed=time.perf_counter()-self.started
        if elapsed>=self.duration:
            self.close()
            return
        p=palette()
        c=self.canvas
        w,h=c.winfo_width(),c.winfo_height()
        if w>5:
            c.delete("all")
            x,y=w/2,h/2-42
            phase=min(1,elapsed/.4)
            ease=1-(1-phase)**3
            gap=18*(1-ease)
            faces=[([-38,-19,0,-41,38,-19,0,3],p["accent"],0,-gap),
                   ([-38,-13,-5,7,-5,45,-38,25],p["success"],-gap,gap),
                   ([5,7,38,-13,38,25,5,45],p["primary_hover"],gap,gap)]
            for points,fill,dx,dy in faces:
                c.create_polygon(*[v+(x+dx if n%2==0 else y+dy) for n,v in enumerate(points)],fill=fill,outline="")
            c.create_text(x,y+85,text="EEDP NEXUS",font=("Segoe UI",23,"bold"),fill=p["text"])
            c.create_text(x,y+121,text="连接工具 · 延伸能力",font=("Microsoft YaHei UI",10),fill=p["muted"])
            c.create_line(x-65,y+153,x+65,y+153,fill=p["border"],width=2)
            pos=(math.sin(elapsed*6-1.5)+1)/2
            c.create_line(x-65+pos*90,y+153,x-25+pos*90,y+153,fill=p["accent"],width=2)
        self.timer=self.root.after(16,self.tick)

    def close(self):
        if self.closed:return
        self.closed=True
        if self.timer:
            try:self.root.after_cancel(self.timer)
            except tk.TclError:pass
        if self.canvas.winfo_exists():self.canvas.destroy()
