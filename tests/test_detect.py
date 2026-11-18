from __future__ import annotations

from pathlib import Path

import pymupdf

from pdf_figures.detect import BBox
from pdf_figures.inventory import build_inventory
from pdf_figures.ocr import ocr_available


def inventory(path: Path, **kwargs):
    with pymupdf.open(path) as document:
        return build_inventory(document, **kwargs)


def captioned(path: Path, prefix: str, **kwargs):
    found = [
        candidate
        for candidate in inventory(path, **kwargs).candidates
        if candidate.caption and candidate.caption.startswith(prefix)
    ]
    assert len(found) == 1, f"expected one {prefix!r} candidate, got {found}"
    return found[0]


def test_raster_figure(fixtures):
    candidate = captioned(fixtures["raster"], "Figure 1")
    assert candidate.kind == "figure"
    assert candidate.embedded_raster is True
    with pymupdf.open(fixtures["raster"]) as document:
        page = document[0]
        xref = page.get_images(full=True)[0][0]
        image = BBox.from_any(page.get_image_rects(xref)[0])
    assert abs(candidate.bbox.x0 - image.x0) < 8
    assert abs(candidate.bbox.y0 - image.y0) < 8
    assert abs(candidate.bbox.x1 - image.x1) < 8
    assert abs(candidate.bbox.y1 - image.y1) < 8


def test_vector_figure(fixtures):
    candidate = captioned(fixtures["vector"], "Figure 2")
    assert candidate.kind == "figure"
    assert candidate.bbox.width > 250
    assert candidate.bbox.height > 150


def test_table(fixtures):
    candidate = captioned(fixtures["table"], "Table 1")
    assert candidate.kind == "table"
    assert candidate.caption_bbox is not None
    assert candidate.bbox.y0 >= candidate.caption_bbox.y1
    assert candidate.bbox.height > 40
    # The table ends before the body paragraph that follows it.
    assert candidate.bbox.y1 < 350


def test_multi_panel(fixtures):
    candidate = captioned(fixtures["multi_panel"], "Figure 3")
    assert candidate.panels >= 2
    assert candidate.bbox.x0 <= 102
    assert candidate.bbox.x1 >= 398


def test_two_column(fixtures):
    candidate = captioned(fixtures["two_column"], "Figure 4")
    assert candidate.bbox.x0 >= 300
    assert candidate.bbox.x1 <= 560


def test_false_caption_is_ignored(fixtures):
    captions = [
        candidate.caption
        for candidate in inventory(fixtures["false_caption"]).candidates
        if candidate.caption
    ]
    assert not any(caption.startswith("Table 2 summarizes") for caption in captions)


def test_no_figures(fixtures):
    assert inventory(fixtures["no_figures"]).candidates == []


def test_uncaptioned_region_is_listed(fixtures):
    # The vector fixture's caption is matched; the uncaptioned pass must not
    # duplicate it.
    candidates = inventory(fixtures["vector"]).candidates
    assert sum(1 for item in candidates if item.caption is None and item.bbox.area > 0) == 0


def test_scanned_page_needs_ocr(fixtures):
    report = inventory(fixtures["scanned"], ocr="off")
    assert report.candidates == []
    assert report.scanned_pages == [1]
    assert report.notes


def test_scanned_page_ocr(fixtures):
    if not ocr_available():
        import pytest

        pytest.skip("tesseract is not installed")
    found = [
        candidate
        for candidate in inventory(fixtures["scanned"], ocr="auto").candidates
        if candidate.caption and "Figure 1" in candidate.caption
    ]
    assert len(found) == 1
    assert found[0].scanned is True
    assert found[0].bbox.height > 100


def test_scanned_region_without_ocr(fixtures):
    """The ink-band crop works from OCR-shaped blocks without Tesseract."""
    from pdf_figures.detect import BBox, TextBlock
    from pdf_figures.scan import scanned_figure_region

    with pymupdf.open(fixtures["scanned"]) as document:
        page = document[0]
        caption = TextBlock(
            bbox=BBox(150, 636, 450, 652),
            text="Figure 1: A raster bar chart used as a fixture.",
            size=9,
        )
        region = scanned_figure_region(page, caption, [caption])
    assert region is not None
    assert region.height > 100
    assert region.y1 <= caption.bbox.y0
