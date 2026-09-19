"""Tesseract on the Homeserver, stdin/stdout only, no image files or raw-text logs."""
import io
import os
import subprocess
import time

from PIL import Image, ImageOps
from .images import CropSpec, crop_image
from .isbn import extract


class OCRUnavailable(Exception):
    pass


def _variants(image):
    """Small bounded variants for real photographs, never title/author OCR."""
    base = ImageOps.autocontrast(image.convert('L'), cutoff=1)
    if max(base.size) < 2200:
        base = base.resize((base.width * 2, base.height * 2), Image.Resampling.LANCZOS)
    base.thumbnail((3000, 3000), Image.Resampling.LANCZOS)
    yield base
    # Strongly lit ISBNs and barcodes benefit from a binary alternative.
    yield base.point(lambda pixel: 255 if pixel > 165 else 0)
    yield base.rotate(90, expand=True)
    yield base.rotate(270, expand=True)


def recognize_isbns(data, max_pixels=50_000_000):
    # Validate and discard metadata even when a client sends a forged content type.
    _, crop = crop_image(data, CropSpec(), max_pixels)
    with Image.open(io.BytesIO(crop['data'])) as source:
        variants = list(_variants(source))
    deadline = time.monotonic() + 18
    found = []
    try:
        for image in variants:
            if time.monotonic() >= deadline:
                break
            buf = io.BytesIO()
            image.save(buf, format='PNG', optimize=True)
            for psm in ('6', '7', '11', '13'):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                result = subprocess.run(
                    ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', psm,
                     '-c', 'tessedit_char_whitelist=0123456789XxISBNisbn:- '],
                    input=buf.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=min(4, max(1, remaining)), check=True,
                    env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
                for number in extract(result.stdout.decode('utf-8', errors='replace')):
                    if number not in found:
                        found.append(number)
        return found
    except (OSError, subprocess.SubprocessError) as exc:
        raise OCRUnavailable('ISBN-OCR ist nicht verfügbar oder hat das Zeitlimit erreicht. ISBN bitte manuell eingeben.') from exc
