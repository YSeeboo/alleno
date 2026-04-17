"""Shared helpers for PDF generators that render part images."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from PIL import Image as PILImage, UnidentifiedImageError
from reportlab.lib.utils import ImageReader

from services.plating_export import download_pdf_image_bytes


def prefetch_images(image_urls) -> dict[str, bytes]:
    """Download the given image URLs concurrently, deduped. Returns {url: bytes}.
    Failed downloads map to empty bytes (caller renders as missing image)."""
    urls = {u for u in image_urls if u}
    if not urls:
        return {}
    cache: dict[str, bytes] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        for url, data in zip(urls, pool.map(_safe_download, urls)):
            cache[url] = data or b""
    return cache


def _safe_download(url: str) -> bytes | None:
    try:
        return download_pdf_image_bytes(url)
    except Exception:
        return None


def fit_image(image_bytes: bytes, max_w: float, max_h: float):
    """Return (ImageReader, draw_w, draw_h) that fits inside the box while
    preserving aspect ratio. Returns None if the image is invalid."""
    try:
        with PILImage.open(BytesIO(image_bytes)) as raw:
            raw.copy()
    except (UnidentifiedImageError, OSError):
        return None
    reader = ImageReader(BytesIO(image_bytes))
    img_w, img_h = reader.getSize()
    if img_w <= 0 or img_h <= 0:
        return None
    scale = min(max_w / img_w, max_h / img_h)
    return reader, max(1, img_w * scale), max(1, img_h * scale)
