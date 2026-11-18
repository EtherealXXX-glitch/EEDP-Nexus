"""Render the Nexus modular hub directly at each Windows icon size."""
from pathlib import Path
from PIL import Image, ImageDraw

SIZES = (16, 20, 24, 28, 32, 36, 40, 48, 56, 60, 64, 72, 80, 96, 128, 256)
FACES = (
    ("#8ae8ff", [(32, 7), (54, 20), (32, 33), (10, 20)]),
    ("#4b91ff", [(10, 24), (30, 36), (30, 57), (10, 45)]),
    ("#3adbc1", [(34, 36), (54, 24), (54, 45), (34, 57)]),
)


def render(size):
    scale = 4
    image = Image.new("RGBA", (size*scale, size*scale))
    draw = ImageDraw.Draw(image)
    inset = max(1, round(size/64))
    draw.rounded_rectangle((inset*scale, inset*scale, (size-inset)*scale, (size-inset)*scale),
                           radius=round(size*.23)*scale, fill="#101c30")
    for color, vertices in FACES:
        # Align each size to its own pixel grid, then antialias only the sloped edges.
        points = [(round(x*size/64)*scale, round(y*size/64)*scale) for x, y in vertices]
        draw.polygon(points, fill=color)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main():
    directory = Path(__file__).resolve().parent / "assets"
    directory.mkdir(exist_ok=True)
    images = {size: render(size) for size in SIZES}
    render(1024).save(directory / "nexus.png")
    for size, image in images.items(): image.save(directory / f"nexus-{size}.png")
    images[256].save(directory / "nexus-hub.ico", sizes=[(n, n) for n in SIZES],
                     append_images=[images[n] for n in SIZES if n != 256])
    (directory / "nexus.svg").write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<title>EEDP Nexus modular hub</title>
<rect x="1" y="1" width="62" height="62" rx="15" fill="#101c30"/>
<path d="M32 7 54 20 32 33 10 20Z" fill="#8ae8ff"/>
<path d="M10 24 30 36 30 57 10 45Z" fill="#4b91ff"/>
<path d="M34 36 54 24 54 45 34 57Z" fill="#3adbc1"/>
</svg>''', encoding="utf-8")
    print("Nexus modular hub assets generated (including native 20/40 px)")


if __name__ == "__main__": main()
