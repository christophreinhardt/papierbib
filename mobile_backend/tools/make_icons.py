"""Deterministic code-drawn PWA icons; no external assets."""
from pathlib import Path
import sys
from PIL import Image, ImageDraw

root = Path(sys.argv[1])
for size in (192, 512):
    image = Image.new('RGB', (size, size), '#173e45')
    draw = ImageDraw.Draw(image)
    for left, right in ((.25, .4), (.44, .59), (.63, .78)):
        draw.rectangle((int(left*size), int(.25*size), int(right*size), int(.75*size)), fill='#f4f5ef')
        draw.rectangle((int((left+.02)*size), int(.36*size), int((right-.02)*size), int(.4*size)), fill='#e8b854')
    image.save(root / f'icon-{size}.png')
