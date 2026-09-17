# Rudder Wine Market Intelligence v0.3.12

Focused comp-quality patch for the screenshot/clipboard build.

Changes:
- White Rhône-style blends are normalized to `White Blend` for market matching.
- Exact-category matching now requires compatible broad categories (Red/White/Rosé).
- Cross-color wines can only act as distant fallback evidence and receive a strong weight penalty.
- `Cotes-du-Robles Blanc` is corrected to `White Blend / White` in the included comp database.
- Comparable price landscape vintage ticks are forced to whole years.

No URL-fetching/scraping functionality is included.
