"""Build the shared curated-dataset manifest (contract v1.0).

The output is the object the wiki's ``action=datasetupsert`` validates and the
MediaWiki MCP ``embeddable-dataset-upsert`` tool forwards unchanged. ``extract_pdf_table``
returns the transport envelope built here:

    { "manifest": {...}, "validation_report": {...}, "manifest_path": "..." }

The contract files live in ``contract/`` and are pinned verbatim from the
ronzz-wikibase EmbeddableContent extension (see ``contract/README.md``). This
module only assembles the shape; the wiki remains the authoritative validator.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_VERSION = "1.0"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(value: str) -> str:
    """Lower-case, dash-separated stable key (table numbers such as ``2a``)."""
    return _SLUG_RE.sub("-", value.strip().lower()).strip("-")


def table_id(dataset_id: str, table_number: str) -> str:
    return f"{dataset_id}-t{slug(table_number)}"


def panel_id(table: str, panel_key: str) -> str:
    return f"{table}-{panel_key}"


def column_id(table: str, panel_key: str | None, column_key: str) -> str:
    return f"{table}-{panel_key or 'p0'}-{column_key}"


def obs_id(table: str, row_index: int, panel_key: str | None, column_key: str) -> str:
    return f"{table}-r{row_index}-{panel_key or 'p0'}-{column_key}"


def footnote_id(table: str, footnote_key: str) -> str:
    return f"{table}-{footnote_key}"


def build_manifest(dataset: dict[str, Any], tables: list[dict[str, Any]]) -> dict[str, Any]:
    """The manifest object; required fields are enforced by the wiki/schema."""
    return {"manifest_version": MANIFEST_VERSION, "dataset": dataset, "tables": tables}


def build_validation_report(
    *,
    status: str,
    checks: list[dict[str, Any]],
    summary: dict[str, int],
    tool: str = "pdf-figures-mcp",
    tool_version: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """The report shape shared by the extractor and the wiki."""
    return {
        "status": status,
        "checks": checks,
        "summary": summary,
        "tool": tool,
        "tool_version": tool_version,
        "generated_at": generated_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def build_envelope(
    manifest: dict[str, Any],
    validation_report: dict[str, Any],
    manifest_path: str | None = None,
) -> dict[str, Any]:
    envelope: dict[str, Any] = {
        "manifest": manifest,
        "validation_report": validation_report,
    }
    if manifest_path is not None:
        envelope["manifest_path"] = manifest_path
    return envelope


def write_envelope(envelope: dict[str, Any], output_dir: str | Path) -> Path:
    """Write the envelope under ``<output_dir>/manifests/`` and return its path."""
    manifest = envelope["manifest"]
    dataset_id = manifest["dataset"]["dataset_id"]
    table_number = manifest["tables"][0]["table_number"] if manifest["tables"] else "t0"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target_dir = Path(output_dir) / "manifests"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{dataset_id}-t{slug(str(table_number))}-{stamp}.json"
    envelope = {**envelope, "manifest_path": str(target)}
    target.write_text(json.dumps(envelope, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return target


def read_envelope(path: str | Path) -> dict[str, Any]:
    """Read an envelope or a bare manifest and normalise it to the envelope."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "manifest" in data:
        return data
    return {"manifest": data}
