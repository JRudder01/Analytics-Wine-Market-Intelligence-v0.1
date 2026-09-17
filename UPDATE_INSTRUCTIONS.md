# Rudder Wine Market Intelligence v0.3.9 — Comp Quality + Identity Normalization

This patch stays on the screenshot/clipboard architecture. It does **not** include the experimental URL intake tool.

## Replace these root files in GitHub

- `app.py`
- `pricing_engine.py`
- `data_loader.py`
- `github_storage.py`
- `vision_intake.py`

## Replace this database file

- Replace `data/wine_comps.csv` with the included `data/wine_comps.csv`.

The included database is based on the `wine_comps.csv` supplied immediately before this patch. It contains 137 rows instead of 139 because two true duplicate direct-winery observations were safely collapsed while retaining the more enriched record.

## What changed

### Accent / punctuation / case insensitive matching
Matching now uses a hidden canonical identity key while preserving the original display spelling. Examples that now match:

- `Côtes-du-Rôbles Blanc` = `Cotes du Robles Blanc`
- `CÔTES DU RÔBLES ROUGE` = `Cotes-du-Robles Rouge`
- `EBERLE` = `Eberle` = `Eberle Winery`
- `Détente` = `Detente`

Users do not need to type accented characters for matching.

### Conservative known-label aliases
A few observed historical naming variations now resolve to the same label for matching without rewriting meaningful tier words:

- Eberle `Vineyard Selection Cabernet` = `Vineyard Selection Cabernet Sauvignon`
- Eberle `Full Boar White` = `Full Boar White Blend`
- Détente `Margot` = `Margot Pinot Noir`

### Duplicate-weight protection
The pricing engine no longer gives extra weight to the same product/vintage/price merely because it was entered with different capitalization, punctuation, accents, or an alternate equivalent label.

### Comp ordering / confidence
Comparable selection now prioritizes:

1. same label / other vintage
2. same category + same tier
3. same category + other tier
4. same winery + same tier
5. adjacent-category fallback

Category and tier confidence now use similarity-weighted coverage rather than a raw row percentage. This better reflects the comps that actually drive the recommendation.

### Category repair rules
Only high-confidence classification errors are corrected automatically. Examples:

- Rosé style cannot remain a red-grape category such as Grenache
- a 45% Cab / 30% Barbera / 25% Zin wine becomes `Red Blend`
- an 80% Cab / 20% Zin wine remains `Cabernet Sauvignon`
- a clearly mixed non-Rhône red is not labeled `Rhône Blend`

Existing curated blend categories are otherwise preserved.

### Current database cleanup
The included database also corrects the known issues found in the latest test batch:

- producer case standardized (`EBERLE` → `Eberle`)
- direct source labels standardized where appropriate
- `Vintage of Valor` → `Red Blend`
- 2025 Eberle rosé → `Rosé`
- `Alcarinho` typo → `Alvarinho`
- `100% Estate Cabernet Sauvignon` varietal → `100% Cabernet Sauvignon`
- `Vineyard Selection Cabernet` → `Vineyard Selection Cabernet Sauvignon`
- `Full Boar Red` erroneous 2026 vintage cleared to NV/blank
- exact duplicate current direct-winery rows collapsed without dropping enriched fields

## Validation

The patch was compiled and tested with:

- accent/punctuation equivalence
- producer normalization
- known-label aliases
- blend-category repair
- duplicate model-weight collapse
- unaccented typed target matching accented historical labels
- GitHub merge deduplication
- the recent 2023 Justin Cabernet test case

The Justin benchmark moved from approximately `$31 / $35 / $43` to `$30 / $34 / $41`, with Tier Match improving from `Limited` to `Moderate` after duplicate/category cleanup and weighted confidence scoring.
