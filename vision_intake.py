from __future__ import annotations

import base64
import io
import json
import os
import re
from datetime import date
from typing import Any

from PIL import Image

TIERS = ["Value/Core", "Core", "Estate", "Limited", "Reserve", "Flagship"]
PRICE_TYPES = [
    "Winery MSRP",
    "Winery retail",
    "Observed retail",
    "Historical listed price",
    "Wine club/member price",
    "Distributor/wholesale",
]
CONFIDENCE_LEVELS = ["High", "Moderate", "Low"]

EXTRACTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "winery": {"type": ["string", "null"]},
        "wine": {"type": ["string", "null"]},
        "vintage": {"type": ["integer", "null"]},
        "varietal_text": {"type": ["string", "null"]},
        "appellation": {"type": ["string", "null"]},
        "subregion": {"type": ["string", "null"]},
        "retail_price": {"type": ["number", "null"]},
        "club_price": {"type": ["number", "null"]},
        "explicit_price_label": {"type": ["string", "null"]},
        "alcohol_pct": {"type": ["number", "null"]},
        "cases_produced": {"type": ["integer", "null"]},
        "critic_name": {"type": ["string", "null"]},
        "critic_score": {"type": ["number", "null"]},
        "competition_awards": {
            "type": "array",
            "items": {"type": "string"},
        },
        "vineyard_sources": {
            "type": "array",
            "items": {"type": "string"},
        },
        "estate_evidence": {"type": ["string", "null"]},
        "single_vineyard_evidence": {"type": ["string", "null"]},
        "tier_evidence": {"type": ["string", "null"]},
        "source_name_visible": {"type": ["string", "null"]},
        "overall_confidence": {
            "type": "string",
            "enum": ["High", "Moderate", "Low"],
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "winery", "wine", "vintage", "varietal_text", "appellation", "subregion",
        "retail_price", "club_price", "explicit_price_label", "alcohol_pct",
        "cases_produced", "critic_name", "critic_score", "competition_awards",
        "vineyard_sources", "estate_evidence", "single_vineyard_evidence",
        "tier_evidence", "source_name_visible", "overall_confidence", "warnings",
    ],
}

EXTRACTION_INSTRUCTIONS = """
You are extracting factual wine-product data from screenshots supplied by a Rudder Analytics administrator.

Rules:
- Extract ONLY details visibly supported by the supplied screenshot(s). Never fill a missing fact from general knowledge.
- Use null when a field is not shown or cannot be read reliably.
- retail_price is the ordinary public bottle price shown for purchase. club_price is a separately labeled wine-club/member price.
- explicit_price_label should contain only a visible label such as MSRP, SRP, Suggested Retail, List Price, Retail, or null. Do not invent a label.
- critic_name/critic_score are for named editorial wine critics/publications. Do NOT put wine-competition scores there. Put competition medals/scores in competition_awards.
- vineyard_sources should contain named vineyard/source locations explicitly stated for the finished wine or its components.
- estate_evidence is ONLY for evidence that the FINISHED WINE is estate-designated or that all fruit for the finished wine is explicitly estate-grown/estate-sourced. Do NOT treat a component vineyard/source such as "Picpoul is from Eberle Estate", a winery name containing Estate, or a named "Estate Vineyard" by itself as proof that the finished wine is Estate. In those cases use null unless the wine title/designation itself says Estate or the page explicitly says the finished wine is estate-grown/estate-bottled/100% estate.
- single_vineyard_evidence should contain visible wording that clearly ties the finished wine to one named vineyard. If multiple vineyard sources are shown, note that in warnings and use null unless the page explicitly calls the finished wine single-vineyard.
- tier_evidence should contain visible words that describe the FINISHED WINE's market tier, such as Flagship, Reserve, Estate, Limited Release, Cellar Club, icon, benchmark, etc. Do not use "Estate" from a component vineyard/source as tier evidence. Otherwise null.
- Keep names faithful to the page. Do not rewrite branding.
- A screenshot can contain several sections of one product page; combine them into one product record.
- If screenshots appear to show more than one different wine, lower confidence and warn the reviewer.
""".strip()


def _get_api_key() -> str | None:
    """Find an OpenAI key without importing Streamlit at module import time."""
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:
        return None


def get_default_model() -> str:
    model = os.getenv("OPENAI_VISION_MODEL")
    if model:
        return model
    try:
        import streamlit as st
        return st.secrets.get("OPENAI_VISION_MODEL", "gpt-5.6-terra")
    except Exception:
        return "gpt-5.6-terra"


def _image_to_data_url(image_input, max_dimension: int = 2600) -> str:
    """Resize screenshots while retaining enough text detail for vision.

    Supports Streamlit UploadedFile objects, raw bytes, file-like objects, and
    PIL images (used by the clipboard-paste component).
    """
    if isinstance(image_input, Image.Image):
        image = image_input.copy()
    else:
        if isinstance(image_input, (bytes, bytearray)):
            raw = bytes(image_input)
        elif hasattr(image_input, "getvalue"):
            raw = image_input.getvalue()
        elif hasattr(image_input, "read"):
            raw = image_input.read()
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input).__name__}")
        image = Image.open(io.BytesIO(raw))
        image.load()
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGB")

    width, height = image.size
    scale = min(1.0, max_dimension / max(width, height))
    if scale < 1.0:
        image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))))

    # JPEG is substantially smaller for browser screenshots; preserve quality for readable text.
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        image = background
    else:
        image = image.convert("RGB")

    out = io.BytesIO()
    image.save(out, format="JPEG", quality=92, optimize=True)
    encoded = base64.b64encode(out.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def extract_wine_from_images(uploaded_files, model: str | None = None) -> dict[str, Any]:
    """Use the OpenAI Responses API to extract literal facts from 1-4 screenshots."""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to Streamlit Secrets or the local environment before using Screenshot Intake."
        )
    if not uploaded_files:
        raise ValueError("Upload at least one screenshot.")
    if len(uploaded_files) > 4:
        raise ValueError("Use at most four screenshots for one wine at a time.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    content = [{
        "type": "input_text",
        "text": "Extract the wine-product facts from these screenshots. Follow the extraction rules exactly.",
    }]
    for uploaded in uploaded_files:
        content.append({
            "type": "input_image",
            "image_url": _image_to_data_url(uploaded),
            "detail": "high",
        })

    response = client.responses.create(
        model=model or get_default_model(),
        store=False,
        instructions=EXTRACTION_INSTRUCTIONS,
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "rudder_wine_screenshot_extraction",
                "description": "Visible facts extracted from screenshots of one wine product page.",
                "schema": EXTRACTION_SCHEMA,
                "strict": True,
            },
            "verbosity": "low",
        },
    )
    if not getattr(response, "output_text", None):
        raise RuntimeError("The vision model returned no structured output.")
    return json.loads(response.output_text)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def infer_graph_category(varietal_text: str, wine_name: str = "") -> str:
    text = f"{varietal_text} {wine_name}".lower()
    # Specific varietals first.
    singles = [
        ("cabernet sauvignon", "Cabernet Sauvignon"),
        ("cabernet franc", "Cabernet Franc"),
        ("pinot noir", "Pinot Noir"),
        ("petite sirah", "Petite Sirah"),
        ("zinfandel", "Zinfandel"),
        ("sangiovese", "Sangiovese"),
        ("barbera", "Barbera"),
        ("chardonnay", "Chardonnay"),
        ("sauvignon blanc", "Sauvignon Blanc"),
        ("viognier", "Viognier"),
        ("syrah", "Syrah"),
        ("grenache", "Grenache"),
        ("mourv", "Mourvèdre"),
        ("merlot", "Merlot"),
    ]

    # Blend detection based on several named components.
    bordeaux_terms = ["cabernet sauvignon", "cabernet franc", "merlot", "petit verdot", "malbec"]
    rhone_red_terms = ["syrah", "grenache", "mourv", "counoise", "petite sirah"]
    rhone_white_terms = ["grenache blanc", "roussanne", "marsanne", "picpoul", "viognier", "clairette"]
    bdx_count = sum(term in text for term in bordeaux_terms)
    rr_count = sum(term in text for term in rhone_red_terms)
    rw_count = sum(term in text for term in rhone_white_terms)
    has_pct_or_commas = "%" in text or "," in varietal_text

    if bdx_count >= 2 and has_pct_or_commas:
        return "Bordeaux Blend"
    if rw_count >= 2 and has_pct_or_commas:
        return "White Blend"
    if rr_count >= 2 and has_pct_or_commas:
        return "Rhône Blend"

    # If explicitly described as a blend, prefer broad category.
    if "white blend" in text or ("blend" in text and any(t in text for t in rhone_white_terms)):
        return "White Blend"
    if "bordeaux" in text:
        return "Bordeaux Blend"
    if "rhône" in text or "rhone" in text:
        return "Rhône Blend"
    if "red blend" in text or "proprietary red" in text:
        return "Red Blend"

    for token, label in singles:
        if token in text:
            return label
    return "Other"


def infer_general_category(graph_category: str, varietal_text: str = "", wine_name: str = "") -> str:
    text = f"{graph_category} {varietal_text} {wine_name}".lower()
    if "rosé" in text or "rose" in text:
        return "Rosé"
    if "sparkling" in text or "brut" in text:
        return "Sparkling"
    white_terms = ["white", "chardonnay", "sauvignon blanc", "viognier", "grenache blanc", "picpoul", "roussanne", "marsanne"]
    if any(t in text for t in white_terms):
        return "White"
    return "Red"


def infer_estate(wine_name: str, estate_evidence: str | None) -> bool:
    """Classify Estate only from finished-wine evidence, not component sources.

    Strongest rule: an explicit Estate designation in the wine/label name.
    Otherwise, require wording that clearly applies estate status to the whole wine.
    A bare vineyard/source phrase such as "Eberle Estate" or "Estate Vineyard"
    is intentionally insufficient on its own.
    """
    name = _text(wine_name).lower()
    evidence = _text(estate_evidence).lower()

    if re.search(r"\bestate\b", name):
        return True
    if not evidence:
        return False

    whole_wine_patterns = [
        r"\bestate[- ]grown\b",
        r"\bestate[- ]bottled\b",
        r"\bestate wine\b",
        r"\bestate designation\b",
        r"\b100%[^.]{0,40}\bestate\b",
        r"\ball (?:fruit|grapes)[^.]{0,50}\bestate\b",
        r"\b(?:entirely|exclusively)[^.]{0,50}\bestate\b",
        r"\bfrom (?:our|the) estate vineyard(?:s)?\b",
        r"\bsourced (?:entirely|exclusively) from[^.]{0,50}\bestate\b",
    ]
    return any(re.search(pattern, evidence) for pattern in whole_wine_patterns)


def infer_product_tier(wine_name: str, tier_evidence: str | None, estate_evidence: str | None) -> str:
    text = f"{wine_name} {_text(tier_evidence)}".lower()
    if any(t in text for t in ["flagship", "icon wine", "iconic", "benchmark", "top wine"]):
        return "Flagship"
    if "reserve" in text:
        return "Reserve"
    if infer_estate(wine_name, estate_evidence):
        return "Estate"
    if any(t in text for t in ["limited", "cellar club", "small production", "small-production", "special release"]):
        return "Limited"
    if any(t in text for t in ["value", "entry level", "entry-level"]):
        return "Value/Core"
    return "Core"


def infer_single_vineyard(extraction: dict[str, Any]) -> bool:
    evidence = _text(extraction.get("single_vineyard_evidence")).lower()
    sources = [str(x).strip() for x in (extraction.get("vineyard_sources") or []) if str(x).strip()]
    if len({s.lower() for s in sources}) > 1:
        return False
    if evidence:
        return True
    # One named source alone is not enough unless wording clearly ties the finished wine to it.
    return False


def infer_price_type(extraction: dict[str, Any], source_kind: str) -> str:
    label = _text(extraction.get("explicit_price_label")).lower()
    if source_kind == "Retailer / merchant":
        return "Observed retail"
    if source_kind == "Official winery site":
        if any(t in label for t in ["msrp", "srp", "suggested retail", "list price"]):
            return "Winery MSRP"
        return "Winery retail"
    return "Observed retail"


def build_comp_record(
    extraction: dict[str, Any],
    source_url: str = "",
    source_kind: str = "Official winery site",
    source_name_override: str = "",
) -> dict[str, Any]:
    winery = _text(extraction.get("winery"))
    wine = _text(extraction.get("wine"))
    varietal = _text(extraction.get("varietal_text"))
    graph = infer_graph_category(varietal, wine)
    general = infer_general_category(graph, varietal, wine)
    price_type = infer_price_type(extraction, source_kind)
    source_name = source_name_override.strip() or _text(extraction.get("source_name_visible"))
    if not source_name:
        source_name = winery if source_kind == "Official winery site" else source_kind

    return {
        "winery": winery,
        "wine": wine,
        "vintage": extraction.get("vintage"),
        "varietal": varietal,
        "graph_category": graph,
        "general_category": general,
        "region": _text(extraction.get("appellation")),
        "subregion": _text(extraction.get("subregion")),
        "price": extraction.get("retail_price"),
        "price_type": price_type,
        "critic": _text(extraction.get("critic_name")),
        "critic_score": extraction.get("critic_score"),
        "cases_produced": extraction.get("cases_produced"),
        "alcohol_pct": extraction.get("alcohol_pct"),
        "estate": infer_estate(wine, extraction.get("estate_evidence")),
        "single_vineyard": infer_single_vineyard(extraction),
        "product_tier": infer_product_tier(wine, extraction.get("tier_evidence"), extraction.get("estate_evidence")),
        "source_name": source_name,
        "source_url": source_url.strip(),
        "price_date": date.today().isoformat(),
        "data_confidence": extraction.get("overall_confidence") or "Moderate",
    }


def duplicate_matches(all_data, record: dict[str, Any]):
    """Return same winery + label + vintage rows for a reviewer warning."""
    if all_data is None or all_data.empty:
        return all_data.iloc[0:0] if all_data is not None else None
    winery = _text(record.get("winery")).casefold()
    wine = _text(record.get("wine")).casefold()
    vintage = record.get("vintage")
    mask = (
        all_data["winery"].fillna("").astype(str).str.strip().str.casefold().eq(winery)
        & all_data["wine"].fillna("").astype(str).str.strip().str.casefold().eq(wine)
    )
    if vintage is not None:
        numeric_vintage = all_data["vintage"]
        mask &= numeric_vintage.eq(float(vintage))
    return all_data.loc[mask].copy()
