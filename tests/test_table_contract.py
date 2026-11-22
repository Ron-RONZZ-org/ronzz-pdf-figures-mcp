from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pymupdf

from pdf_figures import server
from pdf_figures.inventory import build_inventory
from pdf_figures.paths import AllowedRoots
from pdf_figures.table import _cluster_words, extract_table

CONTRACT = Path(__file__).resolve().parent.parent / "contract"


def load(name: str) -> dict:
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


def test_extract_table_maps_rows_columns_and_typed_values(fixtures) -> None:
    path = fixtures["table"]
    with pymupdf.open(path) as doc:
        inventory = build_inventory(doc)
        candidate = next(item for item in inventory.candidates if item.kind == "table")
        table, report = extract_table(
            doc[candidate.page - 1],
            candidate,
            dataset_id="fixture-2026",
            pdf_file=path.name,
            pdf_sha1=hashlib.sha1(path.read_bytes()).hexdigest(),
        )
    assert table["table_id"] == "fixture-2026-t1"
    assert table["table_number"] == "1"
    assert [column["label"] for column in table["columns"]] == ["Layer", "Complexity", "Path"]
    assert len(table["observations"]) == 9
    assert table["columns"][0]["role"] == "dimension"
    assert report["status"] == "ok"
    manifest = {
        "manifest_version": "1.0",
        "dataset": {"dataset_id": "fixture-2026", "title": "Fixture", "access_tier": "public"},
        "tables": [table],
    }
    jsonschema.validate(manifest, load("dataset-manifest.schema.json"))


def test_extract_table_pairs_footnotes(fixtures) -> None:
    path = fixtures["table_footnote"]
    with pymupdf.open(path) as doc:
        inventory = build_inventory(doc)
        candidate = next(item for item in inventory.candidates if item.kind == "table")
        table, report = extract_table(
            doc[candidate.page - 1],
            candidate,
            dataset_id="footnote-2026",
            pdf_file=path.name,
            pdf_sha1=hashlib.sha1(path.read_bytes()).hexdigest(),
        )
    assert table["footnotes"][0]["footnote_key"] == "fn1"
    assert table["footnotes"][0]["status"] == "matched"
    assert table["observations"][0]["footnote_keys"] == ["fn1"]
    assert table["columns"][1]["datatype"] == "float"
    assert table["observations"][1]["value_float"] == 0.42
    assert report["status"] == "ok"


def test_extract_pdf_table_returns_the_manifest_envelope(fixtures, tmp_path, monkeypatch) -> None:
    path = fixtures["table"]
    monkeypatch.setattr(server, "ALLOWED_ROOTS", AllowedRoots([path.parent]))
    monkeypatch.setattr(server, "OUTPUT_DIR", tmp_path)
    result = server.extract_pdf_table(
        str(path),
        1,
        dataset={"dataset_id": "fixture-2026", "title": "Fixture table"},
        pdf_file="fixture.pdf",
    )
    assert len(result) == 2
    envelope = json.loads(result[0].text)
    jsonschema.validate(envelope, load("dataset-envelope.schema.json"))
    jsonschema.validate(envelope["validation_report"], load("validation-report.schema.json"))
    assert envelope["manifest"]["dataset"]["dataset_id"] == "fixture-2026"
    assert envelope["manifest"]["tables"][0]["table_id"] == "fixture-2026-t1"
    assert Path(envelope["manifest_path"]).exists()
    assert result[1].type == "image"


def test_cluster_words_builds_the_ocr_fallback_table() -> None:
    words = [
        (10, 10, 50, 20, "Method", 0, 0, 0),
        (100, 10, 140, 20, "Effect", 0, 0, 1),
        (10, 30, 60, 40, "Attention", 0, 1, 0),
        (100, 30, 140, 40, "0.42", 0, 1, 1),
        (10, 50, 60, 60, "Recurrent", 0, 2, 0),
        (100, 50, 140, 60, "0.18", 0, 2, 1),
    ]
    header, data, rects, bbox = _cluster_words(words)
    assert header == ["Method", "Effect"]
    assert data == [["Attention", "0.42"], ["Recurrent", "0.18"]]
    assert len(rects) == 2
    assert bbox == [10.0, 10.0, 140.0, 60.0]
