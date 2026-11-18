"""Synthetic PDF fixtures for the detector tests.

Each builder writes one PDF.  The fixtures are generated at test time so no
binary files are committed and the geometry stays in one place.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = A4


def _bar_image(path: Path) -> Path:
    image = Image.new("RGB", (300, 200), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for index in range(6):
        left = 20 + index * 44
        draw.rectangle([left, 20 + index * 8, left + 30, 180], fill=(30 + index * 25, 90, 170))
    image.save(path)
    return path


def _body_text(pdf: canvas.Canvas, top: float = 72, lines: int = 8) -> None:
    pdf.setFont("Helvetica", 10)
    text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
    for index in range(lines):
        pdf.drawString(60, PAGE_HEIGHT - top - index * 14, text)


def make_raster_figure(path: Path) -> Path:
    image = _bar_image(path.with_suffix(".png"))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _body_text(pdf)
    pdf.drawImage(str(image), 150, 220, width=300, height=200)
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(150, 200, "Figure 1: A raster bar chart used as a fixture.")
    pdf.showPage()
    pdf.save()
    return path


def make_vector_figure(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _body_text(pdf)
    pdf.rect(150, 220, 300, 200, stroke=1, fill=0)
    pdf.line(150, 220, 450, 420)
    pdf.line(150, 420, 450, 220)
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(150, 200, "Figure 2: A vector diagram used as a fixture.")
    pdf.showPage()
    pdf.save()
    return path


def make_table(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(60, PAGE_HEIGHT - 72, "Table 1: Results of the fixture experiment.")
    rows = [
        ("Layer", "Complexity", "Path"),
        ("Self-attention", "O(n^2)", "1"),
        ("Recurrent", "O(n)", "n"),
        ("Convolution", "O(k n)", "log n"),
    ]
    top = PAGE_HEIGHT - 110
    for row, values in enumerate(rows):
        y = top - row * 22
        for column, value in enumerate(values):
            pdf.setFont("Helvetica", 9)
            pdf.drawString(64 + column * 140, y, value)
        pdf.line(60, y - 4, 520, y - 4)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        60, top - 150, "The table above is followed by body text with a large vertical gap."
    )
    pdf.showPage()
    pdf.save()
    return path


def make_false_caption(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _body_text(pdf)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(60, PAGE_HEIGHT - 260, "Table 2 summarizes our results and compares our model.")
    pdf.showPage()
    pdf.save()
    return path


def make_multi_panel(path: Path) -> Path:
    first = _bar_image(path.with_name(path.stem + "-a.png"))
    second = _bar_image(path.with_name(path.stem + "-b.png"))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _body_text(pdf)
    pdf.drawImage(str(first), 100, 220, width=140, height=200)
    pdf.drawImage(str(second), 260, 220, width=140, height=200)
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(100, 200, "Figure 3: Two panels sharing one caption.")
    pdf.showPage()
    pdf.save()
    return path


def make_two_column(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setFont("Helvetica", 9)
    for index in range(20):
        pdf.drawString(60, PAGE_HEIGHT - 80 - index * 12, "Left column text for the fixture page.")
        pdf.drawString(
            310, PAGE_HEIGHT - 80 - index * 12, "Right column text for the fixture page."
        )
    pdf.setStrokeColorRGB(0.2, 0.2, 0.2)
    pdf.rect(310, 240, 230, 150, stroke=1, fill=0)
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.drawString(310, 220, "Figure 4: A figure in the right column.")
    pdf.showPage()
    pdf.save()
    return path


def make_no_figures(path: Path) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    _body_text(pdf, lines=30)
    pdf.showPage()
    pdf.save()
    return path


def make_scanned(path: Path) -> Path:
    """Render a page to an image, then embed it as a text-less page."""
    inner = path.with_name(path.stem + "-inner.pdf")
    make_raster_figure(inner)
    with pymupdf.open(inner) as document:
        pixmap = document[0].get_pixmap(dpi=150)
        scan_png = path.with_name(path.stem + ".png")
        pixmap.save(scan_png)
    with pymupdf.open() as output:
        page = output.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page.insert_image(page.rect, filename=str(scan_png))
        output.save(path)
    return path


BUILDERS = {
    "raster": make_raster_figure,
    "vector": make_vector_figure,
    "table": make_table,
    "false_caption": make_false_caption,
    "multi_panel": make_multi_panel,
    "two_column": make_two_column,
    "no_figures": make_no_figures,
    "scanned": make_scanned,
}


def build_all(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return {name: builder(directory / f"{name}.pdf") for name, builder in BUILDERS.items()}
