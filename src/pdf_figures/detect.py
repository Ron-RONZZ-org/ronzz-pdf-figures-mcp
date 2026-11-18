"""Figure, table and caption detection for PDF pages.

The detector is pure (no I/O, no MediaWiki): it takes a PyMuPDF page and
returns :class:`FigureCandidate` records.  Captions are the anchors: a
caption block is matched by :data:`CAPTION_RE`, then associated with the
nearest graphic cluster above or below it.  Tables are bounded by their
caption and the next vertical gap or heading.

Scanned pages (no text layer, one full-page image) are detected separately;
they need Tesseract OCR first (see :mod:`pdf_figures.ocr`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import pymupdf

CAPTION_RE = re.compile(
    r"^\s*(?P<kind>figure|fig\.?|table|scheme|chart|diagram|plate)\s*"
    r"(?P<number>S?\d+|[IVXLC]+)\s*[.:)\]\-\u2013\u2014]",
    re.IGNORECASE,
)

# A block this much larger than the body text is a heading.
HEADING_DELTA = 1.5
# Vertical gap that ends a table body.
TABLE_GAP = 20.0
# Maximum distance between a caption and its graphic.
ASSOCIATION_WINDOW = 200.0
# Minimum cluster area as a fraction of the page for an uncaptioned candidate.
UNCAPTIONED_MIN_AREA = 0.08
# A page image covering this much of the page makes the page a scan.
SCAN_COVERAGE = 0.80


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def expanded(self, pad: float) -> BBox:
        return BBox(self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)

    def union(self, other: BBox) -> BBox:
        return BBox(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def intersects(self, other: BBox) -> bool:
        return not (
            self.x1 <= other.x0 or other.x1 <= self.x0 or self.y1 <= other.y0 or other.y1 <= self.y0
        )

    def contains(self, other: BBox) -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and self.x1 >= other.x1
            and self.y1 >= other.y1
        )

    def intersection_area(self, other: BBox) -> float:
        x0, y0 = max(self.x0, other.x0), max(self.y0, other.y0)
        x1, y1 = min(self.x1, other.x1), min(self.y1, other.y1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return (x1 - x0) * (y1 - y0)

    def to_list(self) -> list[float]:
        return [round(self.x0, 2), round(self.y0, 2), round(self.x1, 2), round(self.y1, 2)]

    @classmethod
    def from_any(cls, value: Iterable[float]) -> BBox:
        x0, y0, x1, y1 = (float(v) for v in value)
        return cls(x0, y0, x1, y1)


@dataclass(frozen=True)
class TextBlock:
    bbox: BBox
    text: str
    size: float


@dataclass
class FigureCandidate:
    index: int
    kind: str  # "figure" | "table"
    page: int  # 1-based
    caption: str | None
    bbox: BBox
    caption_bbox: BBox | None = None
    embedded_raster: bool = False
    panels: int = 1
    area_pct: float = 0.0
    scanned: bool = False

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "kind": self.kind,
            "page": self.page,
            "caption": self.caption,
            "bbox": self.bbox.to_list(),
            "caption_bbox": self.caption_bbox.to_list() if self.caption_bbox else None,
            "embedded_raster": self.embedded_raster,
            "panels": self.panels,
            "area_pct": round(self.area_pct, 2),
            "scanned": self.scanned,
        }


def page_bbox(page: pymupdf.Page) -> BBox:
    return BBox.from_any((page.rect.x0, page.rect.y0, page.rect.x1, page.rect.y1))


def page_text_blocks(
    page: pymupdf.Page, textpage: pymupdf.TextPage | None = None
) -> list[TextBlock]:
    """Text blocks with their bbox and largest span size.

    ``textpage`` lets the caller substitute an OCR text page for a scan.
    """
    if textpage is not None:
        raw = page.get_text("dict", textpage=textpage)
    else:
        raw = page.get_text("dict")
    blocks: list[TextBlock] = []
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
        text = re.sub(r"\s+", " ", " ".join(span.get("text", "") for span in spans)).strip()
        if not text:
            continue
        size = max((float(span.get("size", 0)) for span in spans), default=0.0)
        blocks.append(TextBlock(BBox.from_any(block["bbox"]), text, size))
    return blocks


def body_font_size(blocks: list[TextBlock]) -> float:
    sizes = sorted(block.size for block in blocks if block.size > 0)
    if not sizes:
        return 0.0
    return sizes[len(sizes) // 2]


def caption_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    return [block for block in blocks if CAPTION_RE.match(block.text)]


def caption_kind(text: str) -> str:
    match = CAPTION_RE.match(text)
    if match and match.group("kind").lower().startswith("table"):
        return "table"
    return "figure"


def image_rects(page: pymupdf.Page) -> list[BBox]:
    rects: list[BBox] = []
    for item in page.get_images(full=True):
        xref = item[0]
        for rect in page.get_image_rects(xref):
            bbox = BBox.from_any(rect)
            if bbox.area > 4:
                rects.append(bbox)
    return rects


def graphic_rects(page: pymupdf.Page) -> list[BBox]:
    """Vector paths and raster images, minus hairline noise."""
    rects: list[BBox] = []
    for drawing in page.get_drawings():
        bbox = BBox.from_any(drawing["rect"])
        if bbox.width > 2 and bbox.height > 2 and bbox.area > 4:
            rects.append(bbox)
    rects.extend(image_rects(page))
    return rects


def cluster_rects(rects: list[BBox], gap: float = 12.0) -> list[BBox]:
    """Union overlapping or near-touching rectangles until stable."""
    items = list(rects)
    changed = True
    while changed:
        changed = False
        out: list[BBox] = []
        used = [False] * len(items)
        for i, first in enumerate(items):
            if used[i]:
                continue
            current = first
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                if current.expanded(gap).intersects(items[j]):
                    current = current.union(items[j])
                    used[j] = True
                    changed = True
            out.append(current)
        items = out
    return items


def is_full_page(bbox: BBox, page: BBox) -> bool:
    return page.area > 0 and bbox.area / page.area >= 0.9


def _nearest_cluster(caption: TextBlock, clusters: list[BBox]) -> tuple[BBox | None, str | None]:
    best: tuple[float, BBox, str] | None = None
    for cluster in clusters:
        if cluster.intersects(caption.bbox):
            # A drawing or raster may reach into the caption band (a frame,
            # an axis label). Keep the side with more of the cluster.
            above_height = caption.bbox.y0 - cluster.y0
            below_height = cluster.y1 - caption.bbox.y1
            if above_height <= 4 and below_height <= 4:
                continue
            if above_height >= below_height:
                trimmed = BBox(
                    cluster.x0, cluster.y0, cluster.x1, max(cluster.y0, caption.bbox.y0 - 2)
                )
                candidate = (0.0, trimmed, "above")
            else:
                trimmed = BBox(
                    cluster.x0, min(cluster.y1, caption.bbox.y1 + 2), cluster.x1, cluster.y1
                )
                candidate = (0.0, trimmed, "below")
            if trimmed.height <= 4:
                continue
        else:
            gap_above = caption.bbox.y0 - cluster.y1
            if 0 <= gap_above <= ASSOCIATION_WINDOW:
                candidate = (gap_above, cluster, "above")
            else:
                gap_below = cluster.y0 - caption.bbox.y1
                if not 0 <= gap_below <= ASSOCIATION_WINDOW:
                    continue
                candidate = (gap_below, cluster, "below")
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        return None, None
    return best[1], best[2]


def _merge_panels(
    primary: BBox,
    clusters: list[BBox],
    side: str,
    caption: TextBlock,
    page_width: float,
) -> BBox:
    """Union side-by-side panels that share one caption.

    A full-width caption claims every graphic above/below it inside its
    horizontal span; a narrow caption only merges panels with a small gap.
    """
    full_width = caption.bbox.width >= 0.6 * page_width
    region = primary
    changed = True
    while changed:
        changed = False
        for cluster in clusters:
            if cluster.intersects(region) or cluster.intersects(caption.bbox):
                continue
            if side == "above" and cluster.y1 > caption.bbox.y0 + 2:
                continue
            if side == "below" and cluster.y0 < caption.bbox.y1 - 2:
                continue
            vertical_overlap = min(region.y1, cluster.y1) - max(region.y0, cluster.y0)
            smallest = min(region.height, cluster.height)
            if smallest <= 0 or vertical_overlap < 0.3 * smallest:
                continue
            if full_width:
                if cluster.x1 < caption.bbox.x0 or cluster.x0 > caption.bbox.x1:
                    continue
                region = region.union(cluster)
                changed = True
                continue
            gap = max(cluster.x0 - region.x1, region.x0 - cluster.x1)
            if 0 <= gap <= 30:
                region = region.union(cluster)
                changed = True
    return region


def _table_region(
    caption: TextBlock,
    blocks: list[TextBlock],
    clusters: list[BBox],
    body_size: float,
    page_height: float,
) -> BBox | None:
    """Bound a table between its caption and the next gap, heading or figure."""
    upward = caption.bbox.y0 > page_height / 2
    candidates = [block for block in blocks if block is not caption]

    if upward:
        ordered = sorted(
            (block for block in candidates if block.bbox.y1 <= caption.bbox.y0 + 2),
            key=lambda block: -block.bbox.y1,
        )
        previous_edge = caption.bbox.y0
    else:
        ordered = sorted(
            (block for block in candidates if block.bbox.y0 >= caption.bbox.y1 - 2),
            key=lambda block: block.bbox.y0,
        )
        previous_edge = caption.bbox.y1

    region: BBox | None = None
    for block in ordered:
        gap = previous_edge - block.bbox.y1 if upward else block.bbox.y0 - previous_edge
        is_heading = (
            body_size > 0 and block.size > body_size + HEADING_DELTA and len(block.text) < 120
        )
        if region is not None and (gap > TABLE_GAP or is_heading):
            break
        region = block.bbox if region is None else region.union(block.bbox)
        previous_edge = block.bbox.y0 if upward else block.bbox.y1
    if region is None:
        return None

    # Thin rules (table borders) inside the text span.
    for cluster in clusters:
        if (
            cluster.y0 >= region.y0 - 4
            and cluster.y1 <= region.y1 + 4
            and cluster.x0 >= region.x0 - 4
            and cluster.x1 <= region.x1 + 4
        ):
            region = region.union(cluster)
    return region


def _count_panels(region: BBox, images: list[BBox]) -> int:
    inside = [image for image in images if region.intersection_area(image) > 0.5 * image.area]
    return max(1, len(inside))


def _embedded_raster(region: BBox, images: list[BBox]) -> bool:
    return any(region.intersection_area(image) >= 0.5 * region.area for image in images)


def is_scanned_page(page: pymupdf.Page, pages_bbox: BBox | None = None) -> bool:
    """No usable text layer and one image covering most of the page."""
    if len(page.get_text("text").strip()) > 20:
        return False
    page_rect = pages_bbox or page_bbox(page)
    images = image_rects(page)
    return any(image.area / page_rect.area >= SCAN_COVERAGE for image in images)


def detect_page(
    page: pymupdf.Page,
    page_number: int,
    *,
    textpage: pymupdf.TextPage | None = None,
    scanned: bool = False,
) -> list[FigureCandidate]:
    """Captioned figures/tables plus large uncaptioned graphic clusters."""
    blocks = page_text_blocks(page, textpage=textpage)
    if not blocks:
        return []
    body_size = body_font_size(blocks)
    page_rect = page_bbox(page)
    images = image_rects(page)
    clusters = [
        cluster
        for cluster in cluster_rects(graphic_rects(page))
        if not is_full_page(cluster, page_rect)
    ]
    found: list[tuple[float, float, FigureCandidate]] = []
    used: list[BBox] = []

    for caption in caption_blocks(blocks):
        kind = caption_kind(caption.text)
        if kind == "table":
            region = _table_region(caption, blocks, clusters, body_size, page_rect.height)
        else:
            region, side = _nearest_cluster(caption, clusters)
            if region is not None and side is not None:
                region = _merge_panels(region, clusters, side, caption, page_rect.width)
        if region is None:
            continue
        if kind == "figure":
            used.append(region)
        found.append(
            (
                caption.bbox.y0,
                caption.bbox.x0,
                FigureCandidate(
                    index=0,
                    kind=kind,
                    page=page_number,
                    caption=caption.text,
                    bbox=region,
                    caption_bbox=caption.bbox,
                    embedded_raster=_embedded_raster(region, images),
                    panels=_count_panels(region, images),
                    area_pct=100.0 * region.area / page_rect.area,
                    scanned=scanned,
                ),
            )
        )

    for cluster in clusters:
        if any(cluster.intersects(region) for region in used):
            continue
        if cluster.area / page_rect.area < UNCAPTIONED_MIN_AREA:
            continue
        found.append(
            (
                cluster.y0,
                cluster.x0,
                FigureCandidate(
                    index=0,
                    kind="figure",
                    page=page_number,
                    caption=None,
                    bbox=cluster,
                    embedded_raster=_embedded_raster(cluster, images),
                    panels=_count_panels(cluster, images),
                    area_pct=100.0 * cluster.area / page_rect.area,
                    scanned=scanned,
                ),
            )
        )

    found.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in found]
