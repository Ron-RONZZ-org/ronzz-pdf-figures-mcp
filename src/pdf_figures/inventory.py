"""Document-level inventory: text pages, tables and OCR'd scans."""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from .detect import (
    FigureCandidate,
    caption_blocks,
    caption_kind,
    detect_page,
    is_scanned_page,
    page_text_blocks,
)
from .ocr import OcrUnavailableError, ocr_available, ocr_page
from .scan import scanned_figure_region


@dataclass
class Inventory:
    candidates: list[FigureCandidate]
    scanned_pages: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _page_numbers(doc: pymupdf.Document, pages: list[int] | None) -> list[int]:
    total = doc.page_count
    if not pages:
        return list(range(total))
    return [page - 1 for page in sorted({page for page in pages if 1 <= page <= total})]


def _scan_candidates(
    page: pymupdf.Page,
    page_number: int,
    textpage: pymupdf.TextPage,
) -> list[FigureCandidate]:
    blocks = page_text_blocks(page, textpage=textpage)
    page_area = page.rect.get_area()
    found: list[FigureCandidate] = []
    for caption in caption_blocks(blocks):
        region = scanned_figure_region(page, caption, blocks)
        if region is None:
            continue
        found.append(
            FigureCandidate(
                index=0,
                kind=caption_kind(caption.text),
                page=page_number,
                caption=caption.text,
                bbox=region,
                caption_bbox=caption.bbox,
                embedded_raster=True,
                area_pct=100.0 * region.area / page_area,
                scanned=True,
            )
        )
    return found


def build_inventory(
    doc: pymupdf.Document,
    pages: list[int] | None = None,
    *,
    ocr: str = "auto",
    ocr_langs: str = "eng",
) -> Inventory:
    """Detect candidates on the requested 1-based pages."""
    candidates: list[FigureCandidate] = []
    scanned_pages: list[int] = []
    notes: list[str] = []

    for page_index in _page_numbers(doc, pages):
        page = doc[page_index]
        page_number = page_index + 1
        if not is_scanned_page(page):
            candidates.extend(detect_page(page, page_number))
            continue

        scanned_pages.append(page_number)
        if ocr == "off":
            notes.append(f"page {page_number}: scanned (no text layer); OCR skipped (ocr='off').")
            continue
        if not ocr_available():
            notes.append(
                f"page {page_number}: scanned (no text layer); OCR unavailable in this deployment."
            )
            continue
        try:
            textpage = ocr_page(page, language=ocr_langs)
        except OcrUnavailableError as error:
            notes.append(f"page {page_number}: {error}")
            continue
        candidates.extend(_scan_candidates(page, page_number, textpage))

    for index, candidate in enumerate(candidates, start=1):
        candidate.index = index
    return Inventory(candidates=candidates, scanned_pages=scanned_pages, notes=notes)
