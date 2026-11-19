"""Live numeric plots fed from the existing serial event stream."""
from collections import deque
import time
import tkinter as tk
from nexus_ui.themes import palette


def open_plot_view(root, background_request, frame, label, button):
    view=frame(root)
    timer_owner=view.winfo_toplevel()
    view.columnconfigure(0,weight=1)
    view.rowconfigure(1,weight=1)
    controls=frame(view)
    controls.grid(row=0,column=0,sticky="ew",padx=12,pady=8)
    info=label(controls,"等待串口数据",muted=True)
    info.pack(side="left")
    canvas=tk.Canvas(view,bg=palette()["plot"],highlightthickness=0)
    canvas.grid(row=1,column=0,sticky="nsew",padx=12,pady=(0,12))
    state=dict(queue=deque(),chars=0,busy=True,closed=False,points=[],span=500,offset=0,dirty=False,reset_stream=False,dropping=False,clear_requested=False,last_poll=0.0,scheduled=False)

    def request(action,args,done):
        background_request("call",{"target":"plot."+action,"arguments":args},
                           lambda result:done(result) if not state["closed"] else None,
                           lambda error:failed(error) if not state["closed"] else None)
    def failed(error):
        state["busy"]=False
        state["queue"].clear()
        state["chars"]=0
        state["reset_stream"]=True
        state["dropping"]=True
        state["last_poll"]=time.monotonic()
        info.configure(text="波形更新失败："+str(error))
    def draw():
        colors=palette()
        canvas.configure(bg=colors["plot"])
        canvas.delete("all")
        points=state["points"]
        if not points:
            canvas.create_text(canvas.winfo_width()/2,canvas.winfo_height()/2,text="等待 @plot 格式数据",fill=colors["muted"])
            return
        end=max(0,len(points)-state["offset"])
        visible=points[max(0,end-state["span"]):end]
        values=[v for item in visible for v in item["values"].values()]
        if not values:return
        low,high=min(values),max(values)
        if low==high:low-=1;high+=1
        left,top=60,24
        width=max(1,canvas.winfo_width()-80)
        height=max(1,canvas.winfo_height()-54)
        for i in range(5):
            y=top+height*i/4
            canvas.create_line(left,y,left+width,y,fill=colors["grid"])
            canvas.create_text(left-6,y,text=f"{high-(high-low)*i/4:.3g}",anchor="e",fill=colors["muted"])
            x=left+width*i/4
            canvas.create_line(x,top,x,top+height,fill=colors["grid"])
            position=round((len(visible)-1)*i/4)
            canvas.create_text(x,top+height+12,text=str(visible[position]["index"]),fill=colors["muted"])
        names=list(dict.fromkeys(name for item in visible for name in item["values"]))[:16]
        for number,name in enumerate(names):
            color=colors["waves"][number%len(colors["waves"])]
            coords=[]
            for index,item in enumerate(visible):
                value=item["values"].get(name)
                if value is None:
                    if len(coords)>=4:canvas.create_line(*coords,fill=color,width=2)
                    coords=[]
                    continue
                coords.extend((left+width*index/max(1,len(visible)-1),top+height*(high-value)/(high-low)))
            if len(coords)>=4:canvas.create_line(*coords,fill=color,width=2)
            canvas.create_text(left+number*85,8,text=name,anchor="w",fill=color)
    def loaded(result):
        state["last_poll"]=time.monotonic()
        state["points"]=result.get("points",[])
        state["dirty"]=True
        state["busy"]=False
        schedule()
    def fed(result):
        info.configure(text=f"已接收 {result.get('accepted',0)} 点 · 格式错误 {result.get('rejected',0)}")
        request("samples",{"limit":5000},loaded)
    def schedule():
        if state["closed"] or state["scheduled"]:return
        state["scheduled"]=True
        def run():
            state["scheduled"]=False
            pump()
        timer_owner.after(100,run)
    def pump():
        if state["closed"] or state["busy"]:return
        if state["clear_requested"]:
            state["clear_requested"]=False
            state["busy"]=True
            def cleared(_):
                state["points"]=[]
                state["offset"]=0
                state["dirty"]=True
                state["busy"]=False
                pump()
            request("clear",{},cleared)
            return
        if not state["queue"]:return
        chunks=[]
        size=0
        while state["queue"] and size+len(state["queue"][0])<=65536:
            chunk=state["queue"].popleft()
            state["chars"]-=len(chunk)
            chunks.append(chunk)
            size+=len(chunk)
        if chunks:
            state["busy"]=True
            reset=state["reset_stream"]
            state["reset_stream"]=False
            request("feed",{"text":"".join(chunks),"reset_stream":reset},fed)
    def consume(item):
        if item.get("component")!="serial" or item.get("kind")!="rx":return
        text=item.get("text","")
        if not isinstance(text,str) or not text:return
        if state["dropping"]:
            _,separator,text=text.partition("\n")
            if not separator:return
            state["dropping"]=False
        if state["chars"]+len(text)>65536:
            state["queue"].clear()
            state["chars"]=0
            state["reset_stream"]=True
            state["dropping"]=True
            info.configure(text="数据过快，部分显示数据已丢弃")
            return
        state["queue"].append(text)
        state["chars"]+=len(text)
        schedule()
    def clear():
        state["queue"].clear()
        state["chars"]=0
        state["clear_requested"]=True
        state["reset_stream"]=True
        pump()
    button(controls,"清空",clear,small=True).pack(side="right")
    def wheel(event):
        if event.state & 4:
            state["span"]=max(20,min(5000,int(state["span"]*(.7 if event.delta>0 else 1.4))))
        else:
            state["offset"]=max(0,min(max(0,len(state["points"])-1),state["offset"]+(-1 if event.delta>0 else 1)*max(1,state["span"]//10)))
        state["dirty"]=True
        return "break"
    canvas.bind("<MouseWheel>",wheel)
    canvas.bind("<Configure>",lambda event:draw())
    def tick():
        if state["closed"]:return
        if state["dirty"]:
            state["dirty"]=False
            draw()
        if view.winfo_ismapped() and not state["busy"] and not state["queue"] and time.monotonic()-state["last_poll"]>=2:
            state["busy"]=True
            request("samples",{"limit":5000},loaded)
        timer_owner.after(100,tick)
    def destroyed(event):
        if event.widget==view:state["closed"]=True
    view.bind("<Destroy>",destroyed,add="+")
    view.consume_event=consume
    view.on_theme_changed=draw
    request("samples",{"limit":5000},loaded)
    tick()
    return view
