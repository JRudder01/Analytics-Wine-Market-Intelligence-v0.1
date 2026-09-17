from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from data_loader import load_seed, load_upload, merge_data, TEMPLATE_PATH
from pricing_engine import analyze_wine

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

header_left, header_right = st.columns([2.4, 7.6])
with header_left:
    st.image(str(ASSETS / "rudder_wordmark.png"), use_container_width=True)
with header_right:
    st.title("Wine Market Intelligence")
    st.markdown('<div class="ra-subtitle">Pricing & market-positioning prototype · v0.1</div>', unsafe_allow_html=True)

seed = load_seed()
if "uploaded_comps" not in st.session_state:
    st.session_state.uploaded_comps = None
all_data = merge_data(seed, st.session_state.uploaded_comps)

page = st.sidebar.radio("Workspace", ["Pricing Analysis", "Comparable Database", "Methodology"])
st.sidebar.caption(f"{len(all_data):,} pricing observations loaded")

if page == "Pricing Analysis":
    st.subheader("1. Identify the wine")
    st.caption("Load a known wine from the starter database or enter a new/unreleased wine manually.")

    known = st.toggle("Start from a known wine", value=True)
    defaults = {}
    if known:
        known_df = all_data.sort_values(["winery", "wine", "vintage"], ascending=[True, True, False]).copy()
        known_df["label"] = known_df.apply(lambda r: f"{r['winery']} — {int(r['vintage']) if pd.notna(r['vintage']) else 'NV'} {r['wine']}", axis=1)
        default_idx = 0
        eberle_mask = known_df["label"].str.contains("Eberle — 2023 Vineyard Selection Cabernet", case=False, na=False)
        if eberle_mask.any():
            default_idx = int(np.flatnonzero(eberle_mask.to_numpy())[0])
        selection = st.selectbox("Known wine", known_df["label"].tolist(), index=default_idx)
        row = known_df.loc[known_df["label"].eq(selection)].iloc[0]
        defaults = row.to_dict()
        st.info("The known wine's price is excluded from its own comparable analysis to reduce target-price leakage.")

    c1, c2, c3, c4 = st.columns(4)
    winery = c1.text_input("Winery / producer", value=str(defaults.get("winery", "")))
    wine = c2.text_input("Wine / label", value=str(defaults.get("wine", "")))
    vintage_default = int(defaults.get("vintage", 2024)) if pd.notna(defaults.get("vintage", np.nan)) else 2024
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
    product_tier = c3.selectbox("Product tier", tier_options, index=tier_idx)
    channel = c4.selectbox("Primary sales model", ["DTC", "Mixed", "Wholesale"], index=0)

    with st.expander("2. Add details that improve the recommendation", expanded=True):
        a, b, c, d = st.columns(4)
        critic_default = defaults.get("critic_score", np.nan)
        critic_score = a.number_input("Critic score (optional)", min_value=0.0, max_value=100.0,
                                      value=float(critic_default) if pd.notna(critic_default) else 0.0, step=1.0,
                                      help="Leave at 0 when no comparable critic score is available.")
        cases_default = defaults.get("cases_produced", np.nan)
        cases_produced = b.number_input("Cases produced (optional)", min_value=0, value=int(cases_default) if pd.notna(cases_default) else 0, step=50)
        cogs = c.number_input("COGS per 750 mL bottle", min_value=0.0, value=0.0, step=0.50, format="%.2f")
        price_default = defaults.get("price", np.nan)
        current_msrp = d.number_input("Current MSRP (optional)", min_value=0.0, value=float(price_default) if pd.notna(price_default) else 0.0, step=1.0)

        a, b, c, d = st.columns(4)
        estate = a.checkbox("Estate", value=bool(defaults.get("estate", False)))
        single_vineyard = b.checkbox("Single vineyard", value=bool(defaults.get("single_vineyard", False)))
        previous_msrp = c.number_input("Prior-vintage MSRP (optional)", min_value=0.0, value=0.0, step=1.0)
        previous_vintage = d.number_input("Prior vintage", min_value=1990, max_value=2035, value=max(1990, vintage - 1), step=1)

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
        }
        try:
            result = analyze_wine(all_data, target)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        st.divider()
        st.subheader("Rudder pricing recommendation")
        scenario_cols = st.columns(3)
        for col, s in zip(scenario_cols, result["scenarios"]):
            with col:
                st.metric(s["strategy"], f"${s['msrp']:,.0f}")
                st.caption(f"Demand / inventory risk: {s['demand_risk']}")
                if np.isfinite(s["gross_margin_pct"]):
                    st.caption(f"Estimated blended gross margin: {s['gross_margin_pct']:.1%}")
                st.caption(f"Estimated blended net revenue/bottle: ${s['estimated_net_revenue_per_bottle']:,.2f}")

        m1, m2, m3 = st.columns(3)
        m1.metric("Comparable-supported range", f"${result['market_range_low']:,.0f}–${result['market_range_high']:,.0f}")
        m2.metric("Model confidence", result["confidence_label"], f"{result['confidence_score']}/100")
        m3.metric("Comparable observations", len(result["comps"]))

        if current_msrp > 0:
            market_price = result["scenarios"][1]["msrp"]
            delta = current_msrp - market_price
            if abs(delta) < 1:
                st.success("The entered current MSRP is essentially aligned with the prototype market estimate.")
            elif delta > 0:
                st.info(f"Current MSRP is ${delta:,.0f} above the prototype market-aligned estimate.")
            else:
                st.info(f"Current MSRP is ${abs(delta):,.0f} below the prototype market-aligned estimate.")

        left, right = st.columns([1.15, 1])
        with left:
            st.markdown("#### Closest comparable wines")
            comp_view = result["comps"].copy()
            comp_view["Similarity"] = (100 * comp_view["similarity_weight"] / comp_view["similarity_weight"].max()).round(0).astype(int)
            comp_view["Vintage"] = comp_view["vintage"].round(0).astype("Int64")
            comp_view["Price"] = comp_view["price"].map(lambda x: f"${x:,.0f}")
            st.dataframe(
                comp_view[["winery", "wine", "Vintage", "Price", "graph_category", "product_tier", "Similarity"]]
                .rename(columns={"winery": "Winery", "wine": "Wine", "graph_category": "Category", "product_tier": "Tier"}),
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
                hover_data={"winery": True, "graph_category": True, "similarity_weight": ":.2f"},
                labels={"price": "Observed price ($)", "winery": "Winery", "graph_category": "Category"},
            )
            fig.add_hline(y=result["scenarios"][1]["msrp"], line_dash="dash", annotation_text="Rudder market-aligned")
            fig.update_layout(height=390, margin=dict(l=10, r=10, t=15, b=10))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### What is moving the recommendation")
        for item in result["drivers"] or ["The first build is being driven primarily by the comparable-wine distribution."]:
            st.write(f"• {item}")
        for item in result["confidence_notes"]:
            st.write(f"• Confidence note: {item}")

        export_rows = []
        for s in result["scenarios"]:
            export_rows.append({
                "Winery": winery, "Wine": wine, "Vintage": vintage, "Region": region,
                "Strategy": s["strategy"], "Recommended MSRP": s["msrp"],
                "Demand Risk": s["demand_risk"], "Confidence": result["confidence_label"],
                "Confidence Score": result["confidence_score"],
                "Comparable Count": len(result["comps"]),
            })
        export_df = pd.DataFrame(export_rows)
        st.download_button(
            "Download recommendation CSV",
            export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"rudder_wine_pricing_{winery}_{vintage}.csv".replace(" ", "_"),
            mime="text/csv",
        )

        st.warning("Prototype v0.1: recommendations are decision-support estimates, not guaranteed market-clearing prices. Demand forecasting is intentionally not yet presented without winery-specific sales history.")

elif page == "Comparable Database":
    st.subheader("Comparable-wine database")
    st.write("The prototype ships with Cabernet/Bordeaux observations extracted from the supplied Rudder Access database plus a small set of publicly verified Eberle records.")

    upload = st.file_uploader("Add comparable data for this session", type=["csv", "xlsx", "xls"])
    if upload is not None:
        try:
            st.session_state.uploaded_comps = load_upload(upload)
            st.success(f"Loaded {len(st.session_state.uploaded_comps):,} additional rows. Return to Pricing Analysis to use them.")
        except Exception as exc:
            st.error(f"Could not load file: {exc}")

    st.download_button(
        "Download comp import template",
        TEMPLATE_PATH.read_bytes(),
        file_name="rudder_wine_comp_import_template.csv",
        mime="text/csv",
    )

    show = merge_data(seed, st.session_state.uploaded_comps)
    st.dataframe(show, use_container_width=True, hide_index=True)

    if st.button("Clear uploaded session data"):
        st.session_state.uploaded_comps = None
        st.rerun()

elif page == "Methodology":
    st.subheader("Prototype methodology")
    st.markdown(
        """
The first build deliberately uses a transparent comparable-market framework rather than presenting a black-box forecast.

**Comparable selection** considers wine category, region, vintage proximity, producer history, tier, critic-score proximity when available, and data-source confidence. The exact target wine/vintage is excluded from its own analysis.

**Positioning adjustments** currently incorporate product tier, critic score, estate/single-vineyard designations, production scarcity, and an optional prior-vintage MSRP anchor. These are prototype coefficients and are meant to be calibrated as the Rudder database expands.

**Three strategies** are returned: a lower/volume-oriented position, a market-aligned position, and a premium/higher-risk position. COGS and channel mix are used to show approximate per-bottle economics, but v0.1 does not claim unit-sales forecasts without winery sales history.

**Next planned data layers** include broader Paso Robles/Napa comps, structured critic data, public winery tech-sheet enrichment, CDFA grape-market inputs, NOAA vintage conditions, and later winery-specific price-elasticity modeling.
        """
    )
    st.caption("Rudder Analytics · Wine Market Intelligence · Prototype v0.1")
