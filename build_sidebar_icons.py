"""Rasterize pinned Lucide SVGs to crisp, theme-aware native-size sidebar icons."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from svg.path import parse_path, Move, Line, Close
from themes import THEMES

ROOT=Path(__file__).resolve().parent


def geometry(path):
    shapes=[]
    for element in ET.parse(path).getroot():
        kind=element.tag.rsplit("}",1)[-1]
        a=element.attrib
        if kind=="path":
            points=[]
            for segment in parse_path(a["d"]):
                if isinstance(segment,Move):
                    if points:shapes.append(("line",points))
                    points=[(segment.end.real,segment.end.imag)]
                    continue
                if not points:points=[(segment.start.real,segment.start.imag)]
                samples=1 if isinstance(segment,(Line,Close)) else 20
                for index in range(1,samples+1):
                    point=segment.point(index/samples)
                    points.append((point.real,point.imag))
            if points:shapes.append(("line",points))
        elif kind=="circle":shapes.append((kind,tuple(float(a[key]) for key in ("cx","cy","r"))))
        elif kind=="rect":shapes.append((kind,tuple(float(a.get(key,0)) for key in ("x","y","width","height","rx"))))
        elif kind=="line":shapes.append(("line",[(float(a["x1"]),float(a["y1"])),(float(a["x2"]),float(a["y2"]))]))
        elif kind in ("polyline","polygon"):
            values=[float(value) for value in a["points"].replace(","," ").split()]
            points=list(zip(values[::2],values[1::2]))
            if kind=="polygon":points.append(points[0])
            shapes.append(("line",points))
        else:raise ValueError("Unsupported SVG primitive: "+kind)
    return shapes


def render(shapes,size,color):
    scale=4
    factor=size/24*scale
    width=round(2*factor)
    image=Image.new("RGBA",(size*scale,size*scale))
    draw=ImageDraw.Draw(image)
    for kind,values in shapes:
        if kind=="line":
            points=[(x*factor,y*factor) for x,y in values]
            draw.line(points,fill=color,width=width,joint="curve")
            for x,y in (points[0],points[-1]):
                radius=width/2
                draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
        elif kind=="circle":
            x,y,r=values
            draw.ellipse(((x-r)*factor,(y-r)*factor,(x+r)*factor,(y+r)*factor),outline=color,width=width)
        elif kind=="rect":
            x,y,w,h,r=values
            draw.rounded_rectangle((x*factor,y*factor,(x+w)*factor,(y+h)*factor),radius=r*factor,outline=color,width=width)
    return image.resize((size,size),Image.Resampling.LANCZOS)


def main():
    directory=ROOT/"assets/sidebar"
    icons={path.stem:geometry(path) for path in (directory/"source").glob("*.svg")}
    for theme,palette in THEMES.items():
        target=directory/theme
        target.mkdir(exist_ok=True)
        for name,shapes in icons.items():
            for mode in ("normal","active"):
                color=palette["accent"] if mode=="active" else palette["text"]
                for size in (24,28,32,40,48):render(shapes,size,color).save(target/f"{name}-{mode}-{size}.png")
    (directory/"provenance.json").write_text(json.dumps(dict(project="Lucide",version="0.468.0",license="ISC",
        source="https://github.com/lucide-icons/lucide/tree/0.468.0/icons",icons=sorted(icons)),indent=2),encoding="utf-8")
    print("Lucide sidebar assets generated")


if __name__=="__main__":main()
