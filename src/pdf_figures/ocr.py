"""OCR support for scanned PDF pages (Tesseract through PyMuPDF).

PyMuPDF's ``Page.get_textpage_ocr`` shells out to the ``tesseract`` binary and
returns a TextPage whose word boxes the detector can consume exactly like a
text layer.  OCR only runs when the caller asks for it and the page has no
usable text layer.
"""

from __future__ import annotations

import os
import shutil

import pymupdf

DEFAULT_OCR_DPI = 300


class OcrUnavailableError(RuntimeError):
    """Tesseract is not installed in this environment."""


def ocr_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_page(
    page: pymupdf.Page,
    language: str = "eng",
    dpi: int = DEFAULT_OCR_DPI,
    tessdata: str | None = None,
) -> pymupdf.TextPage:
    """Return an OCR text page; ``language`` uses Tesseract's ``+`` syntax."""
    if not ocr_available():
        raise OcrUnavailableError(
            "tesseract is not installed; install tesseract-ocr with the "
            "eng/fra/epo language packages, or call the tool with ocr='off'."
        )
    tessdata = tessdata or os.environ.get("TESSDATA_PREFIX") or None
    return page.get_textpage_ocr(
        language=language,
        dpi=dpi,
        full=False,
        tessdata=tessdata,
    )
