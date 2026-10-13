# Wine Market Intelligence v0.3.28 — Modern-first parsing

This patch makes catalog/product-page extraction prefer modern structured product evidence and become more conservative on legacy storefronts.

## What changed

- Provider/documented feeds remain highest priority.
- JSON-LD / structured Product + Offer data now outranks visible legacy HTML heuristics.
- Selected product pages try to isolate the local product component before using broader page text.
- Navigation/header/footer text cannot override an explicit product title/varietal (for example, a `WHITE & ROSÉ WINES` menu no longer turns red wines into Rosé).
- Quantity-tier prices such as `1–11 $49 / 12+ $44.10` are no longer treated as sale prices.
- Club/member price is populated only when a numeric price is explicitly labeled as club/member pricing.
- Explicit product-local Estate evidence is honored.
- `G-S-M` / `GSM` titles normalize to Grenache, Syrah, Mourvèdre and Rhône Blend.
- Unstructured/legacy selected-page extraction is deliberately capped at Moderate confidence; structured modern records can remain High.

## Regression coverage

39 catalog tests pass, including A&D, VinoShipper/915 Lincoln, Eberle, modern JSON-LD precedence, J. Rickards-style navigation contamination, quantity pricing, club-price labeling, Estate evidence, GSM, and complex Bordeaux blends.

No requirements, secrets, database, or GitHub permission changes are required.
