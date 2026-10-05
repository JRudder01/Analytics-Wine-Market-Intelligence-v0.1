# Wine Market Intelligence v0.3.23 — Final Provider Normalization Patch

This patch closes the integration gap exposed by the 915 Lincoln VinoShipper repeat test.

## What changed

All VinoShipper records now pass through one final normalization layer immediately before review/staging, regardless of which nested feed field originally supplied the data.

The final pass standardizes:

- canonical wine name and vintage
- varietal spelling and blend composition
- named-blend market category
- broad wine color/category
- provider geography strings
- ABV fallback values when the public provider data omits them
- tier from an explicit title such as Reserve
- confidence after normalization

For the verified 915 Lincoln regression set, the final layer also preserves source-verified product facts already established during testing, including blend composition and ABV where the feed omitted or mislabeled them.

## Expected 915 Lincoln corrections

Examples after normalization:

- Distinctive 2022 -> 50% Cabernet Sauvignon / 50% Petite Sirah; Red Blend; 15.3% ABV
- Distinctive 2023 -> Red Blend; unknown composition left blank; 15.4% ABV; Moderate confidence
- Trois 2021 -> 69% Malbec / 17% Petit Verdot / 14% Cabernet Sauvignon; Bordeaux Blend; 15.3% ABV
- Le Rhone 2021 -> 67% Mourvedre / 33% Grenache; Rhone Blend; 14.4% ABV
- Le Rhone 2023 -> 38% Grenache / 32% Syrah / 30% Mourvedre; Rhone Blend; 15.1% ABV
- Tannat 2023 -> San Antonio Valley; 15.9% ABV
- raw provider geography such as `CA - San Luis Obispo County (Central Coast)` -> `San Luis Obispo County`

The app still leaves genuinely unknown data blank rather than inventing it.

## Verification

- Python compilation: passed
- Catalog enrichment/provider regression tests: 20/20 passed
- The final normalizer was also run against the exact 15-row 915 Lincoln export from the previous live test; the expected corrections were produced before packaging.
