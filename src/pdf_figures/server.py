"""pdf-figures MCP server.

Tools:
  list_pdf_figures   inventory (no images)
  extract_pdf_figure one figure/table as a full-resolution PNG + preview
  render_pdf_region  escape hatch for an arbitrary page region
"""

from __future__ import annotations

import base64
import json
import os
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
from mcp.server.mcpserver import MCPServer
from mcp.types import ImageContent, TextContent

from .detect import BBox
from .inventory import Inventory, build_inventory
from .paths import AllowedRoots, PathNotAllowed
from .render import DEFAULT_DPI, preview_png, render_png

OUTPUT_DIR = Path(os.environ.get("PDF_FIGURES_OUTPUT_DIR", "/figures"))
ALLOWED_ROOTS = AllowedRoots(
    os.environ.get(
        "PDF_FIGURES_ALLOWED_ROOTS",
        "/app/backend/data/uploads:/figures",
    ).split(":")
)

_CACHE: OrderedDict[tuple, Inventory] = OrderedDict()
_CACHE_MAX = 8

mcp = MCPServer("pdf-figures")


def _resolve(filepath: str) -> Path:
    try:
        path = ALLOWED_ROOTS.resolve(filepath)
    except PathNotAllowed as error:
        raise ValueError(str(error)) from error
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"{path.name!r} is not a PDF (expected a .pdf file).")
    return path


def _inventory_key(path: Path, pages: list[int] | None, ocr: str, langs: str) -> tuple:
    stat = path.stat()
    return (str(path), stat.st_mtime_ns, stat.st_size, tuple(pages or ()), ocr, langs)


def _inventory(path: Path, pages: list[int] | None, ocr: str, langs: str) -> Inventory:
    key = _inventory_key(path, pages, ocr, langs)
    cached = _CACHE.get(key)
    if cached is not None:
        _CACHE.move_to_end(key)
        return cached
    with pymupdf.open(path) as doc:
        inventory = build_inventory(doc, pages, ocr=ocr, ocr_langs=langs)
    _CACHE[key] = inventory
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return inventory


def _write_png(name: str, png: bytes) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_DIR / name
    target.write_bytes(png)
    return target


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _image_block(png: bytes) -> ImageContent:
    return ImageContent(
        type="image",
        data=base64.b64encode(preview_png(png)).decode("ascii"),
        mimeType="image/png",
    )


@mcp.tool(
    name="list_pdf_figures",
    description=(
        "Inventory the figures, tables and captions of a PDF inside an allowed upload directory. "
        "Returns JSON (no images): index, kind (figure|table), page, caption, bbox, caption_bbox, "
        "embedded_raster, panels, area_pct, scanned. Captions are matched by a 'Figure N:' / "
        "'Table N:' pattern; large uncaptioned graphic regions are listed with caption=null. "
        "Scanned pages are reported in scanned_pages; pass ocr='auto' (default) to OCR them "
        "with Tesseract (eng/fra/epo via ocr_langs). Show the table to the user and let them "
        "pick indices before calling extract_pdf_figure."
    ),
)
def list_pdf_figures(
    filepath: str,
    pages: list[int] | None = None,
    ocr: str = "auto",
    ocr_langs: str = "eng",
) -> str:
    path = _resolve(filepath)
    inventory = _inventory(path, pages, ocr, ocr_langs)
    with pymupdf.open(path) as doc:
        total_pages = doc.page_count
    return json.dumps(
        {
            "file": str(path),
            "pages": total_pages,
            "figures": [candidate.to_dict() for candidate in inventory.candidates],
            "scanned_pages": inventory.scanned_pages,
            "notes": inventory.notes,
        },
        ensure_ascii=False,
        indent=1,
    )


@mcp.tool(
    name="extract_pdf_figure",
    description=(
        "Render ONE figure/table from the inventory to a full-resolution PNG under the shared "
        "figures volume and return a text summary plus a downscaled preview. index is the value "
        "from list_pdf_figures; pass the same pages filter. include_caption includes the caption "
        "band in the crop. The summary's local_path is what a wiki upload tool consumes "
        "(sourceEntity should be the paper's Source item; license and rights_basis are set by "
        "the caller). The file is written at dpi (default 600, max 600) within the pixel caps."
    ),
)
def extract_pdf_figure(
    filepath: str,
    index: int,
    pages: list[int] | None = None,
    dpi: int = DEFAULT_DPI,
    include_caption: bool = False,
    ocr: str = "auto",
    ocr_langs: str = "eng",
) -> list[TextContent | ImageContent]:
    path = _resolve(filepath)
    inventory = _inventory(path, pages, ocr, ocr_langs)
    candidate = next(
        (item for item in inventory.candidates if item.index == index),
        None,
    )
    if candidate is None:
        available = ", ".join(str(item.index) for item in inventory.candidates) or "none"
        raise ValueError(
            f"index {index} is not in the inventory (available: {available}). "
            "Call list_pdf_figures first, or pass the same pages/ocr arguments."
        )

    bbox = candidate.bbox
    if include_caption and candidate.caption_bbox is not None:
        bbox = bbox.union(candidate.caption_bbox)

    with pymupdf.open(path) as doc:
        page = doc[candidate.page - 1]
        rendered = render_png(page, bbox, dpi=dpi)

    name = f"{path.stem}-p{candidate.page}-{candidate.kind}{index}-{_stamp()}.png"
    target = _write_png(name, rendered.png)
    meta = {
        "local_path": str(target),
        "bytes": rendered.size,
        "mime_type": "image/png",
        "width": rendered.width,
        "height": rendered.height,
        "dpi": round(rendered.dpi, 1),
        "kind": candidate.kind,
        "page": candidate.page,
        "caption": candidate.caption,
        "bbox": bbox.to_list(),
        "scanned": candidate.scanned,
    }
    return [
        TextContent(type="text", text=json.dumps(meta, ensure_ascii=False)),
        _image_block(rendered.png),
    ]


@mcp.tool(
    name="render_pdf_region",
    description=(
        "Render an arbitrary region of a PDF page (absolute PDF points, origin top-left) to "
        "a PNG under the shared figures volume. Use it for an uncaptioned or scanned region "
        "that list_pdf_figures could not bound. Returns the same summary shape as "
        "extract_pdf_figure."
    ),
)
def render_pdf_region(
    filepath: str,
    page: int,
    bbox: list[float],
    dpi: int = DEFAULT_DPI,
) -> list[TextContent | ImageContent]:
    path = _resolve(filepath)
    if len(bbox) != 4:
        raise ValueError("bbox must be [x0, y0, x1, y1] in PDF points.")
    region = BBox.from_any(bbox)
    if region.width <= 0 or region.height <= 0:
        raise ValueError("bbox must have positive width and height.")
    with pymupdf.open(path) as doc:
        if not 1 <= page <= doc.page_count:
            raise ValueError(f"page {page} is outside 1..{doc.page_count}.")
        rendered = render_png(doc[page - 1], region, dpi=dpi)
    target = _write_png(f"{path.stem}-p{page}-region-{_stamp()}.png", rendered.png)
    meta = {
        "local_path": str(target),
        "bytes": rendered.size,
        "mime_type": "image/png",
        "width": rendered.width,
        "height": rendered.height,
        "dpi": round(rendered.dpi, 1),
        "kind": "region",
        "page": page,
        "caption": None,
        "bbox": region.to_list(),
        "scanned": False,
    }
    return [
        TextContent(type="text", text=json.dumps(meta, ensure_ascii=False)),
        _image_block(rendered.png),
    ]


def main() -> None:
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
