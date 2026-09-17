from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

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
    st.markdown('<div class="ra-subtitle">Pricing, comparable-market & public-context prototype · v0.2</div>', unsafe_allow_html=True)

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
    st.caption("Start with a known comparable or enter a new/unreleased wine. v0.2 uses the expanded Paso workbook plus public market context.")

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
### v0.2 approach

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
        """
    )
