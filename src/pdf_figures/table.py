"""Turn a detected table candidate into a curated-dataset manifest table.

Uses PyMuPDF's table finder for the text layer (`page.find_tables(clip=…)`)
and extracts each cell's text with `page.get_text("text", clip=cell_rect)` so
spacing is preserved. Footnotes are marker-bearing cells paired with note
lines below the table; the shape is the shared contract in ``manifest.py``.

This is the extractor half of the contract: the output is handed to
``embeddable-dataset-upsert`` unchanged.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import pymupdf

from .detect import BBox, FigureCandidate

try:
    TOOL_VERSION = version("pdf-figures-mcp")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    TOOL_VERSION = "0.1.0"

MARKER_RE = re.compile(r"([\u2020\u2021\u00a7\u00b6*]+)\s*$")
NOTE_RE = re.compile(r"^\s*([\u2020\u2021\u00a7\u00b6*]+)\s*(.+)$")
TABLE_NUMBER_RE = re.compile(r"\bTable\s+([A-Za-z]?\d+[A-Za-z]?)", re.IGNORECASE)
INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TableExtractionError(RuntimeError):
    """The candidate could not be parsed as a table."""


def extract_table(
    page: pymupdf.Page,
    candidate: FigureCandidate,
    *,
    dataset_id: str,
    pdf_file: str,
    pdf_sha1: str,
    ocr_langs: str = "eng",
    method: str = "auto",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns ``(table_manifest, validation_report)``."""
    clip = pymupdf.Rect(candidate.bbox.x0, candidate.bbox.y0, candidate.bbox.x1, candidate.bbox.y1)
    textpage = None
    table_data = None if method == "ocr" else _text_layer_table(page, clip)
    method_used = "ocr" if candidate.scanned else "text-layer"
    confidence = 0.9
    if table_data is None:
        if method == "text-layer":
            raise TableExtractionError(
                "no table was found in the PDF text layer; retry with method='auto' or 'ocr'"
            )
        if method == "vision":
            raise TableExtractionError(
                "vision extraction is not implemented; use OCR or fill the manifest manually"
            )
        try:
            textpage = page.get_textpage_ocr(language=ocr_langs, dpi=300)
        except Exception as error:  # noqa: BLE001 - surfaced as a TableExtractionError
            raise TableExtractionError(f"OCR is unavailable: {error}") from error
        table_data = _cluster_words(page.get_text("words", clip=clip, textpage=textpage))
        method_used = "ocr"
        confidence = 0.6
    header, data, cell_rects, table_bbox = table_data
    if not data:
        raise TableExtractionError("the table has no data rows")

    datatypes = [_infer_datatype([row[i] for row in data]) for i in range(len(header))]
    column_keys = _unique_keys([_slug(value) or f"c{i + 1}" for i, value in enumerate(header)])
    table_number = _table_number(candidate.caption, candidate.index)
    table_id = f"{dataset_id}-t{_slug(table_number)}"
    page_label = str(candidate.page)

    markers = _markers(data)
    notes = _notes(page, table_bbox, textpage)
    footnotes = _footnotes(markers, notes)
    columns = [
        {
            "panel_key": "p1",
            "column_key": column_keys[i],
            "label": header[i],
            "description": None,
            "unit": None,
            "datatype": datatypes[i],
            "role": _role(i, datatypes[i]),
            "missing_token": "—",
            "sort_order": i + 1,
            "column_parent_key": None,
            "column_level": 1,
        }
        for i in range(len(header))
    ]
    observations = []
    for ri, row in enumerate(data, start=1):
        row_label = row[0].strip() if row else ""
        for ci in range(len(header)):
            text = row[ci].strip()
            marker = MARKER_RE.search(text)
            keys = [markers[marker.group(1)]] if marker and marker.group(1) in markers else []
            observation = {
                "panel_key": "p1",
                "row_index": ri,
                "row_key": _slug(row_label) or f"row{ri}",
                "row_label": row_label or f"Row {ri}",
                "row_path": row_label or f"Row {ri}",
                "row_parent_key": None,
                "row_depth": 1,
                "column_key": column_keys[ci],
                "value_float": None,
                "value_int": None,
                "value_text": text,
                "value_date": None,
                "flag_significant": False,
                "flag_note": None,
                "footnote_keys": keys,
                "source_page": page_label,
                "cell_bbox": cell_rects[ri - 1][ci] if ri - 1 < len(cell_rects) else None,
            }
            _typed_value(observation, datatypes[ci], text)
            observations.append(observation)

    manifest_table = {
        "table_id": table_id,
        "table_number": table_number,
        "caption": candidate.caption or f"Table {table_number}",
        "page": page_label,
        "page_start": candidate.page,
        "page_end": candidate.page,
        "table_bbox": list(table_bbox),
        "caption_bbox": candidate.caption_bbox.to_list() if candidate.caption_bbox else None,
        "source_index": candidate.index,
        "pdf_file": pdf_file,
        "pdf_sha1": pdf_sha1,
        "pdf_revision": None,
        "source_file_access": None,
        "extractor": "pdf-figures-mcp",
        "extractor_version": TOOL_VERSION,
        "method": method_used,
        "confidence": confidence,
        "review_status": "unreviewed",
        "reviewer": None,
        "review_date": None,
        "notes": None,
        "panels": [
            {
                "panel_key": "p1",
                "panel_label": None,
                "panel_order": 1,
                "description": None,
            }
        ],
        "columns": columns,
        "observations": observations,
        "footnotes": footnotes,
        "extraction_runs": [
            {
                "run_id": f"{table_id}-run1",
                "tool": "pdf-figures-mcp",
                "tool_version": TOOL_VERSION,
                "model": None,
                "prompt_version": None,
                "started_at": _now(),
                "finished_at": _now(),
                "status": "ok",
                "confidence": confidence,
                "report_json": None,
                "diff_json": None,
            }
        ],
    }
    report = _report(manifest_table)
    return manifest_table, report


def _text_layer_table(page: pymupdf.Page, clip: pymupdf.Rect):
    found = page.find_tables(clip=clip).tables
    if not found:
        return None
    table = max(found, key=lambda item: len(item.rows) * max(1, item.col_count))
    header_rows = 1 if table.header.names and table.row_count > 1 else 0
    data_rows = table.rows[header_rows:]
    if not data_rows:
        return None
    raw_header = _cell_texts(page, table.rows[header_rows - 1]) if header_rows else []
    header = [
        (raw_header[i] if i < len(raw_header) else "").strip() or f"column {i + 1}"
        for i in range(table.col_count)
    ]
    data = [[_cell_text(page, row.cells[i]) for i in range(table.col_count)] for row in data_rows]
    rects = [[_rect(row.cells[i]) for i in range(table.col_count)] for row in data_rows]
    return header, data, rects, list(table.bbox)


def _cluster_words(words):
    items = [word for word in words if str(word[4]).strip()]
    if not items:
        raise TableExtractionError("OCR found no text in the table region")
    items.sort(key=lambda word: (word[1], word[0]))
    rows: list[list] = []
    current: list = []
    row_y: float | None = None
    for word in items:
        y0 = float(word[1])
        height = float(word[3]) - y0
        if current and row_y is not None and y0 > row_y + max(3.0, height * 0.6):
            rows.append(current)
            current = []
        if not current:
            row_y = y0
        current.append(word)
    if current:
        rows.append(current)
    if len(rows) < 2:
        raise TableExtractionError("OCR found no table rows")
    header_words = rows[0]
    centers = [(float(word[0]) + float(word[2])) / 2 for word in header_words]
    header = [str(word[4]) for word in header_words]
    data = []
    rects = []
    for row in rows[1:]:
        cells = [""] * len(centers)
        cell_rects: list[list[float] | None] = [None] * len(centers)
        buckets: list[list] = [[] for _ in centers]
        for word in row:
            x = (float(word[0]) + float(word[2])) / 2
            index = min(range(len(centers)), key=lambda i: abs(centers[i] - x))
            buckets[index].append(word)
        for index, bucket in enumerate(buckets):
            if bucket:
                cells[index] = " ".join(str(word[4]) for word in bucket)
                cell_rects[index] = _union_rect(bucket)
        data.append(cells)
        rects.append(cell_rects)
    return header, data, rects, _union_rect(items)


def _union_rect(words) -> list[float]:
    return [
        round(min(float(word[0]) for word in words), 2),
        round(min(float(word[1]) for word in words), 2),
        round(max(float(word[2]) for word in words), 2),
        round(max(float(word[3]) for word in words), 2),
    ]


def _cell_texts(page: pymupdf.Page, row: Any) -> list[str]:
    return [_cell_text(page, rect) for rect in row.cells]


def _cell_text(page: pymupdf.Page, rect: Iterable[float] | None) -> str:
    if rect is None:
        return ""
    text = page.get_text("text", clip=pymupdf.Rect(rect)).strip()
    return " ".join(text.split())


def _rect(rect: Iterable[float] | None) -> list[float] | None:
    return None if rect is None else [round(float(v), 2) for v in rect]


def _infer_datatype(values: list[str]) -> str:
    present = [value for value in values if value.strip() != ""]
    if not present:
        return "text"
    if all(INT_RE.match(value) for value in present):
        return "integer"
    if all(INT_RE.match(value) or FLOAT_RE.match(value) for value in present):
        return "float"
    if all(DATE_RE.match(value) for value in present):
        return "date"
    return "text"


def _role(index: int, datatype: str) -> str:
    if index == 0:
        return "dimension"
    return "measure" if datatype in {"integer", "float"} else "note"


def _typed_value(observation: dict[str, Any], datatype: str, text: str) -> None:
    if datatype == "integer" and INT_RE.match(text):
        observation["value_int"] = int(text)
    elif datatype == "float" and (INT_RE.match(text) or FLOAT_RE.match(text)):
        observation["value_float"] = float(text)
    elif datatype == "date" and DATE_RE.match(text):
        observation["value_date"] = text


def _table_number(caption: str | None, index: int) -> str:
    if caption:
        match = TABLE_NUMBER_RE.search(caption)
        if match:
            return match.group(1)
    return str(index)


def _markers(data: list[list[str]]) -> dict[str, str]:
    markers: dict[str, str] = {}
    for row in data:
        for text in row:
            match = MARKER_RE.search(text)
            if match and match.group(1) not in markers:
                markers[match.group(1)] = f"fn{len(markers) + 1}"
    return markers


def _notes(page: pymupdf.Page, table_bbox: BBox | list[float], textpage=None) -> dict[str, str]:
    bottom = (table_bbox.y1 if hasattr(table_bbox, "y1") else float(table_bbox[3])) - 2
    notes: dict[str, str] = {}
    try:
        blocks = (
            page.get_text("blocks", textpage=textpage)
            if textpage is not None
            else page.get_text("blocks")
        )
    except TypeError:
        blocks = page.get_text("blocks")
    for block in blocks:
        if block[1] < bottom:
            continue
        for line in str(block[4]).splitlines():
            match = NOTE_RE.match(line)
            if match and match.group(1) not in notes:
                notes[match.group(1)] = match.group(2).strip()
    return notes


def _footnotes(markers: dict[str, str], notes: dict[str, str]) -> list[dict[str, Any]]:
    footnotes = []
    for marker, key in markers.items():
        text = notes.get(marker)
        footnotes.append(
            {
                "footnote_key": key,
                "marker_raw": marker,
                "text": text if text is not None else "(no note found)",
                "scope": "cell",
                "language": "en",
                "sort_order": len(footnotes) + 1,
                "status": "matched" if text is not None else "missing_note",
            }
        )
    for marker, text in notes.items():
        if marker in markers:
            continue
        footnotes.append(
            {
                "footnote_key": f"fn{len(footnotes) + 1}",
                "marker_raw": marker,
                "text": text,
                "scope": "table",
                "language": "en",
                "sort_order": len(footnotes) + 1,
                "status": "orphan_note",
            }
        )
    return footnotes


def _report(table: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if not table["columns"]:
        checks.append(
            {
                "code": "manifest-invalid",
                "severity": "error",
                "path": "tables[0].columns",
                "message": "no columns were detected",
            }
        )
    if not table["observations"]:
        checks.append(
            {
                "code": "manifest-invalid",
                "severity": "error",
                "path": "tables[0].observations",
                "message": "no data rows were detected",
            }
        )
    for footnote in table["footnotes"]:
        if footnote["status"] == "missing_note":
            checks.append(
                {
                    "code": "referential-integrity",
                    "severity": "warning",
                    "path": f"tables[0].footnotes[{footnote['footnote_key']}]",
                    "message": f"marker {footnote['marker_raw']} has no note",
                }
            )
        if footnote["status"] == "orphan_note":
            checks.append(
                {
                    "code": "referential-integrity",
                    "severity": "warning",
                    "path": f"tables[0].footnotes[{footnote['footnote_key']}]",
                    "message": f"note {footnote['marker_raw']} is not referenced",
                }
            )
    status = (
        "errors"
        if any(c["severity"] == "error" for c in checks)
        else ("warnings" if checks else "ok")
    )
    return {
        "status": status,
        "checks": checks,
        "summary": {
            "tables": 1,
            "panels": len(table["panels"]),
            "columns": len(table["columns"]),
            "observations": len(table["observations"]),
            "footnotes": len(table["footnotes"]),
        },
        "tool": "pdf-figures-mcp",
        "tool_version": TOOL_VERSION,
        "generated_at": _now(),
    }


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def _unique_keys(keys: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for key in keys:
        count = seen.get(key, 0)
        seen[key] = count + 1
        out.append(key if count == 0 else f"{key}-{count + 1}")
    return out


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
