# Wine Market Intelligence v0.3.18 — geography-confidence patch

Focused follow-up to v0.3.17.

## Changes
- Multi-subregion product pages now preserve the broad AVA and leave `subregion` blank.
- An explicit `Appellation:` field no longer overrides contradictory/multi-area sourcing prose.
- Rows with unresolved multi-subregion geography are capped at `Moderate` confidence.
- Existing catalog enrichment behavior from v0.3.17 is retained.
