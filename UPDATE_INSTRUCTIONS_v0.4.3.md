# v0.4.3 UI cleanup

This update is intentionally UI-focused. It does not change catalog extraction, rendered-page behavior, provider precedence, AI evidence rules, or staging logic.

## Replace
- `app.py`

## What changed
- Routine catalog scanning now keeps the primary screen focused on **Winery / producer**, **Catalog URL**, and **Scan**.
- Source-status and AI interpretation controls moved into **Scan settings (optional)**.
- Product-page JavaScript fallback moved into **Product-page scan options** and remains off by default.
- Safeguard text was shortened without weakening the underlying request behavior.
- VinoShipper producer ID remains conditional and is shown only when relevant.
- App display version updated to **v0.4.3**; catalog parser remains **v0.4.2** because parsing logic did not change.

`requirements.txt` must continue to include `playwright>=1.55,<2`, and root `packages.txt` must continue to include `chromium`.
