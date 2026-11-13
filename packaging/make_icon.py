"""Draw the herd app icon (packaging/herd.ico + web favicon). Run: uv run --with pillow python packaging/make_icon.py"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ACCENT_TOP, ACCENT_BOTTOM = (166, 194, 228), (118, 150, 196)  # around the UI accent #96b2d7
INK = (19, 21, 24)  # canvas #131518
DONE = (76, 196, 140)  # done dot #4cc48c
FONT = "C:/Windows/Fonts/segoeuib.ttf"
S = 1024  # draw big, downsample for crisp small sizes


def draw() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(ACCENT_TOP, ACCENT_BOTTOM)))
    mask = Image.new("L", (S, S), 0)
    pad = 40
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, S - pad, S - pad], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 760)
    box = d.textbbox((0, 0), "h", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((S - w) / 2 - box[0] - 40, (S - h) / 2 - box[1] + 10), "h", font=font, fill=INK)

    r, cx, cy = 118, S - 230, S - 230  # status dot, ringed in the canvas colour so it reads at 16px
    d.ellipse([cx - r - 34, cy - r - 34, cx + r + 34, cy + r + 34], fill=INK)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DONE)
    return img


def main() -> None:
    img = draw()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    img.save(ROOT / "herd.ico", sizes=[(s, s) for s in sizes])
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "herd-256.png")
    web = ROOT.parent / "src" / "herd" / "web"
    img.resize((64, 64), Image.LANCZOS).save(web / "favicon.png")
    img.save(web / "app-icon.ico", sizes=[(s, s) for s in sizes])  # pywebview on Windows needs .ico
    print("wrote herd.ico, herd-256.png, web/favicon.png, web/app-icon.ico")


if __name__ == "__main__":
    main()
