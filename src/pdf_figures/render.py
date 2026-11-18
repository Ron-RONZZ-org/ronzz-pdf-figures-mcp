"""Region rendering with hard DPI, pixel and size caps."""

from __future__ import annotations

import io
from dataclasses import dataclass

import pymupdf
from PIL import Image

from .detect import BBox

DEFAULT_DPI = 600
MAX_DPI = 600
MAX_PIXELS = 48_000_000
MAX_EDGE = 8000
PREVIEW_WIDTH = 1024


@dataclass(frozen=True)
class RenderedPng:
    png: bytes
    width: int
    height: int
    dpi: float

    @property
    def size(self) -> int:
        return len(self.png)


def effective_scale(bbox: BBox, dpi: int) -> float:
    """Clamp the requested DPI so the output stays within the caps."""
    dpi = max(36, min(int(dpi), MAX_DPI))
    scale = dpi / 72.0
    width_px = max(1.0, bbox.width * scale)
    height_px = max(1.0, bbox.height * scale)
    if width_px * height_px > MAX_PIXELS:
        scale *= (MAX_PIXELS / (width_px * height_px)) ** 0.5
    width_px = max(1.0, bbox.width * scale)
    height_px = max(1.0, bbox.height * scale)
    longest = max(width_px, height_px)
    if longest > MAX_EDGE:
        scale *= MAX_EDGE / longest
    return scale


def render_png(page: pymupdf.Page, bbox: BBox, dpi: int = DEFAULT_DPI) -> RenderedPng:
    scale = effective_scale(bbox, dpi)
    pixmap = page.get_pixmap(
        clip=pymupdf.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
        matrix=pymupdf.Matrix(scale, scale),
        alpha=False,
    )
    return RenderedPng(
        png=pixmap.tobytes("png"),
        width=pixmap.width,
        height=pixmap.height,
        dpi=scale * 72.0,
    )


def preview_png(png: bytes, max_width: int = PREVIEW_WIDTH) -> bytes:
    """A model-facing preview; the full-resolution file stays on disk."""
    with Image.open(io.BytesIO(png)) as image:
        if image.width <= max_width:
            return png
        ratio = max_width / image.width
        resized = image.convert("RGB").resize(
            (max_width, max(1, round(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )
        out = io.BytesIO()
        resized.save(out, format="PNG", optimize=True)
        return out.getvalue()
