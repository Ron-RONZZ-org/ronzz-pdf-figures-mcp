from __future__ import annotations

import pymupdf

from pdf_figures.detect import BBox
from pdf_figures.render import MAX_EDGE, MAX_PIXELS, effective_scale, preview_png, render_png


def test_default_600_dpi(fixtures):
    with pymupdf.open(fixtures["raster"]) as document:
        page = document[0]
        xref = page.get_images(full=True)[0][0]
        image = BBox.from_any(page.get_image_rects(xref)[0])
        rendered = render_png(page, image, dpi=600)
    assert abs(rendered.width - 2500) <= 1
    assert abs(rendered.height - 1667) <= 1
    assert rendered.png.startswith(b"\x89PNG")


def test_pixel_and_edge_caps():
    scale = effective_scale(BBox(0, 0, 2000, 2000), 600)
    width = 2000 * scale
    height = 2000 * scale
    assert width * height <= MAX_PIXELS + 1
    assert max(width, height) <= MAX_EDGE + 1


def test_preview_width(fixtures):
    with pymupdf.open(fixtures["raster"]) as document:
        page = document[0]
        xref = page.get_images(full=True)[0][0]
        rendered = render_png(page, BBox.from_any(page.get_image_rects(xref)[0]), dpi=600)
    preview = preview_png(rendered.png, max_width=1024)
    import io

    from PIL import Image

    with Image.open(io.BytesIO(preview)) as image:
        assert image.width == 1024
