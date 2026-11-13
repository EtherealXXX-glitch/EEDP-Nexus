"""Palette previews and independent button typography controls."""
import tkinter as tk
from tkinter import ttk, font
from themes import THEMES, contrast


def build_appearance(parent, manager, changed, frame, label, button):
    outer=parent
    viewport=tk.Canvas(outer,bg="#252830",highlightthickness=0)
    scroll=ttk.Scrollbar(outer,orient="vertical",command=viewport.yview)
    scroll.pack(side="right",fill="y")
    viewport.pack(side="left",fill="both",expand=True)
    viewport.configure(yscrollcommand=scroll.set)
    parent=frame(viewport)
    content=viewport.create_window(0,0,window=parent,anchor="nw")
    parent.bind("<Configure>",lambda event:viewport.configure(scrollregion=viewport.bbox("all")))
    viewport.bind("<Configure>",lambda event:viewport.itemconfigure(content,width=event.width))
    top=outer.winfo_toplevel()
    def wheel(event):
        if not viewport.winfo_exists() or not viewport.winfo_ismapped():return
        if isinstance(event.widget,ttk.Combobox):return
        widget=event.widget
        while widget is not None:
            if widget==parent:
                viewport.yview_scroll(-int(event.delta/120),"units")
                return "break"
            widget=getattr(widget,"master",None)
    binding=top.bind("<MouseWheel>",wheel,add="+")
    outer.bind("<Destroy>",lambda event:top.unbind("<MouseWheel>",binding) if event.widget==outer else None,add="+")
    heading=frame(parent)
    heading.pack(fill="x",padx=18,pady=(14,6))
    label(heading,"工作台配色",font=("Microsoft YaHei UI",13,"bold")).pack(side="left")
    current=label(heading,"",muted=True)
    current.pack(side="right")
    cards=frame(parent)
    cards.pack(fill="x",padx=18)
    selectors={}
    def apply_theme(key):
        manager.select(key)
        refresh()
        changed()
    for number,(key,p) in enumerate(THEMES.items()):
        cards.columnconfigure(number%3,weight=1,uniform="theme")
        card=tk.Frame(cards,bg=p["panel"],highlightthickness=1,highlightbackground=p["border"],height=115)
        card._nexus_preview=True
        card.grid(row=number//3,column=number%3,sticky="nsew",padx=4,pady=4)
        card.grid_propagate(False)
        card.columnconfigure(0,weight=1)
        tk.Label(card,text=p["name"],bg=p["panel"],fg=p["text"],font=("Microsoft YaHei UI",11,"bold"),anchor="w").grid(row=0,column=0,sticky="ew",padx=12,pady=(8,0))
        description=tk.Label(card,text=p["description"],bg=p["panel"],fg=p["muted"],font=("Microsoft YaHei UI",8),anchor="w",wraplength=260,justify="left")
        description.grid(row=1,column=0,columnspan=2,sticky="ew",padx=12)
        card.bind("<Configure>",lambda event,item=description:item.configure(wraplength=max(150,event.width-24)))
        swatches=tk.Frame(card,bg=p["panel"])
        swatches.grid(row=2,column=0,sticky="w",padx=12,pady=9)
        for role in ("bg","field","accent","success","error"):
            tk.Frame(swatches,bg=p[role],width=22,height=14).pack(side="left",padx=(0,4))
        select=tk.Button(card,text="使用",command=lambda name=key:apply_theme(name),bg=p["primary"],fg=p["primary_text"],
                         activebackground=p["primary_hover"],activeforeground=p["primary_text"],relief="flat",font=("Microsoft YaHei UI",8),padx=10,pady=3)
        select.grid(row=2,column=1,padx=(0,12),pady=6)
        selectors[key]=select
    controls=frame(parent)
    controls.pack(fill="x",padx=22,pady=(12,4))
    label(controls,"按钮文字风格",font=("Microsoft YaHei UI",11,"bold")).grid(row=0,column=0,columnspan=6,sticky="w",pady=(0,8))
    available=set(font.families(parent))
    families=[name for name in ("Microsoft YaHei UI","Microsoft YaHei","Segoe UI","Cascadia Mono","Consolas") if name in available]
    if manager.typography["family"] not in families:families.insert(0,manager.typography["family"])
    family=tk.StringVar(value=manager.typography["family"])
    size=tk.StringVar(value=str(manager.typography["size"]))
    weight=tk.BooleanVar(value=manager.typography["bold"])
    icons=tk.BooleanVar(value=manager.typography["icons"])
    icon_size=tk.StringVar(value=str(manager.icon_size))
    shape=tk.StringVar(value="圆角" if manager.typography["shape"]=="rounded" else "直角")
    density=tk.StringVar(value="舒适" if manager.typography["density"]=="comfortable" else "紧凑")
    startup=tk.BooleanVar(value=manager.typography["startup"])
    label(controls,"字体",muted=True).grid(row=1,column=0,sticky="w",padx=(0,6))
    font_box=ttk.Combobox(controls,textvariable=family,values=families,state="readonly",width=23)
    font_box.grid(row=1,column=1,sticky="ew",padx=(0,16))
    label(controls,"字号",muted=True).grid(row=1,column=2,padx=(0,6))
    size_box=ttk.Combobox(controls,textvariable=size,values=list(range(8,15)),state="readonly",width=5)
    size_box.grid(row=1,column=3,padx=(0,16))
    def apply_type(_=None):
        manager.typography.update(family=family.get(),size=int(size.get()),bold=weight.get(),icons=icons.get())
        manager.typography.update(shape="rounded" if shape.get()=="圆角" else "square",density="comfortable" if density.get()=="舒适" else "compact")
        manager.typography["startup"]=startup.get()
        manager.icon_size=int(icon_size.get())
        manager.apply()
        changed()
    font_box.bind("<<ComboboxSelected>>",apply_type)
    size_box.bind("<<ComboboxSelected>>",apply_type)
    tk.Checkbutton(controls,text="加粗",variable=weight,command=apply_type,bg="#252830",fg="#e3e6ed",selectcolor="#30343e").grid(row=1,column=4,padx=(0,12))
    tk.Checkbutton(controls,text="显示按钮图标",variable=icons,command=apply_type,bg="#252830",fg="#e3e6ed",selectcolor="#30343e").grid(row=1,column=5,sticky="w")
    label(controls,"侧栏图标 px",muted=True).grid(row=2,column=0,sticky="w",pady=(10,0))
    icon_box=ttk.Combobox(controls,textvariable=icon_size,values=[24,28,32,40],state="readonly",width=5)
    icon_box.grid(row=2,column=1,sticky="w",pady=(10,0))
    icon_box.bind("<<ComboboxSelected>>",apply_type)
    label(controls,"默认 32；原生尺寸绘制，不拉伸小图标",muted=True).grid(row=2,column=2,columnspan=4,sticky="w",pady=(10,0))
    for column,title,variable,values in ((0,"按钮形状",shape,["圆角","直角"]),(2,"按钮密度",density,["舒适","紧凑"])):
        label(controls,title,muted=True).grid(row=3,column=column,sticky="w",pady=(10,0))
        box=ttk.Combobox(controls,textvariable=variable,values=values,state="readonly",width=8)
        box.grid(row=3,column=column+1,sticky="w",pady=(10,0))
        box.bind("<<ComboboxSelected>>",apply_type)
    tk.Checkbutton(controls,text="启动动画（点击可跳过）",variable=startup,command=apply_type,bg="#252830",fg="#e3e6ed",selectcolor="#30343e").grid(row=3,column=4,columnspan=2,sticky="w",pady=(10,0))
    preview=frame(parent)
    preview.pack(fill="x",padx=22,pady=(12,6))
    label(preview,"即时预览",muted=True).pack(side="left",padx=(0,12))
    button(preview,"▶  开始采集",lambda:None,primary=True).pack(side="left",padx=(0,8))
    button(preview,"保存设置 Aa 123",lambda:None).pack(side="left")
    def reset():
        family.set("Microsoft YaHei UI");size.set("10");weight.set(False);icons.set(True);icon_size.set("32")
        shape.set("圆角");density.set("舒适")
        startup.set(True)
        manager.icon_size=32
        manager.typography.update(family=family.get(),size=10,bold=False,icons=True,shape="rounded",density="comfortable",startup=True)
        apply_theme("nexus")
    button(preview,"恢复默认",reset,small=True).pack(side="right")
    notice=label(parent,"选择立即生效并自动保存；纯文字模式仍保留清楚的功能名称。",muted=True)
    notice.pack(anchor="w",padx=22,pady=(2,10))
    def refresh():
        p=THEMES[manager.name]
        current.configure(text="当前："+p["name"])
        for key,item in selectors.items():item.configure(text="已选择" if key==manager.name else "使用")
        if manager.name=="contrast":
            minimum=min(contrast(p[role],p[background]) for role in ("text","muted") for background in ("bg","panel","field","terminal"))
            notice.configure(text=f"高对比正文 / 辅助文字在主要底色上的最低计算对比度 {minimum:.1f}:1；按钮、状态与波形同时保留文字标识。")
        else:notice.configure(text="选择立即生效并自动保存；纯文字模式仍保留清楚的功能名称。")
    refresh()
