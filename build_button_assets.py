"""Build tiny antialiased nine-slice frames; no imaging library is needed at runtime."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageColor
from themes import THEMES


def main():
    directory=Path(__file__).resolve().parent/"assets/buttons"
    for theme,p in THEMES.items():
        target=directory/theme
        target.mkdir(parents=True,exist_ok=True)
        for shape,radius in (("rounded",7),("square",2)):
            for variant in ("primary","secondary"):
                for state in ("normal","hover","pressed","focus","disabled"):
                    fill=p["primary"] if variant=="primary" else p["field"]
                    if state in ("hover","pressed"):fill=p["primary_hover"] if variant=="primary" else p["hover"] if state=="hover" else p["selection"]
                    if state=="pressed":
                        rgb=ImageColor.getrgb(fill)
                        base=ImageColor.getrgb(p["bg"])
                        fill=tuple(round(a*.7+b*.3) for a,b in zip(rgb,base))
                    if state=="disabled":fill=p["field"]
                    edge=p["accent"] if state in ("focus","pressed","hover") else p["border"]
                    image=Image.new("RGBA",(84,84))
                    ImageDraw.Draw(image).rounded_rectangle((2,2,81,81),radius=radius*4,fill=fill,outline=edge,width=4)
                    image.resize((21,21),Image.Resampling.LANCZOS).save(target/f"{shape}-{variant}-{state}.png")
    print("Antialiased button frames generated")


if __name__=="__main__":main()
