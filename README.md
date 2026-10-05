# Rudder Analytics Wine Market Intelligence v0.3.24

## Purpose
This patch fixes a Streamlit live-session integration gap discovered during the 915 Lincoln / VinoShipper regression test.

The 19:58, 20:09, and 20:18 exports were byte-for-byte identical even after parser updates, showing that previously serialized `catalog_offers` could remain in `st.session_state` across a hot reload and bypass the newest VinoShipper final normalization logic.

## Changes
- Re-normalizes every serialized VinoShipper offer immediately before the review table is rendered.
- Recovers the producer ID from the current input, provider note, or stored offer metadata.
- Preserves `provider_id` during optional product-page merge/reconstruction.
- Adds a visible `Catalog parser build: v0.3.24` marker so deployment state is easy to verify.
- Keeps the v0.3.23 provider-normalization rules for blends, ABV, geography, aliases, tier, and confidence.

## Validation
- Python compilation passes.
- 21 catalog enrichment tests pass.
- The exact uploaded 915 Lincoln 20:18 export was replayed through the new session-state finalizer and produced the expected corrected blend, ABV, and geography fields.
