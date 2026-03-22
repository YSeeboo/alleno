from __future__ import annotations

from io import BytesIO

from PIL import Image as PILImage, ImageOps, UnidentifiedImageError

_PDF_MAX_DIMENSION = 1200
_PDF_JPEG_QUALITY = 70


def prepare_pdf_image_bytes(image_bytes: bytes, max_dimension: int = _PDF_MAX_DIMENSION, quality: int = _PDF_JPEG_QUALITY) -> bytes | None:
    if not image_bytes:
        return None

    try:
        with PILImage.open(BytesIO(image_bytes)) as raw_image:
            image = ImageOps.exif_transpose(raw_image)
            if getattr(image, "is_animated", False):
                image.seek(0)
            image = image.copy()
    except (UnidentifiedImageError, OSError):
        return None

    width, height = image.size
    if width <= 0 or height <= 0:
        return None

    image.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)

    if image.mode not in ("RGB", "L"):
        rgba_image = image.convert("RGBA")
        background = PILImage.new("RGB", image.size, "white")
        background.paste(rgba_image, mask=rgba_image.getchannel("A"))
        image = background
    elif image.mode == "L":
        image = image.convert("RGB")

    output = BytesIO()
    image.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()
