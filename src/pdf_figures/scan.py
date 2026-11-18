"""Figure region discovery on scanned pages.

A scanned page is one full-page raster: there are no vector paths or image
objects to cluster.  The caption (found by OCR) is still the anchor.  The
figure sits on the side of the caption with more room, bounded by the nearest
text block, and the ink bounding box inside that band trims the margins.
"""

from __future__ import annotations

import pymupdf
from PIL import Image

from .detect import BBox, TextBlock

# A pixel darker than this counts as ink.
INK_THRESHOLD = 200
PROFILE_DPI = 100


def _ink_bbox(
    image: Image.Image, box_px: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = box_px
    if x1 <= x0 or y1 <= y0:
        return None
    crop = image.crop(box_px)
    mask = crop.point(lambda pixel: 255 if pixel < INK_THRESHOLD else 0)
    bounds = mask.getbbox()
    if bounds is None:
        return None
    return (x0 + bounds[0], y0 + bounds[1], x0 + bounds[2], y0 + bounds[3])


def _side(caption: BBox, page_height: float) -> str:
    return "above" if (caption.y0 + caption.y1) / 2 > page_height / 2 else "below"


def scanned_figure_region(
    page: pymupdf.Page,
    caption: TextBlock,
    blocks: list[TextBlock],
    *,
    gap_pt: float = 12.0,
) -> BBox | None:
    """The ink-bounded figure band on the caption's side of a scanned page."""
    page_rect = page.rect
    side = _side(caption.bbox, page_rect.height)
    others = [block for block in blocks if block is not caption]

    if side == "above":
        above = [block for block in others if block.bbox.y1 <= caption.bbox.y0 + 2]
        top = max((block.bbox.y1 for block in above), default=page_rect.y0 + 18)
        band = BBox(page_rect.x0 + 18, top + gap_pt, page_rect.x1 - 18, caption.bbox.y0 - gap_pt)
    else:
        below = [block for block in others if block.bbox.y0 >= caption.bbox.y1 - 2]
        bottom = min((block.bbox.y0 for block in below), default=page_rect.y1 - 18)
        band = BBox(page_rect.x0 + 18, caption.bbox.y1 + gap_pt, page_rect.x1 - 18, bottom - gap_pt)

    if band.width <= 0 or band.height <= 0:
        return None

    pixmap = page.get_pixmap(
        dpi=PROFILE_DPI,
        colorspace=pymupdf.csGRAY,
        clip=pymupdf.Rect(band.x0, band.y0, band.x1, band.y1),
    )
    image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
    ink = _ink_bbox(image, (0, 0, pixmap.width, pixmap.height))
    if ink is None:
        return band

    scale = 72.0 / PROFILE_DPI
    return BBox(
        band.x0 + ink[0] * scale,
        band.y0 + ink[1] * scale,
        band.x0 + ink[2] * scale,
        band.y0 + ink[3] * scale,
    )
