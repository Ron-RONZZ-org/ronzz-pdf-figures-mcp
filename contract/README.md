# Dataset manifest contract (pinned)

These files are copied **verbatim** from the ronzz-wikibase EmbeddableContent
extension (`extensions/EmbeddableContent/contract/`), emitted by
`maintenance/emitDatasetContract.php`:

- `dataset-manifest.schema.json` — the manifest (one dataset, N tables).
- `dataset-envelope.schema.json` — `{ manifest, validation_report, manifest_path }`.
- `validation-report.schema.json` — the report shared by the extractor and the wiki.
- `dataset-manifest.example.json` / `dataset-envelope.example.json` — the golden fixtures.

Do not edit them here. Refresh after a wiki-side change:

```sh
cp <ronzz-wikibase>/extensions/EmbeddableContent/contract/dataset-*.json \
   contract/
cp <ronzz-wikibase>/extensions/EmbeddableContent/contract/validation-report.schema.json \
   contract/
```

`tests/test_manifest_contract.py` validates the examples against the pinned
schemas and checks the `pdf_figures.manifest` builder output.

## Handoff

`extract_pdf_table` (follow-up) returns the **envelope**:

```json
{
  "manifest": { "manifest_version": "1.0", "dataset": {}, "tables": [] },
  "validation_report": { "status": "ok", "checks": [], "summary": {}, "tool": "pdf-figures-mcp", "tool_version": "0.2.0", "generated_at": "…" },
  "manifest_path": "/figures/manifests/example-2026-t1-20261122T170000Z.json"
}
```

The MediaWiki MCP `embeddable-dataset-upsert` tool accepts the envelope, a bare manifest,
or a path to either, so the Statistician passes the extractor output unchanged.
The wiki (`action=datasetupsert`) is the authoritative validator; the
extractor's report is advisory.
