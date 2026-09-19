"""Tesseract on the Homeserver, stdin/stdout only, no image files or raw-text logs."""
import io
import os
import subprocess

from PIL import Image, ImageOps
from .images import CropSpec, crop_image
from .isbn import extract


class OCRUnavailable(Exception):
    pass


def recognize_isbns(data, max_pixels=50_000_000):
    # Validate and discard metadata even when a client sends a forged content type.
    _, crop = crop_image(data, CropSpec(), max_pixels)
    with Image.open(io.BytesIO(crop['data'])) as source:
        image = ImageOps.autocontrast(source.convert('L'))
        image.thumbnail((2400, 2400))
        if image.width < 1200 and image.height < 800:
            image = image.resize((image.width*2, image.height*2))
        buf = io.BytesIO()
        image.save(buf, format='PNG')
    try:
        result = subprocess.run(
            ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '6',
             '-c', 'tessedit_char_whitelist=0123456789XxISBNisbn:- '],
            input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=12, check=True, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
    except (OSError, subprocess.SubprocessError) as exc:
        raise OCRUnavailable('ISBN-OCR ist nicht verfügbar oder hat das Zeitlimit erreicht. ISBN bitte manuell eingeben.') from exc
    # Raw OCR text never leaves this function; title/author are not interpreted.
    return extract(result.stdout.decode('utf-8', errors='replace'))
