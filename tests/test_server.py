from __future__ import annotations

import json
from pathlib import Path

from pdf_figures import server
from pdf_figures.paths import AllowedRoots


def configure(monkeypatch, root: Path, output: Path) -> None:
    monkeypatch.setattr(server, "ALLOWED_ROOTS", AllowedRoots([root]))
    monkeypatch.setattr(server, "OUTPUT_DIR", output)


def test_list_inventory(fixtures, tmp_path, monkeypatch):
    configure(monkeypatch, fixtures["raster"].parent, tmp_path)
    payload = json.loads(server.list_pdf_figures(str(fixtures["raster"])))
    assert payload["pages"] == 1
    caption = payload["figures"][0]["caption"]
    assert caption.startswith("Figure 1")
    assert payload["figures"][0]["bbox"]


def test_extract_returns_text_and_image(fixtures, tmp_path, monkeypatch):
    configure(monkeypatch, fixtures["raster"].parent, tmp_path)
    payload = json.loads(server.list_pdf_figures(str(fixtures["raster"])))
    index = payload["figures"][0]["index"]
    result = server.extract_pdf_figure(str(fixtures["raster"]), index)
    assert len(result) == 2
    meta = json.loads(result[0].text)
    assert meta["kind"] == "figure"
    assert meta["page"] == 1
    assert Path(meta["local_path"]).exists()
    assert meta["local_path"].startswith(str(tmp_path))
    assert result[1].type == "image"


def test_extract_rejects_unknown_index(fixtures, tmp_path, monkeypatch):
    configure(monkeypatch, fixtures["raster"].parent, tmp_path)
    import pytest

    with pytest.raises(ValueError, match="not in the inventory"):
        server.extract_pdf_figure(str(fixtures["raster"]), 999)


def test_region_render(fixtures, tmp_path, monkeypatch):
    configure(monkeypatch, fixtures["raster"].parent, tmp_path)
    result = server.render_pdf_region(str(fixtures["raster"]), 1, [150, 422, 450, 622])
    meta = json.loads(result[0].text)
    assert meta["kind"] == "region"
    assert Path(meta["local_path"]).exists()
