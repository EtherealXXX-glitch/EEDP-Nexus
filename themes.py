"""Semantic color and button typography profiles shared by all desktop components."""
import re
import tkinter as tk
from tkinter import ttk
from app_paths import RESOURCES


def make(name, description, **values):
    base=dict(bg="#20232b",panel="#252830",terminal="#23252b",field="#30343e",border="#393e49",
        text="#e3e6ed",muted="#929aaa",accent="#54c9ed",success="#79d4ac",error="#f18d97",
        warning="#e9b860",top="#1c2029",selection="#39516a",primary="#23576b",primary_hover="#326e84",
        primary_text="#f1f8ff",hover="#424854",grid="#29313d",plot="#171c25",dark=True,
        waves=["#63dcf2","#6fa7ff","#65d5a9","#e8c56b","#b69dff","#f18d97","#93d6ce","#dfb1e9"])
    return dict(base, name=name,description=description,**values)


THEMES={
    "nexus":make("Nexus 深空", "克制的深灰与青蓝，保留熟悉的工作氛围"),
    "mocha":make("Mocha 柔紫", "受 Catppuccin 启发，柔和的紫色与粉彩",bg="#1e1e2e",panel="#181825",terminal="#181825",field="#313244",
        border="#6c7086",text="#cdd6f4",muted="#bac2de",accent="#cba6f7",success="#a6e3a1",error="#f38ba8",warning="#f9e2af",
        top="#11111b",selection="#45475a",primary="#cba6f7",primary_hover="#b4befe",primary_text="#11111b",hover="#45475a",grid="#45475a",plot="#11111b",
        waves=["#89dceb","#89b4fa","#a6e3a1","#f9e2af","#cba6f7","#f38ba8","#94e2d5","#f5c2e7"]),
    "nord":make("Nord 极地", "受 Nord 启发，冷静的蓝灰与冰川青",bg="#2e3440",panel="#343b49",terminal="#2e3440",field="#434c5e",
        border="#7b879d",text="#eceff4",muted="#d8dee9",accent="#88c0d0",success="#a3be8c",error="#f3a5ad",warning="#ebcb8b",
        top="#242933",selection="#4c566a",primary="#88c0d0",primary_hover="#8fbcbb",primary_text="#242933",hover="#4c566a",grid="#4c566a",plot="#242933",
        waves=["#88c0d0","#81a1c1","#a3be8c","#ebcb8b","#c5a2c0","#f3a5ad","#8fbcbb","#d9b9da"]),
    "warm":make("暖砂 日落", "暖灰、杏色和低饱和绿，适合安静工作的时段",bg="#252120",panel="#2c2725",terminal="#1e1b1a",field="#39312d",
        border="#8d7b6d",text="#f4ebdd",muted="#d6c3ae",accent="#e9b885",success="#b9d3a5",error="#f49c94",warning="#f0d68f",
        top="#1e1b1a",selection="#554236",primary="#e9b885",primary_hover="#f4cba6",primary_text="#251e19",hover="#55483d",grid="#493e35",plot="#1e1b1a",
        waves=["#f0ca98","#a8c8dc","#b9d3a5","#f0d68f","#cfb8df","#f49c94","#a7d3c8","#e3b4c4"]),
    "paper":make("Paper 明亮", "受现代代码编辑器启发，清爽的浅灰与蓝色",bg="#ffffff",panel="#f6f8fa",terminal="#ffffff",field="#ffffff",
        border="#8c959f",text="#1f2328",muted="#59636e",accent="#0969da",success="#116329",error="#b42318",warning="#8a5700",
        top="#eaeef2",selection="#cce5ff",primary="#0969da",primary_hover="#0550ae",primary_text="#ffffff",hover="#d8dee4",grid="#d0d7de",plot="#ffffff",dark=False,
        waves=["#00798a","#0969da","#116329","#8a5700","#8250df","#b42318","#007268","#953d75"]),
    "contrast":make("高对比 黑金", "黑白正文、亮黄焦点与清楚的控件边界",bg="#000000",panel="#080808",terminal="#000000",field="#101010",
        border="#bfbfbf",text="#ffffff",muted="#d6d6d6",accent="#ffff00",success="#83ff95",error="#ffa4a4",warning="#ffff80",
        top="#000000",selection="#333333",primary="#ffff00",primary_hover="#ffffff",primary_text="#000000",hover="#303030",grid="#777777",plot="#000000",
        waves=["#00ffff","#b3d7ff","#83ff95","#ffff80","#e6b3ff","#ffa4a4","#b4ffe6","#ffb3e6"]),
}

# Old literal colors are migration aliases. New components should use color(role).
ALIASES={"#20232b":"bg","#252830":"panel","#23252b":"terminal","#30343e":"field","#393e49":"border",
    "#e3e6ed":"text","#929aaa":"muted","#54c9ed":"accent","#79d4ac":"success","#f18d97":"error",
    "#e9b860":"warning","#1c2029":"top","#181d26":"top","#2b3543":"selection","#39516a":"selection",
    "#40576a":"selection","#315369":"selection","#23576b":"primary","#326e84":"primary_hover",
    "#424854":"hover","#3d4350":"hover","#424650":"border","#657084":"hover","#354b48":"primary",
    "#171c25":"plot","#29313d":"grid","#f1f8ff":"primary_text","white":"text","#ffffff":"text"}
for _index,_value in enumerate(THEMES["nexus"]["waves"]):ALIASES.setdefault(_value,"wave"+str(_index))
CURRENT="nexus"


def palette():return THEMES[CURRENT]


def role(value):return ALIASES.get(str(value).lower(),str(value) if str(value) in palette() else None)


def color(value):
    key=role(value)
    if key and key.startswith("wave"):return palette()["waves"][int(key[4:])]
    return palette().get(key,value)


def contrast(first, second):
    def luminance(value):
        rgb=[int(value[i:i+2],16)/255 for i in (1,3,5)]
        linear=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb]
        return sum(x*y for x,y in zip(linear,(.2126,.7152,.0722)))
    values=sorted([luminance(first),luminance(second)])
    return (values[1]+.05)/(values[0]+.05)


class ThemeManager:
    OPTIONS=("background","foreground","activebackground","activeforeground","disabledforeground",
        "insertbackground","selectbackground","selectforeground","selectcolor","highlightbackground","highlightcolor")

    def __init__(self,root,saved):
        global CURRENT
        self.root=root
        self.name=saved.get("theme","nexus") if saved.get("theme","nexus") in THEMES else "nexus"
        CURRENT=self.name
        try:size=max(8,min(14,int(saved.get("button_size",10))))
        except (TypeError,ValueError):size=10
        self.typography={"family":str(saved.get("button_family","Microsoft YaHei UI")),
            "size":size,"bold":bool(saved.get("button_bold",False)),
            "icons":bool(saved.get("button_icons",True)),
            "shape":saved.get("button_shape","rounded") if saved.get("button_shape") in ("rounded","square") else "rounded",
            "density":saved.get("button_density","comfortable") if saved.get("button_density") in ("comfortable","compact") else "comfortable",
            "startup":bool(saved.get("startup_animation",True))}
        self.pending=None
        self.applied_style=None
        self.images={}
        self.icon_size=saved.get("rail_icon_size",32) if saved.get("rail_icon_size",32) in (24,28,32,40) else 32
        root.bind_all("<Map>",lambda event:self.schedule(),add="+")

    def settings(self):
        return dict(theme=self.name,button_family=self.typography["family"],button_size=self.typography["size"],
                    button_bold=self.typography["bold"],button_icons=self.typography["icons"],rail_icon_size=self.icon_size,
                    button_shape=self.typography["shape"],button_density=self.typography["density"],startup_animation=self.typography["startup"])

    def icon(self,name,size=None,active=False):
        size=size or self.icon_size
        key=(self.name,name,size,active)
        if key not in self.images:
            path=RESOURCES/"assets/sidebar"/self.name/f"{name}-{'active' if active else 'normal'}-{size}.png"
            if not path.is_file():return None
            self.images[key]=tk.PhotoImage(master=self.root,file=str(path))
        return self.images[key]

    def select(self,name):
        global CURRENT
        if name not in THEMES:raise ValueError("Unknown theme")
        self.name=CURRENT=name
        self.apply()

    def schedule(self):
        if self.pending is None:self.pending=self.root.after_idle(self.apply)

    def _resolve(self,value,known=None):
        key=role(value)
        if key:return key,color(value)
        if known:return known,self._value(known)
        return None,value

    def _value(self,key):
        return palette()["waves"][int(key[4:])] if key.startswith("wave") else palette()[key]

    def _button(self,widget):
        raw=getattr(widget,"_nexus_raw_text",str(widget.cget("text")))
        widget._nexus_raw_text=raw
        text=raw if self.typography["icons"] and not getattr(widget,"_nexus_rail",False) else "\n".join(line for line in
            (re.sub(r"^[^\w\u4e00-\u9fff]+","",line).strip() for line in raw.splitlines()) if line)
        size=max(8,self.typography["size"]-2) if getattr(widget,"_nexus_rail",False) else self.typography["size"]
        widget._nexus_original_configure(text=text,font=(self.typography["family"],size,"bold" if self.typography["bold"] else "normal"))
        if hasattr(widget,"set_geometry_style"):
            widget.set_geometry_style(self.typography["shape"],self.typography["density"])
            widget._paint_key=None
            widget._paint()
        if getattr(widget,"_nexus_rail",False):
            active=widget._nexus_color_roles.get("foreground")=="accent"
            image=self.icon(getattr(widget,"_nexus_icon_name","blocks"),active=active) if self.typography["icons"] else None
            widget._nexus_original_configure(image=image or "",compound="top",pady=5)
            widget._nexus_original_configure(highlightthickness=1,highlightbackground=palette()["accent"] if active else palette()["top"],highlightcolor=palette()["accent"])

    def _watch(self,widget,token,force=False):
        if getattr(widget,"_nexus_preview",False):return
        if not force and getattr(widget,"_nexus_applied_theme",None)==token:
            for child in widget.winfo_children():self._watch(child,token)
            return
        if not hasattr(widget,"_nexus_color_roles"):
            widget._nexus_color_roles={}
            original=widget.configure
            widget._nexus_original_configure=original
            for option in self.OPTIONS:
                if option not in widget.keys():continue
                value=widget.cget(option)
                key=role(value)
                if str(value).lower().startswith("system"):
                    if option in ("foreground","insertbackground","activeforeground"):key="text"
                    elif option=="background":key="field" if isinstance(widget,(tk.Entry,tk.Spinbox)) else "terminal" if isinstance(widget,tk.Text) else "panel"
                    elif option=="selectcolor":key="field"
                if option=="background" and key=="text":
                    key="field" if isinstance(widget,(tk.Entry,tk.Spinbox)) else "terminal" if isinstance(widget,tk.Text) else "panel"
                if option=="background" and widget.master is not None:
                    try:
                        if value==widget.master.cget("background"):
                            key=getattr(widget.master,"_nexus_color_roles",{}).get("background",key)
                    except tk.TclError:pass
                if key:widget._nexus_color_roles[option]=key
            def configured(cnf=None,**kwargs):
                if isinstance(cnf,dict):kwargs={**cnf,**kwargs};cnf=None
                for option in list(kwargs):
                    canonical={"bg":"background","fg":"foreground"}.get(option,option)
                    if canonical in self.OPTIONS:
                        key,value=self._resolve(kwargs[option])
                        if key:widget._nexus_color_roles[canonical]=key
                        kwargs[option]=value
                if isinstance(widget,(tk.Button,tk.Menubutton)) and "text" in kwargs:widget._nexus_raw_text=str(kwargs["text"])
                result=original(cnf,**kwargs)
                if isinstance(widget,(tk.Button,tk.Menubutton)) and ("text" in kwargs or getattr(widget,"_nexus_rail",False)):self._button(widget)
                return result
            widget.configure=widget.config=configured
            if isinstance(widget,tk.Canvas):
                create=widget._create
                def created(item,args,kw):
                    for option in ("fill","outline"):
                        if option in kw:kw[option]=color(kw[option])
                    return create(item,args,kw)
                widget._create=created
            if isinstance(widget,tk.Text):
                widget._nexus_tags={}
                for tag in widget.tag_names():
                    values={}
                    for option in ("foreground","background"):
                        value=widget.tag_cget(tag,option)
                        if role(value):values[option]=role(value)
                    if values:widget._nexus_tags[tag]=values
        widget._nexus_original_configure(**{key:self._value(value) for key,value in widget._nexus_color_roles.items()})
        if isinstance(widget,(tk.Button,tk.Menubutton)):
            self._button(widget)
            if getattr(widget,"_nexus_primary",False):widget._nexus_original_configure(foreground=palette()["primary_text"],activeforeground=palette()["primary_text"])
        if isinstance(widget,tk.Label) and getattr(widget,"_nexus_icon_name",None):
            widget._nexus_original_configure(image=self.icon(widget._nexus_icon_name,32) or "")
        if getattr(widget,"_nexus_statusbar",False):widget._nexus_original_configure(height=max(31,int(self.typography["size"]*2.4+8)))
        if isinstance(widget,tk.Text):
            for tag,values in widget._nexus_tags.items():widget.tag_configure(tag,**{key:self._value(value) for key,value in values.items()})
        icon=getattr(widget,"_nexus_icon",None)
        if icon:icon.apply_theme(palette())
        widget._nexus_applied_theme=token
        callback=getattr(widget,"on_theme_changed",None)
        if callback:self.to_redraw.append(callback)
        for child in widget.winfo_children():self._watch(child,token,force)

    def apply(self,force=False):
        self.pending=None
        if not self.root.winfo_exists():return
        token=(self.name,tuple(self.typography.items()),self.icon_size)
        self.to_redraw=[]
        self._watch(self.root,token,force)
        callbacks=self.to_redraw
        if not force and self.applied_style==token:
            for callback in callbacks:callback()
            return
        self.applied_style=token
        p=palette()
        style=ttk.Style(self.root)
        style.configure("TCombobox",fieldbackground=p["field"],background=p["field"],foreground=p["text"],
            bordercolor=p["border"],arrowcolor=p["text"],lightcolor=p["field"],darkcolor=p["field"],selectbackground=p["selection"],selectforeground=p["text"])
        style.map("TCombobox",fieldbackground=[("readonly",p["field"]),("disabled",p["panel"])],foreground=[("readonly",p["text"]),("disabled",p["muted"])],
            selectbackground=[("readonly",p["field"])],selectforeground=[("readonly",p["text"])],bordercolor=[("focus",p["accent"])],background=[("active",p["hover"])])
        for orientation in ("Horizontal","Vertical"):
            style.configure(orientation+".TScrollbar",background=p["border"],troughcolor=p["terminal"],bordercolor=p["terminal"],arrowcolor=p["text"],lightcolor=p["terminal"],darkcolor=p["terminal"])
            style.map(orientation+".TScrollbar",background=[("active",p["muted"])])
        style.configure("Horizontal.TProgressbar",background=p["accent"],troughcolor=p["field"],bordercolor=p["border"])
        style.configure("Nexus.Treeview",background=p["terminal"],fieldbackground=p["terminal"],foreground=p["text"])
        style.configure("Nexus.Treeview.Heading",background=p["field"],foreground=p["text"])
        style.map("Nexus.Treeview",background=[("selected",p["selection"])],foreground=[("selected",p["text"])])
        style.configure("Nexus.TNotebook",background=p["panel"],borderwidth=0)
        style.configure("Nexus.TNotebook.Tab",background=p["field"],foreground=p["text"],padding=(14,8))
        style.map("Nexus.TNotebook.Tab",background=[("selected",p["primary"])],foreground=[("selected",p["primary_text"])])
        self.root.option_add("*TCombobox*Listbox.background",p["field"])
        self.root.option_add("*TCombobox*Listbox.foreground",p["text"])
        for callback in callbacks:callback()
