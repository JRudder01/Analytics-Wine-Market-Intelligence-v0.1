# Rudder Analytics Wine Market Intelligence v0.3.27

Small normalization cleanup following the Eberle regression test.

## Changes
- Reserve tier detection now requires the whole word `Reserve`, preventing prose such as `preserve` or `preserves` from creating false Reserve classifications.
- The universal finalizer repairs stale false-positive Reserve rows before review/staging.
- Canonical single-varietal values now remove `100%` and `Estate` qualifiers (for example, `100% Estate Cabernet Sauvignon` becomes `Cabernet Sauvignon`).
- Blend percentages are preserved because they carry useful composition information.
- App and catalog parser build labels updated to v0.3.27.

## Validation
- 33/33 catalog enrichment regression tests pass.
- `app.py` and `catalog_scraper.py` compile successfully.
- Replayed against the latest five-row Eberle export:
  - Côtes du Rôbles Rouge -> Core
  - Estate Cabernet Sauvignon -> Cabernet Sauvignon / Estate
  - Reserve Chardonnay -> Chardonnay / Reserve
  - Steinbeck Syrah -> Syrah / Core
  - Vineyard Selection Cabernet -> Cabernet Sauvignon / Core
