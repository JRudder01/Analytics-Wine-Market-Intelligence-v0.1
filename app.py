from __future__ import annotations

from pathlib import Path
import hashlib
import io

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from streamlit_paste_button import paste_image_button
except Exception:
    paste_image_button = None

from data_loader import (
    load_comps,
    load_public_context,
    load_upload,
    load_rudder_pricing_workbook,
    load_reference_table,
    merge_data,
    VISITOR_PATH,
    FEES_PATH,
)
from pricing_engine import analyze_wine, normalize_comp_data
from public_data import refresh_all_public_data
from vision_intake import (
    extract_wine_from_images,
    build_comp_record,
    duplicate_matches,
    TIERS,
    PRICE_TYPES,
    CONFIDENCE_LEVELS,
    get_default_model,
)

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"

st.set_page_config(
    page_title="Rudder Analytics | Wine Market Intelligence",
    page_icon="🍷",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container {padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1280px;}
.ra-subtitle {font-size: 1.08rem; color: #58758d; margin-top: -0.45rem; margin-bottom: 1.2rem;}
.ra-card {border: 1px solid #dfe8ee; border-radius: 14px; padding: 1rem 1.1rem; background: #ffffff;}
.ra-note {font-size: 0.88rem; color: #667985;}
div[data-testid="stMetric"] {border: 1px solid #dfe8ee; border-radius: 12px; padding: 0.8rem;}
</style>
""",
    unsafe_allow_html=True,
)

header_left, header_right = st.columns([2.1, 7.9])
with header_left:
    st.image(str(ASSETS / "rudder_wordmark.png"), width=265)
with header_right:
    st.title("Wine Market Intelligence")
    st.markdown('<div class="ra-subtitle">Pricing, comparable-market & AI-assisted data intake · v0.3</div>', unsafe_allow_html=True)

seed = load_comps()
context = load_public_context()
if "uploaded_comps" not in st.session_state:
    st.session_state.uploaded_comps = None
all_data = merge_data(seed, st.session_state.uploaded_comps)

page = st.sidebar.radio("Workspace", ["Pricing Analysis", "Data Hub (Admin)", "Methodology"])
st.sidebar.caption(f"{len(all_data):,} usable pricing observations loaded")
st.sidebar.caption(f"{all_data['winery'].nunique():,} wineries represented")


def _known_label(r):
    vint = int(r["vintage"]) if pd.notna(r["vintage"]) else "NV"
    return f"{r['winery']} — {vint} {r['wine']}"


if page == "Pricing Analysis":
    st.subheader("1. Identify the wine")
    st.caption("Start with a known comparable or enter a new/unreleased wine. v0.3 uses the expanded Paso workbook, public market context, and AI-assisted comp intake.")

    known = st.toggle("Start from a known wine", value=True)
    defaults = {}
    if known:
        known_df = all_data.sort_values(["winery", "wine", "vintage"], ascending=[True, True, False]).copy()
        known_df["label"] = known_df.apply(_known_label, axis=1)
        default_idx = 0
        mask = known_df["label"].str.contains("Eberle — 2023 Vineyard Selection Cabernet", case=False, na=False)
        if mask.any():
            default_idx = int(np.flatnonzero(mask.to_numpy())[0])
        selection = st.selectbox("Known wine", known_df["label"].tolist(), index=default_idx)
        row = known_df.loc[known_df["label"].eq(selection)].iloc[0]
        defaults = row.to_dict()
        st.info("The selected wine's own price is excluded from its comparable analysis. Use Historical backtest mode to also exclude later vintages.")

    c1, c2, c3, c4 = st.columns(4)
    winery = c1.text_input("Winery / producer", value=str(defaults.get("winery", "")))
    wine = c2.text_input("Wine / label", value=str(defaults.get("wine", "")))
    vint_val = defaults.get("vintage", np.nan)
    vintage_default = int(vint_val) if pd.notna(vint_val) else 2024
    vintage = c3.number_input("Vintage", min_value=1990, max_value=2035, value=vintage_default, step=1)
    region = c4.text_input("Region / AVA", value=str(defaults.get("region", "Paso Robles") or "Paso Robles"))

    c1, c2, c3, c4 = st.columns(4)
    graph_options = sorted(set(all_data["graph_category"].replace("", np.nan).dropna().tolist() + ["Cabernet Sauvignon", "Bordeaux Blend"]))
    graph_default = str(defaults.get("graph_category", "Cabernet Sauvignon") or "Cabernet Sauvignon")
    graph_idx = graph_options.index(graph_default) if graph_default in graph_options else 0
    graph_category = c1.selectbox("Market category", graph_options, index=graph_idx)
    subregion = c2.text_input("Sub-AVA / district (optional)", value=str(defaults.get("subregion", "")))
    tier_options = ["Value/Core", "Core", "Estate", "Limited", "Reserve", "Flagship"]
    tier_default = str(defaults.get("product_tier", "Core") or "Core")
    tier_idx = tier_options.index(tier_default) if tier_default in tier_options else 1
    product_tier = c3.selectbox("Product tier", tier_options, index=tier_idx,
                                help="Tier is used to prevent Estate/Reserve/Flagship wines from overpowering a Core-tier recommendation.")
    analysis_mode = c4.selectbox("Analysis mode", ["Current market", "Historical backtest"], index=0,
                                 help="Historical backtest excludes comparable vintages later than the target vintage.")

    with st.expander("2. Add details that improve the recommendation", expanded=True):
        a, b, c, d = st.columns(4)
        critic_default = defaults.get("critic_score", np.nan)
        critic_score = a.number_input("Critic score (optional)", min_value=0.0, max_value=100.0,
                                      value=float(critic_default) if pd.notna(critic_default) else 0.0, step=1.0,
                                      help="Leave at 0 when no comparable critic score is available.")
        cases_default = defaults.get("cases_produced", np.nan)
        cases_produced = b.number_input("Cases produced (optional)", min_value=0,
                                        value=int(cases_default) if pd.notna(cases_default) else 0, step=50)
        cogs = c.number_input("COGS per 750 mL bottle", min_value=0.0, value=0.0, step=0.50, format="%.2f")
        price_default = defaults.get("price", np.nan)
        current_msrp = d.number_input("Current MSRP / known price (optional)", min_value=0.0,
                                      value=float(price_default) if pd.notna(price_default) else 0.0, step=1.0)

        a, b, c, d = st.columns(4)
        estate = a.checkbox("Estate", value=bool(defaults.get("estate", False)))
        single_vineyard = b.checkbox("Single vineyard", value=bool(defaults.get("single_vineyard", False)))
        previous_msrp = c.number_input("Prior-vintage MSRP (optional)", min_value=0.0, value=0.0, step=1.0)
        previous_vintage = d.number_input("Prior vintage", min_value=1990, max_value=2035, value=max(1990, vintage - 1), step=1)

        channel = st.selectbox("Primary sales model", ["DTC", "Mixed", "Wholesale"], index=0)
        if channel == "Mixed":
            dtc_share = st.slider("DTC share of unit sales", 0, 100, 60, 5) / 100
        elif channel == "DTC":
            dtc_share = 1.0
        else:
            dtc_share = 0.0
        wholesale_net_pct = st.slider("Wholesale net revenue as % of MSRP", 35, 65, 50, 1) / 100

    run = st.button("Generate Rudder Market Analysis", type="primary", use_container_width=True)

    if run:
        target = {
            "winery": winery,
            "wine": wine,
            "vintage": vintage,
            "varietal": graph_category,
            "graph_category": graph_category,
            "general_category": "Red" if graph_category not in {"Chardonnay", "Viognier", "Sauvignon Blanc", "White Blend"} else "White",
            "region": region,
            "subregion": subregion,
            "product_tier": product_tier,
            "critic_score": critic_score if critic_score > 0 else None,
            "cases_produced": cases_produced if cases_produced > 0 else None,
            "estate": estate,
            "single_vineyard": single_vineyard,
            "cogs": cogs if cogs > 0 else None,
            "channel": channel,
            "dtc_share": dtc_share,
            "wholesale_net_pct": wholesale_net_pct,
            "previous_msrp": previous_msrp if previous_msrp > 0 else None,
            "previous_vintage": previous_vintage if previous_msrp > 0 else None,
            "analysis_mode": analysis_mode,
        }
        try:
            result = analyze_wine(all_data, target, context=context)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        st.divider()
        st.subheader("Rudder pricing recommendation")
        scenario_cols = st.columns(3)
        for col, s in zip(scenario_cols, result["scenarios"]):
            with col:
                st.metric(s["strategy"], f"${s['msrp']:,.0f}")
                st.caption(s["positioning"])
                if np.isfinite(s["gross_margin_pct"]):
                    st.caption(f"Estimated blended gross margin: {s['gross_margin_pct']:.1%}")
                st.caption(f"Estimated blended net revenue/bottle: ${s['estimated_net_revenue_per_bottle']:,.2f}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Comparable-supported range", f"${result['market_range_low']:,.0f}–${result['market_range_high']:,.0f}")
        m2.metric("Model confidence", result["confidence_label"], f"{result['confidence_score']}/100")
        m3.metric("Comparable observations", len(result["comps"]))
        m4.metric("Public-context adjustment", f"{(result['context_factor']-1)*100:+.1f}%")

        if current_msrp > 0:
            market_price = result["scenarios"][1]["msrp"]
            delta = current_msrp - market_price
            if abs(delta) < 1:
                st.success("The entered current price is essentially aligned with the prototype market estimate.")
            elif delta > 0:
                st.info(f"Current price is ${delta:,.0f} above the prototype market-aligned estimate.")
            else:
                st.info(f"Current price is ${abs(delta):,.0f} below the prototype market-aligned estimate.")

        left, right = st.columns([1.2, 1])
        with left:
            st.markdown("#### Closest comparable wines")
            comp_view = result["comps"].copy()
            mx = max(comp_view["similarity_weight"].max(), 1e-9)
            comp_view["Similarity"] = (100 * comp_view["similarity_weight"] / mx).round(0).astype(int)
            comp_view["Vintage"] = comp_view["vintage"].round(0).astype("Int64")
            comp_view["Price"] = comp_view["price"].map(lambda x: f"${x:,.0f}")
            st.dataframe(
                comp_view[["winery", "wine", "Vintage", "Price", "product_tier", "comp_reason", "Similarity"]]
                .rename(columns={"winery": "Winery", "wine": "Wine", "product_tier": "Tier", "comp_reason": "Why included"}),
                use_container_width=True,
                hide_index=True,
            )
        with right:
            st.markdown("#### Comparable price landscape")
            plot_df = result["comps"].copy()
            plot_df["Vintage"] = plot_df["vintage"].fillna(vintage)
            fig = px.scatter(
                plot_df,
                x="Vintage",
                y="price",
                size="similarity_weight",
                hover_name="wine",
                hover_data={"winery": True, "product_tier": True, "comp_reason": True, "similarity_weight": ":.2f"},
                labels={"price": "Observed price ($)", "winery": "Winery", "product_tier": "Tier"},
            )
            fig.add_hline(y=result["scenarios"][1]["msrp"], line_dash="dash", annotation_text="Rudder market-aligned")
            fig.update_layout(height=410, margin=dict(l=10, r=10, t=15, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### What is moving the recommendation")
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**Upward support**")
            if result["upward_drivers"]:
                for item in result["upward_drivers"]:
                    st.write(f"• {item}")
            else:
                st.caption("No major wine-specific upward adjustments were supplied.")
        with d2:
            st.markdown("**Constraints / downward pressure**")
            if result["downward_drivers"]:
                for item in result["downward_drivers"]:
                    st.write(f"• {item}")
            else:
                st.caption("No major wine-specific downward adjustments were supplied.")

        if result["context_notes"]:
            st.markdown("**Public market context**")
            for item in result["context_notes"]:
                st.write(f"• {item}")

        st.markdown("#### Confidence breakdown")
        conf_df = pd.DataFrame([{"Component": k, "Assessment": v} for k, v in result["confidence_breakdown"].items()])
        st.dataframe(conf_df, use_container_width=True, hide_index=True)
        for item in result["confidence_notes"]:
            st.caption(f"Confidence note: {item}")

        export_rows = []
        for s in result["scenarios"]:
            export_rows.append({
                "Winery": winery, "Wine": wine, "Vintage": vintage, "Region": region,
                "Strategy": s["strategy"], "Recommended MSRP": s["msrp"],
                "Positioning": s["positioning"], "Confidence": result["confidence_label"],
                "Confidence Score": result["confidence_score"],
                "Comparable Count": len(result["comps"]),
                "Public Context Adjustment %": round((result["context_factor"] - 1) * 100, 2),
            })
        export_df = pd.DataFrame(export_rows)
        st.download_button(
            "Download recommendation CSV",
            export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"rudder_wine_pricing_{winery}_{vintage}.csv".replace(" ", "_"),
            mime="text/csv",
        )

elif page == "Data Hub (Admin)":
    st.subheader("Rudder Wine Data Hub")
    st.caption("Internal data-management layer. Customers do not need to build or maintain comparable sets themselves.")

    a, b, c, d = st.columns(4)
    a.metric("Pricing observations", len(all_data))
    b.metric("Wineries", all_data["winery"].nunique())
    c.metric("Market categories", all_data["graph_category"].replace("", np.nan).nunique())
    d.metric("Paso observations", int(all_data["region"].str.contains("Paso", case=False, na=False).sum()))

    st.markdown("### Screenshot Intake")
    st.caption("Upload screenshots you manually captured from a wine product/shop page. AI extracts visible facts, then Rudder applies our classification rules. Nothing is saved until you review and approve it.")

    if "vision_pasted_images" not in st.session_state:
        st.session_state.vision_pasted_images = []
    if "vision_last_paste_hash" not in st.session_state:
        st.session_state.vision_last_paste_hash = ""

    ss1, ss2 = st.columns([1.25, 1])
    with ss1:
        shot_files = st.file_uploader(
            "Wine product screenshots (1–4)",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="vision_shots",
            help="Use screenshots from one wine/product page at a time. Include price/spec sections when possible.",
        )

        st.caption("Or copy a screenshot to your clipboard and add it directly.")
        if paste_image_button is not None:
            pasted = paste_image_button(
                label="📋 Paste screenshot from clipboard",
                text_color="#ffffff",
                background_color="#285873",
                hover_background_color="#1f465d",
                key="vision_clipboard_paste",
                errors="raise",
            )
            if pasted.image_data is not None:
                buffer = io.BytesIO()
                pasted.image_data.save(buffer, format="PNG")
                pasted_bytes = buffer.getvalue()
                paste_hash = hashlib.sha256(pasted_bytes).hexdigest()
                existing_count = len(shot_files or []) + len(st.session_state.vision_pasted_images)
                if paste_hash != st.session_state.vision_last_paste_hash:
                    if existing_count >= 4:
                        st.warning("A maximum of four screenshots can be used for one wine. Clear one before pasting another.")
                    else:
                        st.session_state.vision_pasted_images.append({
                            "name": f"Clipboard screenshot {len(st.session_state.vision_pasted_images) + 1}",
                            "bytes": pasted_bytes,
                            "hash": paste_hash,
                        })
                        st.session_state.vision_last_paste_hash = paste_hash
        else:
            st.info("Clipboard paste is unavailable until the streamlit-paste-button dependency is installed. File upload still works normally.")

        if st.session_state.vision_pasted_images:
            with st.expander(f"Clipboard screenshots ({len(st.session_state.vision_pasted_images)})", expanded=True):
                preview_cols = st.columns(min(4, len(st.session_state.vision_pasted_images)))
                for idx, item in enumerate(st.session_state.vision_pasted_images):
                    with preview_cols[idx % len(preview_cols)]:
                        st.image(item["bytes"], caption=item["name"], use_container_width=True)
                if st.button("Clear clipboard screenshots", key="clear_vision_clipboard"):
                    st.session_state.vision_pasted_images = []
                    st.session_state.vision_last_paste_hash = ""
                    st.rerun()

        vision_source_url = st.text_input(
            "Source URL",
            key="vision_source_url",
            placeholder="https://winery.example/product/...",
            help="Stored for auditability; Rudder does not fetch this URL during screenshot extraction.",
        )
    with ss2:
        vision_source_kind = st.selectbox(
            "Source type",
            ["Official winery site", "Retailer / merchant", "Other public source"],
            key="vision_source_kind",
        )
        vision_source_name = st.text_input(
            "Source name override (optional)",
            key="vision_source_name",
            placeholder="Eberle Winery",
        )
        model_options = ["gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.6-sol"]
        default_model = get_default_model()
        model_idx = model_options.index(default_model) if default_model in model_options else 0
        vision_model = st.selectbox(
            "Vision model",
            model_options,
            index=model_idx,
            key="vision_model",
            help="Terra is the default balance of extraction quality and cost. Luna is cheaper; Sol is more capable but more expensive.",
        )

    combined_shots = list(shot_files or []) + [item["bytes"] for item in st.session_state.vision_pasted_images]
    too_many_shots = len(combined_shots) > 4
    if combined_shots:
        st.caption(f"{len(combined_shots)} screenshot(s) ready. Screenshot content is sent to the configured OpenAI API model only when you click Extract.")
    if too_many_shots:
        st.warning("Use no more than four screenshots for one wine. Remove an uploaded file or clear a clipboard screenshot before extracting.")

    extract_clicked = st.button(
        "Extract wine details with AI",
        type="primary",
        disabled=(not combined_shots) or too_many_shots,
        key="vision_extract_btn",
    )
    if extract_clicked:
        try:
            with st.spinner("Reading the screenshots and structuring the visible wine details..."):
                extracted = extract_wine_from_images(combined_shots, model=vision_model)
            st.session_state.vision_extraction = extracted
            st.session_state.vision_extraction_source_url = vision_source_url
            st.session_state.vision_extraction_source_kind = vision_source_kind
            st.session_state.vision_extraction_source_name = vision_source_name
            st.success("Extraction complete. Review every field below before adding it to the comp database.")
        except Exception as exc:
            st.error(f"Screenshot extraction failed: {exc}")

    extracted = st.session_state.get("vision_extraction")
    if extracted:
        proposed = build_comp_record(
            extracted,
            source_url=st.session_state.get("vision_extraction_source_url", ""),
            source_kind=st.session_state.get("vision_extraction_source_kind", "Official winery site"),
            source_name_override=st.session_state.get("vision_extraction_source_name", ""),
        )

        warnings = extracted.get("warnings") or []
        awards = extracted.get("competition_awards") or []
        if warnings:
            for warning in warnings:
                st.warning(f"Vision review note: {warning}")
        if extracted.get("estate_evidence") and not proposed.get("estate"):
            st.info("Estate wording was detected, but Rudder did not mark the finished wine as Estate because the evidence did not clearly designate the whole wine as estate-grown/estate-bottled or include Estate in the wine name.")

        with st.expander("Extraction evidence / non-model fields", expanded=False):
            st.write(f"**Overall vision confidence:** {extracted.get('overall_confidence', 'Moderate')}")
            st.write(f"**Estate evidence:** {extracted.get('estate_evidence') or 'Not shown'}")
            st.write(f"**Single-vineyard evidence:** {extracted.get('single_vineyard_evidence') or 'Not shown'}")
            st.write(f"**Tier evidence:** {extracted.get('tier_evidence') or 'Not shown'}")
            st.write(f"**Vineyard sources seen:** {', '.join(extracted.get('vineyard_sources') or []) or 'Not shown'}")
            st.write(f"**Competition awards (not stored as critic scores):** {', '.join(awards) or 'None shown'}")
            if extracted.get("club_price") is not None:
                st.write(f"**Club/member price detected:** ${float(extracted['club_price']):,.2f} — shown for reference, not used as the main comp price.")

        duplicates = duplicate_matches(all_data, proposed)
        if duplicates is not None and not duplicates.empty:
            st.warning(f"Possible duplicate: {len(duplicates)} existing observation(s) already match this winery + wine + vintage. Review them before adding another price observation.")
            dup_view = duplicates[["winery", "wine", "vintage", "price", "price_type", "source_name", "price_date"]].copy()
            st.dataframe(dup_view, use_container_width=True, hide_index=True)

        st.markdown("#### Review extracted comp")
        st.caption("AI-proposed values are editable. Blank/unknown values should remain blank rather than being guessed.")

        category_options = sorted(set(all_data["graph_category"].replace("", np.nan).dropna().tolist() + [
            "Cabernet Sauvignon", "Bordeaux Blend", "Rhône Blend", "Red Blend", "Pinot Noir", "Zinfandel",
            "Petite Sirah", "Syrah", "Grenache", "Mourvèdre", "Merlot", "Cabernet Franc", "Sangiovese",
            "Barbera", "Chardonnay", "Sauvignon Blanc", "Viognier", "White Blend", "Rosé", "Sparkling", "Other"
        ]))
        graph_default = proposed.get("graph_category") or "Other"
        if graph_default not in category_options:
            category_options.append(graph_default)
            category_options = sorted(set(category_options))

        with st.form("vision_review_form"):
            r1, r2, r3, r4 = st.columns(4)
            rv_winery = r1.text_input("Winery / producer", value=proposed.get("winery", ""), key="rv_winery")
            rv_wine = r2.text_input("Wine / label", value=proposed.get("wine", ""), key="rv_wine")
            rv_vintage = r3.number_input("Vintage", min_value=1900, max_value=2100,
                                         value=int(proposed.get("vintage") or pd.Timestamp.today().year), step=1, key="rv_vintage")
            rv_price = r4.number_input("Price", min_value=0.0, value=float(proposed.get("price") or 0.0), step=1.0, format="%.2f", key="rv_price")

            r1, r2, r3, r4 = st.columns(4)
            rv_varietal = r1.text_input("Varietal / blend", value=proposed.get("varietal", ""), key="rv_varietal")
            rv_graph = r2.selectbox("Market category", category_options,
                                    index=category_options.index(graph_default), key="rv_graph")
            general_options = ["Red", "White", "Rosé", "Sparkling", "Dessert/Other"]
            gen_default = proposed.get("general_category") if proposed.get("general_category") in general_options else "Red"
            rv_general = r3.selectbox("General category", general_options, index=general_options.index(gen_default), key="rv_general")
            rv_tier_default = proposed.get("product_tier") if proposed.get("product_tier") in TIERS else "Core"
            rv_tier = r4.selectbox("Product tier", TIERS, index=TIERS.index(rv_tier_default), key="rv_tier")

            r1, r2, r3, r4 = st.columns(4)
            rv_region = r1.text_input("Region / AVA", value=proposed.get("region", ""), key="rv_region")
            rv_subregion = r2.text_input("Sub-AVA / district", value=proposed.get("subregion", ""), key="rv_subregion")
            price_type_default = proposed.get("price_type") if proposed.get("price_type") in PRICE_TYPES else "Observed retail"
            rv_price_type = r3.selectbox("Price type", PRICE_TYPES, index=PRICE_TYPES.index(price_type_default), key="rv_price_type")
            conf_default = proposed.get("data_confidence") if proposed.get("data_confidence") in CONFIDENCE_LEVELS else "Moderate"
            rv_conf = r4.selectbox("Data confidence", CONFIDENCE_LEVELS, index=CONFIDENCE_LEVELS.index(conf_default), key="rv_conf")

            r1, r2, r3, r4 = st.columns(4)
            rv_critic = r1.text_input("Critic (optional)", value=proposed.get("critic", ""), key="rv_critic")
            rv_score = r2.number_input("Critic score (optional)", min_value=0.0, max_value=100.0,
                                       value=float(proposed.get("critic_score") or 0.0), step=1.0, key="rv_score")
            rv_cases = r3.number_input("Cases produced (optional)", min_value=0,
                                       value=int(proposed.get("cases_produced") or 0), step=50, key="rv_cases")
            rv_abv = r4.number_input("Alcohol % (optional)", min_value=0.0, max_value=30.0,
                                     value=float(proposed.get("alcohol_pct") or 0.0), step=0.1, format="%.1f", key="rv_abv")

            r1, r2, r3, r4 = st.columns(4)
            rv_estate = r1.checkbox("Estate", value=bool(proposed.get("estate", False)), key="rv_estate")
            rv_single = r2.checkbox("Single vineyard", value=bool(proposed.get("single_vineyard", False)), key="rv_single")
            rv_source_name = r3.text_input("Source name", value=proposed.get("source_name", ""), key="rv_source_name")
            rv_price_date = r4.text_input("Price observed date", value=proposed.get("price_date", pd.Timestamp.today().date().isoformat()), key="rv_price_date")
            rv_source_url = st.text_input("Source URL", value=proposed.get("source_url", ""), key="rv_source_url")

            approved = st.form_submit_button("Approve & add comparable to this session", type="primary")

        if approved:
            required_missing = []
            if not rv_winery.strip(): required_missing.append("winery")
            if not rv_wine.strip(): required_missing.append("wine")
            if not rv_region.strip(): required_missing.append("region")
            if rv_price <= 0: required_missing.append("positive price")
            if required_missing:
                st.error("Cannot add comp; missing: " + ", ".join(required_missing))
            else:
                approved_record = pd.DataFrame([{
                    "winery": rv_winery.strip(),
                    "wine": rv_wine.strip(),
                    "vintage": rv_vintage,
                    "varietal": rv_varietal.strip(),
                    "graph_category": rv_graph,
                    "general_category": rv_general,
                    "region": rv_region.strip(),
                    "subregion": rv_subregion.strip(),
                    "price": rv_price,
                    "price_type": rv_price_type,
                    "critic": rv_critic.strip(),
                    "critic_score": rv_score if rv_score > 0 else np.nan,
                    "cases_produced": rv_cases if rv_cases > 0 else np.nan,
                    "alcohol_pct": rv_abv if rv_abv > 0 else np.nan,
                    "estate": rv_estate,
                    "single_vineyard": rv_single,
                    "product_tier": rv_tier,
                    "source_name": rv_source_name.strip(),
                    "source_url": rv_source_url.strip(),
                    "price_date": rv_price_date.strip(),
                    "data_confidence": rv_conf,
                }])
                current = st.session_state.uploaded_comps
                combined = pd.concat([current, approved_record], ignore_index=True) if current is not None else approved_record
                st.session_state.uploaded_comps = normalize_comp_data(combined)
                st.session_state.vision_extraction = None
                st.success("Comparable approved and added to this session. Use Download merged comp database below to persist the updated file in GitHub.")

    st.markdown("### Comp database")
    source_counts = all_data.groupby(["source_name", "data_confidence"], dropna=False).size().reset_index(name="Observations")
    st.dataframe(source_counts.rename(columns={"source_name": "Source", "data_confidence": "Confidence"}), use_container_width=True, hide_index=True)

    st.markdown("#### Import a newer Rudder pricing workbook")
    wb_upload = st.file_uploader("Paso pricing workbook", type=["xlsx", "xls"], key="rudder_wb")
    if wb_upload is not None:
        try:
            imported = load_rudder_pricing_workbook(wb_upload)
            st.success(f"Normalized {len(imported)} priced wine observations from the workbook's Data sheet.")
            st.dataframe(imported.head(20), use_container_width=True, hide_index=True)
            if st.button("Use this workbook for this session"):
                st.session_state.uploaded_comps = imported
                st.rerun()
        except Exception as exc:
            st.error(f"Workbook import failed: {exc}")

    st.markdown("#### Add a manually researched comparable")
    with st.form("manual_comp"):
        x1, x2, x3, x4 = st.columns(4)
        m_winery = x1.text_input("Winery")
        m_wine = x2.text_input("Wine")
        m_vintage = x3.number_input("Vintage", min_value=1990, max_value=2035, value=2024)
        m_price = x4.number_input("Price", min_value=0.0, value=0.0, step=1.0)
        x1, x2, x3, x4 = st.columns(4)
        m_varietal = x1.text_input("Varietal / blend")
        m_category = x2.text_input("Market category", value="Cabernet Sauvignon")
        m_region = x3.text_input("AVA / region", value="Paso Robles")
        m_tier = x4.selectbox("Tier", ["Value/Core", "Core", "Estate", "Limited", "Reserve", "Flagship"], index=1)
        m_source = st.text_input("Source URL (recommended)")
        m_price_type = st.selectbox("Price type", ["Winery MSRP", "Winery retail", "Observed retail", "Historical listed price"])
        submitted = st.form_submit_button("Add comparable to this session")
    if submitted:
        if not m_winery or not m_wine or m_price <= 0:
            st.error("Winery, wine and a positive price are required.")
        else:
            general = "White" if any(k in m_category.lower() for k in ["chardonnay", "viognier", "sauvignon blanc", "white"]) else "Red"
            new = pd.DataFrame([{
                "winery": m_winery, "wine": m_wine, "vintage": m_vintage, "varietal": m_varietal,
                "graph_category": m_category, "general_category": general, "region": m_region, "subregion": "",
                "price": m_price, "price_type": m_price_type, "critic": "", "critic_score": np.nan,
                "cases_produced": np.nan, "alcohol_pct": np.nan, "estate": m_tier == "Estate",
                "single_vineyard": False, "product_tier": m_tier, "source_name": "Manual Rudder research",
                "source_url": m_source, "price_date": pd.Timestamp.today().date().isoformat(), "data_confidence": "Moderate",
            }])
            current = st.session_state.uploaded_comps
            st.session_state.uploaded_comps = normalize_comp_data(pd.concat([current, new], ignore_index=True) if current is not None else new)
            st.success("Comparable added for this session. Download the merged database below if you want to persist it in GitHub.")

    merged_export = merge_data(seed, st.session_state.uploaded_comps)
    st.download_button("Download merged comp database", merged_export.to_csv(index=False).encode("utf-8"),
                       file_name="wine_comps_updated.csv", mime="text/csv")

    st.divider()
    st.markdown("### Public market context")
    st.caption("These sources are government/open-data feeds, not retailer or winery scrapers. v0.2 gives them only a small capped influence on bottle pricing.")
    context_view = load_public_context()
    st.dataframe(context_view, use_container_width=True, hide_index=True)
    if st.button("Refresh public data now", type="secondary"):
        with st.spinner("Refreshing BLS / TTB / USDA public sources..."):
            statuses = refresh_all_public_data()
        st.dataframe(pd.DataFrame(statuses), use_container_width=True, hide_index=True)
        st.info("On Streamlit Community Cloud, button-triggered files are temporary. The included GitHub Action is the persistent background-refresh path.")

    st.markdown("#### Public-data roadmap")
    roadmap = pd.DataFrame([
        ["BLS Wine at Home CPI", "Live connector", "Active model context", "No key"],
        ["TTB wine monthly/yearly open data", "Live download", "Raw cache + future market features", "No key"],
        ["TTB wine producer permit list", "Live download", "Regional producer context", "No key"],
        ["USDA/NASS CA Grape Crush", "Live download", "Supply / grape economics", "No key"],
        ["NOAA vintage climate", "Prepared next", "Vintage weather adjustment", "Free token"],
        ["Bottle-level current pricing", "Rudder workbook + manual additions", "Core comparable layer", "No scraping required"],
    ], columns=["Source", "Status", "Use", "Credential"])
    st.dataframe(roadmap, use_container_width=True, hide_index=True)

    st.markdown("### Workbook reference context")
    st.caption("The supplied workbook also contains Paso visitor/tasting-fee reference data. v0.2 shows it here but does not use it in pricing until provenance is verified.")
    visitor = load_reference_table(VISITOR_PATH)
    fees = load_reference_table(FEES_PATH)
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Monthly tasting-room paying visitors**")
        st.dataframe(visitor, use_container_width=True, hide_index=True)
    with r2:
        st.markdown("**Average tasting-room fees**")
        st.dataframe(fees, use_container_width=True, hide_index=True)

else:
    st.subheader("Methodology")
    st.markdown(
        """
### v0.3 approach

Rudder estimates a market-supported bottle-price range from a weighted comparable set, then applies deliberately modest wine-specific and public-market adjustments.

**Comparable hierarchy**

1. Same label, other vintages
2. Same winery and same product tier
3. Same category and same product tier
4. Same category but adjacent tier
5. Adjacent-category fallback only when necessary

**Historical backtesting** excludes later vintages so the model cannot use future information to "predict" an older release.

**Public market context** is intentionally light-touch and capped at ±4% in v0.2. The current seed uses BLS Wine at Home CPI and California red-wine grape-crush conditions; TTB/USDA raw feeds are collected for expansion, and NOAA vintage-weather enrichment is the next public-data connector.

The model is a market-positioning aid, not a guarantee of demand or sell-through. Winery-specific sales history will be needed before Rudder should make quantitative demand forecasts.

**Screenshot Intake** uses the OpenAI Responses API on screenshots explicitly uploaded by a Rudder administrator. The AI extracts visible facts only; Rudder applies deterministic classification rules; a human must review/edit the proposed row before it is added to the session comp database.
        """
    )
