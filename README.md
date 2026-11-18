# pdf-figures-mcp

An MCP tool server that inventories and extracts **figures, tables and captions**
from research-paper PDFs for the **Veramiko Bibliographer** on
`llm.ronzz.org`.

Pipeline:

```
OWUI upload store (ro)  ->  pdf-figures (MCP)  ->  /figures  ->  mediawiki-mcp-writer  ->  wiki File:
```

The wiki writer mounts `/figures` read-only and lists it in `uploadDirs`, so the
`local_path` returned by `extract_pdf_figure` is uploadable verbatim.

## Tools

| Tool | Returns |
|---|---|
| `list_pdf_figures(filepath, pages?, ocr="auto", ocr_langs="eng")` | JSON inventory: `index, kind, page, caption, bbox, caption_bbox, embedded_raster, panels, area_pct, scanned` plus `scanned_pages` / `notes`. No images. |
| `extract_pdf_figure(filepath, index, pages?, dpi=600, include_caption=false, ocr="auto", ocr_langs="eng")` | Text summary (`local_path`, bytes, dimensions, dpi, caption) + a 1024-px PNG preview. The full-resolution PNG is written under `/figures`. |
| `render_pdf_region(filepath, page, bbox, dpi=600)` | Same summary for an arbitrary page region (uncaptioned or scanned content). |

## Detection

- Captions are the anchors: `Figure|Fig.|Table|Scheme|Chart|Diagram|Plate <N>[:.]`
  (the punctuation requirement rejects sentences such as "Table 2 summarizes…").
- Vector paths (`Page.get_drawings()`) and raster images (`Page.get_image_rects()`)
  are clustered; the nearest cluster above or below the caption wins; side-by-side
  panels with one caption are merged.
- Tables are bounded from the caption to the next vertical gap (> 20 pt) or heading.
- Large uncaptioned clusters (≥ 8 % of the page) are listed with `caption: null`.
- **Scanned pages** (no text layer, one image covering ≥ 80 % of the page) are
  detected, reported in `scanned_pages`, and OCR'd **on request** only:
  PyMuPDF `get_textpage_ocr` → Tesseract (`eng`, `fra`, `epo`). The figure band is
  the ink-bounded area on the caption's side of the page.

## Rendering

- Default **600 DPI**, maximum 600.
- Caps: 48 MP, 8000 px on the long edge, one render at a time (`mem_limit 1g`).
- The model preview is downscaled to 1024 px; only the file on `/figures` is full resolution.
- OCR always runs at 300 DPI (Tesseract's accuracy plateau).

## Configuration

| Env | Default |
|---|---|
| `PDF_FIGURES_ALLOWED_ROOTS` | `/app/backend/data/uploads:/figures` (colon-separated) |
| `PDF_FIGURES_OUTPUT_DIR` | `/figures` |
| `PORT` | `8000` |
| `TESSDATA_PREFIX` | `/usr/share/tesseract-ocr/5/tessdata` (Dockerfile) |

Paths are absolute, `realpath`-resolved and checked against the allowlist;
symlinks that escape a root are rejected. Only `.pdf` files are accepted.

## Run

```bash
uv sync --extra dev
uv run pytest
uv run python -m pdf_figures.server          # streamable HTTP on :8000/mcp
```

Docker: `docker build -t pdf-figures .` (arm64 image via CI).

## Licence

AGPL-3.0-or-later (PyMuPDF is AGPL-3.0).
