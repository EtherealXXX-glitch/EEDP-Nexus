"""Native Tk button behavior with scalable, antialiased rounded frames."""
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from app_paths import RESOURCES


class ActionButton(tk.Button):
    def __init__(self, master, *, primary=False, small=False, frame_theme=None, **kwargs):
        self._ready=False
        self.primary=primary
        self.small=small
        self.frame_theme=frame_theme
        self.shape="rounded"
        self.density="comfortable"
        self.hovered=self.pressed=self.focused=False
        self._virtual={key:kwargs.get(key,value) for key,value in dict(background="#30343e",activebackground="#424854",
            foreground="#e3e6ed",activeforeground="#ffffff",disabledforeground="#929aaa",padx=14,pady=8,font=("Microsoft YaHei UI",10)).items()}
        for short,long in (("bg","background"),("fg","foreground")):
            if short in kwargs:self._virtual[long]=kwargs.pop(short)
        self._font_key=None
        self._font=None
        self._paint_key=None
        self._frame=None
        top=master.winfo_toplevel()
        if not hasattr(top,"_nexus_button_frames"):
            top._nexus_button_frames=OrderedDict()
            top._nexus_button_sources={}
        self._top=top
        self._pixel=tk.PhotoImage(master=top,width=1,height=1)
        kwargs.update(image=self._pixel,compound="center",borderwidth=0,highlightthickness=0,relief="flat",padx=0,pady=0)
        super().__init__(master,**kwargs)
        self._ready=True
        self.bind("<Configure>",lambda event:self._paint(event.width,event.height),add="+")
        self.bind("<Enter>",lambda event:self._state(hovered=True),add="+")
        self.bind("<Leave>",lambda event:self._state(hovered=False,pressed=False),add="+")
        self.bind("<ButtonPress-1>",lambda event:self._state(pressed=True),add="+")
        self.bind("<ButtonRelease-1>",lambda event:self._state(pressed=False),add="+")
        self.bind("<FocusIn>",lambda event:self._state(focused=True),add="+")
        self.bind("<FocusOut>",lambda event:self._state(focused=False,pressed=False),add="+")
        self.bind("<KeyPress-space>",lambda event:self._state(pressed=True),add="+")
        self.bind("<KeyRelease-space>",lambda event:self._state(pressed=False),add="+")
        self.bind("<Return>",lambda event:(self.invoke(),"break")[1],add="+")
        self._layout()

    def cget(self,key):
        canonical={"bg":"background","fg":"foreground"}.get(key,key)
        if self._ready and canonical in self._virtual:return self._virtual[canonical]
        return super().cget(key)

    def configure(self,cnf=None,**kwargs):
        if not self._ready:return super().configure(cnf,**kwargs)
        if isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
        if not kwargs:return super().configure(cnf)
        geometry=False
        for key in list(kwargs):
            canonical={"bg":"background","fg":"foreground"}.get(key,key)
            if canonical in self._virtual:
                value=kwargs.pop(key)
                if self._virtual[canonical]!=value and canonical in ("font","padx","pady"):geometry=True
                self._virtual[canonical]=value
                if canonical in ("foreground","disabledforeground","font"):kwargs[canonical]=value
        if "text" in kwargs:geometry=True
        # Frames draw their own border and inherit the outside color from their container.
        for key in ("borderwidth","bd","highlightthickness","highlightbackground","highlightcolor","relief"):
            kwargs.pop(key,None)
        kwargs.pop("activeforeground",None)
        super().configure(cnf,**kwargs)
        if geometry:self._layout()
        self._paint()

    config=configure

    def set_geometry_style(self,shape,density):
        if (shape,density)==(self.shape,self.density):return
        self.shape,self.density=shape,density
        self._layout()
        self._paint()

    def _layout(self):
        key=str(self._virtual["font"])
        if key!=self._font_key:
            self._font=tkfont.Font(root=self,font=self._virtual["font"])
            self._font_key=key
        text=str(super().cget("text"))
        lines=text.splitlines() or [""]
        padding=12 if self.small else 16
        width=max(64 if self.small else 96 if self.primary else 80,max(self._font.measure(line) for line in lines)+padding*2)
        minimum=30 if self.small else 32 if self.density=="compact" else 40
        height=max(minimum,self._font.metrics("linespace")*len(lines)+(10 if self.small or self.density=="compact" else 14))
        super().configure(width=width,height=height,padx=0,pady=0,borderwidth=0,highlightthickness=0,compound="center")
        self._paint_key=None

    def _state(self,**values):
        for key,value in values.items():setattr(self,key,value)
        self._paint()

    def _paint(self,width=None,height=None):
        if not self._ready or not self.winfo_exists():return
        from themes import CURRENT, THEMES
        width=max(22,width or self.winfo_width())
        height=max(22,height or self.winfo_height())
        if width<=22:width=max(22,int(super().cget("width")))
        if height<=22:height=max(22,int(super().cget("height")))
        theme=self.frame_theme or CURRENT
        p=THEMES[theme]
        state="disabled" if super().cget("state")=="disabled" else "pressed" if self.pressed else "hover" if self.hovered else "focus" if self.focused else "normal"
        variant="primary" if self.primary else "secondary"
        key=(theme,self.shape,variant,state,width,height)
        try:outside=self.master.cget("background")
        except tk.TclError:outside=p["panel"]
        super().configure(background=outside,activebackground=outside,activeforeground=self._virtual["foreground"])
        if key==self._paint_key:return
        path=RESOURCES/"assets/buttons"/theme/f"{self.shape}-{variant}-{state}.png"
        if not path.is_file():return
        sources=self._top._nexus_button_sources
        source_key=(theme,self.shape,variant,state)
        if source_key not in sources:sources[source_key]=tk.PhotoImage(master=self._top,file=str(path))
        cache=self._top._nexus_button_frames
        if key not in cache:
            target=tk.PhotoImage(master=self._top,width=width,height=height)
            source=sources[source_key]
            source_edges=(0,10,11,21)
            dest_x=(0,10,width-10,width)
            dest_y=(0,10,height-10,height)
            for row in range(3):
                for col in range(3):
                    target.tk.call(str(target),"copy",str(source),"-from",source_edges[col],source_edges[row],source_edges[col+1],source_edges[row+1],
                        "-to",dest_x[col],dest_y[row],"-zoom",width-20 if col==1 else 1,height-20 if row==1 else 1)
            cache[key]=target
            while len(cache)>96:cache.popitem(last=False)
        cache.move_to_end(key)
        self._frame=cache[key]
        self._paint_key=key
        super().configure(image=self._frame)
