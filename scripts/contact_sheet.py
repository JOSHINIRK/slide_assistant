"""Combine exported slide PNGs into one contact-sheet image (used for README previews)."""
import sys
from pathlib import Path
from PIL import Image

src, out = Path(sys.argv[1]), Path(sys.argv[2])
cols = int(sys.argv[3]) if len(sys.argv) > 3 else 3
files = sorted(src.glob("slide_*.png"))
tw, th, pad = 800, 450, 16
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * tw + (cols + 1) * pad, rows * th + (rows + 1) * pad), "#D9DEE5")
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB").resize((tw, th), Image.LANCZOS)
    r, c = divmod(i, cols)
    sheet.paste(im, (pad + c * (tw + pad), pad + r * (th + pad)))
out.parent.mkdir(parents=True, exist_ok=True)
sheet.save(out)
print(out)
