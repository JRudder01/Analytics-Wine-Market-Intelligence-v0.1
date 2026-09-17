# Rudder Wine Market Intelligence v0.3.10

## Known-wine search fix

Replace the root-level `app.py` with the included version.

The Pricing Analysis known-wine selector now has a normalized search field. Search ignores:

- accents/diacritics (`Côtes` = `Cotes`)
- capitalization (`EBERLE` = `Eberle`)
- hyphens and punctuation (`Cotes-du-Robles` = `Cotes du Robles`)
- repeated spacing

Examples that now match the same wine include:

- `cotes du rob`
- `Cotes-du-Robles Blanc`
- `CÔTES DU RÔBLES BLANC`

This patch changes only the Pricing Analysis search UI. The v0.3.9 identity normalization and pricing behavior remain in place.
