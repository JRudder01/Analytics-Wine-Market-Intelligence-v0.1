# Rudder Wine Market Intelligence v0.3.7 patch

Replace only the repository-root `vision_intake.py`.

Changes:
- Stronger Estate detection for whole-wine phrases such as “crafted from Estate Chardonnay”, while keeping component-only estate mentions false.
- Direct winery producer/source names are canonicalized for consistency (for example `Eberle Winery` -> `Eberle`, `JUSTIN Vineyards & Winery` -> `JUSTIN`).
- Product tier remains independent: a Reserve made from estate fruit stays `Reserve` with `estate = TRUE`.
