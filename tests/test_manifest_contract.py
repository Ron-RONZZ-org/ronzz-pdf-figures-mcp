from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from pdf_figures import manifest as manifest_builder

CONTRACT = Path(__file__).resolve().parent.parent / "contract"


def load(name: str) -> dict:
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


def test_golden_manifest_validates() -> None:
    jsonschema.validate(load("dataset-manifest.example.json"), load("dataset-manifest.schema.json"))


def test_golden_envelope_and_report_validate() -> None:
    envelope = load("dataset-envelope.example.json")
    jsonschema.validate(envelope, load("dataset-envelope.schema.json"))
    jsonschema.validate(envelope["validation_report"], load("validation-report.schema.json"))


def test_builder_round_trips_the_golden_manifest() -> None:
    example = load("dataset-manifest.example.json")
    built = manifest_builder.build_manifest(example["dataset"], example["tables"])
    assert built == example
    jsonschema.validate(built, load("dataset-manifest.schema.json"))


def test_stable_ids_follow_the_contract_formula() -> None:
    table = manifest_builder.table_id("example-2026", "1")
    assert table == "example-2026-t1"
    assert manifest_builder.table_id("example-2026", "2a") == "example-2026-t2a"
    assert manifest_builder.panel_id(table, "p1") == "example-2026-t1-p1"
    assert manifest_builder.column_id(table, "p1", "d") == "example-2026-t1-p1-d"
    assert manifest_builder.column_id(table, None, "d") == "example-2026-t1-p0-d"
    assert manifest_builder.obs_id(table, 1, "p1", "d") == "example-2026-t1-r1-p1-d"
    assert manifest_builder.footnote_id(table, "fn1") == "example-2026-t1-fn1"


def test_build_report_and_write_envelope(tmp_path: Path) -> None:
    example = load("dataset-manifest.example.json")
    report = manifest_builder.build_validation_report(
        status="ok",
        checks=[],
        summary={"tables": 1, "panels": 1, "columns": 2, "observations": 4, "footnotes": 1},
        tool_version="0.2.0",
    )
    jsonschema.validate(report, load("validation-report.schema.json"))

    envelope = manifest_builder.build_envelope(example, report)
    jsonschema.validate(envelope, load("dataset-envelope.schema.json"))

    path = manifest_builder.write_envelope(envelope, tmp_path)
    assert path.exists()
    assert path.parent.name == "manifests"
    written = manifest_builder.read_envelope(path)
    assert written["manifest"] == example
    assert written["manifest_path"] == str(path)
