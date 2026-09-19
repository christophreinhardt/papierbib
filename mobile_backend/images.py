"""Validated, EXIF-oriented coordinates; crop versions always derive from original."""
import io
import math
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

class CropSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    # Existing project revisions may contain 270°, hence accept a complete turn.
    # The editor stores an arbitrary clockwise correction in degrees.
    rotation: float = Field(default=0, ge=-360, le=360)
    x: float = Field(default=0, ge=0, lt=1)
    y: float = Field(default=0, ge=0, lt=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)

class InvalidImage(ValueError):
    pass

def crop_image(data, spec, max_pixels):
    if spec.x + spec.width > 1.000001 or spec.y + spec.height > 1.000001:
        raise InvalidImage('Der Ausschnitt liegt außerhalb des Fotos.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise InvalidImage('Bitte ein einzelnes JPEG-, PNG- oder WebP-Bild verwenden.')
                if source.width * source.height > max_pixels:
                    raise InvalidImage('Das Foto überschreitet das Limit von 50 Megapixeln.')
                mime = Image.MIME[source.format]
                source.load()
                oriented = ImageOps.exif_transpose(source)
                info = dict(mime=mime, width=oriented.width, height=oriented.height)
                rotated = oriented.rotate(-spec.rotation, expand=True)
                # Ignore floating-point noise at exact pixel boundaries.
                left, top = math.floor(spec.x * rotated.width + 1e-7), math.floor(spec.y * rotated.height + 1e-7)
                right = min(rotated.width, math.ceil((spec.x + spec.width) * rotated.width - 1e-7))
                bottom = min(rotated.height, math.ceil((spec.y + spec.height) * rotated.height - 1e-7))
                if right - left < 8 or bottom - top < 8:
                    raise InvalidImage('Bitte einen mindestens 8 × 8 Pixel großen Ausschnitt wählen.')
                cropped = rotated.crop((left, top, right, bottom))
                if cropped.mode in ('RGBA', 'LA') or 'transparency' in cropped.info:
                    rgba = cropped.convert('RGBA')
                    rgb = Image.new('RGB', cropped.size, 'white')
                    rgb.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    rgb = cropped.convert('RGB')
                output = io.BytesIO()
                rgb.save(output, format='JPEG', quality=95)
                return info, dict(data=output.getvalue(), width=rgb.width, height=rgb.height)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise InvalidImage('Foto beschädigt, zu groß oder Format nicht unterstützt.') from exc
