from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any


AI_CATALOG_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "wine": {"type": ["string", "null"]},
        "vintage": {"type": ["integer", "null"]},
        "regular_price": {"type": ["number", "null"]},
        "sale_price": {"type": ["number", "null"]},
        "club_price": {"type": ["number", "null"]},
        "currency": {"type": ["string", "null"]},
        "varietal": {"type": ["string", "null"]},
        "graph_category": {"type": ["string", "null"]},
        "general_category": {"type": ["string", "null"]},
        "region": {"type": ["string", "null"]},
        "subregion": {"type": ["string", "null"]},
        "alcohol_pct": {"type": ["number", "null"]},
        "cases_produced": {"type": ["integer", "null"]},
        "estate_status": {"type": "string", "enum": ["Yes", "No", "Unknown"]},
        "single_vineyard_status": {"type": "string", "enum": ["Yes", "No", "Unknown"]},
        "product_tier": {"type": ["string", "null"]},
        "availability_status": {"type": ["string", "null"]},
        "overall_confidence": {"type": "string", "enum": ["High", "Moderate", "Low"]},
        "evidence": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "wine": {"type": ["string", "null"]},
                "vintage": {"type": ["string", "null"]},
                "regular_price": {"type": ["string", "null"]},
                "sale_price": {"type": ["string", "null"]},
                "club_price": {"type": ["string", "null"]},
                "varietal": {"type": ["string", "null"]},
                "region": {"type": ["string", "null"]},
                "subregion": {"type": ["string", "null"]},
                "alcohol_pct": {"type": ["string", "null"]},
                "cases_produced": {"type": ["string", "null"]},
                "estate_status": {"type": ["string", "null"]},
                "single_vineyard_status": {"type": ["string", "null"]},
                "product_tier": {"type": ["string", "null"]},
                "availability_status": {"type": ["string", "null"]},
            },
            "required": [
                "wine", "vintage", "regular_price", "sale_price", "club_price",
                "varietal", "region", "subregion", "alcohol_pct", "cases_produced",
                "estate_status", "single_vineyard_status", "product_tier", "availability_status",
            ],
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "wine", "vintage", "regular_price", "sale_price", "club_price", "currency",
        "varietal", "graph_category", "general_category", "region", "subregion",
        "alcohol_pct", "cases_produced", "estate_status", "single_vineyard_status",
        "product_tier", "availability_status", "overall_confidence", "evidence", "warnings",
    ],
}


AI_CATALOG_INSTRUCTIONS = r"""
You are a conservative wine-product extraction agent inside Wine Market Intelligence.
You receive evidence from ONE product page that has already been fetched by the application.
Your job is to interpret that evidence semantically and return a structured wine record.

Core rules:
- Extract ONLY facts supported by the supplied evidence. Never fill a missing fact from outside knowledge.
- Use null when a fact is absent, ambiguous, or only implied.
- Prefer explicit structured product data and explicit product-local technical fields over prose.
- Product navigation, menus, category links, footer text, related products, and generic site-wide marketing MUST NOT determine the wine's category or attributes.
- Treat the supplied deterministic candidate as a hint, not as ground truth. Preserve it when supported; correct it when the page evidence clearly contradicts it.
- Do not infer appellation, estate status, single-vineyard status, or tier merely from the winery's identity.

Pricing rules:
- regular_price = ordinary public bottle price for the product.
- sale_price ONLY when a second numeric price is explicitly a sale/promotion/current reduced price for the same bottle.
- club_price ONLY when a numeric price is explicitly labeled member/club pricing for the same bottle.
- Quantity/case discounts such as "12+", "6 bottles", "case price", "1-11 / 12+", or volume tiers are NOT sale prices and NOT club prices. Ignore them for sale_price/club_price.
- If the page says members receive special pricing but does not show a numeric member price, club_price must be null.
- Never assume a struck-through or second price is a sale unless the evidence clearly establishes that relationship.

Wine identity/category rules:
- Keep the marketed product name faithful to the page but separate a leading/trailing vintage into the vintage field.
- varietal may be a single grape or explicit blend composition. Preserve percentages when explicitly shown.
- graph_category should describe the marketed wine identity/category. Examples: Cabernet Sauvignon, Pinot Noir, Chardonnay, Zinfandel, Bordeaux Blend, Rhône Blend, Red Blend, White Blend, Rosé, Other.
- general_category should be Red, White, Rosé, Sparkling, Dessert, Fortified, or Other when clearly supported.
- A disclosed blend composition does not automatically erase a marketed varietal identity. Example: a wine explicitly sold as Cabernet Sauvignon can remain Cabernet Sauvignon even if minor blending grapes are disclosed.
- G-S-M/GSM means a Rhône-style Grenache/Syrah/Mourvèdre blend when that identity is explicit.
- Late-harvest/sweet wording may support Dessert as the general category when clearly tied to the product.

Estate/single-vineyard/tier rules:
- estate_status = Yes only when the finished wine is explicitly estate-designated or all fruit for the finished wine is explicitly estate-grown/sourced. Unknown when not stated.
- single_vineyard_status = Yes only when the finished wine is clearly from one named vineyard or explicitly called single-vineyard. Multiple vineyard sources => No when explicit; otherwise Unknown.
- product_tier should be one of Core, Estate, Limited, Reserve, Flagship when explicitly supported. Do not match substrings such as "preserve" as Reserve.

Evidence rules:
- For every non-null extracted fact, provide a short evidence snippet or concise paraphrase in the corresponding evidence field.
- Evidence should be short (normally under 160 characters) and come only from the supplied page evidence.
- If a value is null/Unknown, evidence can be null.
- Put unresolved contradictions or notable ambiguity in warnings.

Confidence:
- High: product-local or structured evidence strongly supports the core identity/pricing and there are no material contradictions.
- Moderate: useful record but one or more important facts required interpretation, are missing, or the page is legacy/noisy.
- Low: material ambiguity remains; use null rather than guessing.
""".strip()


def _get_api_key() -> str | None:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:
        return None


def get_catalog_ai_model() -> str:
    model = os.getenv("OPENAI_CATALOG_MODEL")
    if model:
        return model
    try:
        import streamlit as st
        configured = st.secrets.get("OPENAI_CATALOG_MODEL")
        if configured:
            return configured
    except Exception:
        pass
    try:
        from vision_intake import get_default_model
        return get_default_model()
    except Exception:
        return "gpt-5.6-terra"


def ai_catalog_available() -> bool:
    return bool(_get_api_key())


def _clean_snippet(value: Any, max_len: int = 220) -> str:
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return text[:max_len]


def _sanitize_numeric(value: Any, low: float, high: float) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        num = float(value)
    except Exception:
        return None
    if not (low <= num <= high):
        return None
    return num


def validate_ai_catalog_result(result: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic sanity checks after model extraction.

    The model interprets context; deterministic code still owns basic type/range
    validation and removes unsupported values rather than letting them enter review.
    """
    out = dict(result or {})
    current_year = date.today().year

    vintage = out.get("vintage")
    try:
        vintage = int(vintage) if vintage is not None else None
    except Exception:
        vintage = None
    if vintage is not None and not (1900 <= vintage <= current_year + 2):
        vintage = None
    out["vintage"] = vintage

    for field, bounds in {
        "regular_price": (0.01, 10000.0),
        "sale_price": (0.01, 10000.0),
        "club_price": (0.01, 10000.0),
        "alcohol_pct": (4.0, 25.0),
    }.items():
        out[field] = _sanitize_numeric(out.get(field), *bounds)

    cases = out.get("cases_produced")
    try:
        cases = int(cases) if cases is not None else None
    except Exception:
        cases = None
    if cases is not None and not (1 <= cases <= 10_000_000):
        cases = None
    out["cases_produced"] = cases

    for field in [
        "wine", "currency", "varietal", "graph_category", "general_category",
        "region", "subregion", "product_tier", "availability_status", "overall_confidence",
    ]:
        value = out.get(field)
        out[field] = None if value is None else re.sub(r"\s+", " ", str(value)).strip() or None

    if out.get("overall_confidence") not in {"High", "Moderate", "Low"}:
        out["overall_confidence"] = "Moderate"
    if out.get("product_tier") not in {None, "Core", "Estate", "Limited", "Reserve", "Flagship"}:
        out["product_tier"] = None
    if out.get("estate_status") not in {"Yes", "No", "Unknown"}:
        out["estate_status"] = "Unknown"
    if out.get("single_vineyard_status") not in {"Yes", "No", "Unknown"}:
        out["single_vineyard_status"] = "Unknown"

    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    out["evidence"] = {k: (_clean_snippet(v) or None) for k, v in evidence.items()}
    warnings = out.get("warnings") if isinstance(out.get("warnings"), list) else []
    out["warnings"] = [_clean_snippet(x, 300) for x in warnings if _clean_snippet(x, 300)][:8]

    # Do not allow a semantic field to survive without evidence, except the two
    # derived category fields which may be a classification of supported identity.
    evidence_map = {
        "wine": "wine", "vintage": "vintage", "regular_price": "regular_price",
        "sale_price": "sale_price", "club_price": "club_price", "varietal": "varietal",
        "region": "region", "subregion": "subregion", "alcohol_pct": "alcohol_pct",
        "cases_produced": "cases_produced", "product_tier": "product_tier",
        "availability_status": "availability_status",
    }
    for field, ev_field in evidence_map.items():
        if out.get(field) is not None and not out["evidence"].get(ev_field):
            out[field] = None

    if out.get("estate_status") != "Unknown" and not out["evidence"].get("estate_status"):
        out["estate_status"] = "Unknown"
    if out.get("single_vineyard_status") != "Unknown" and not out["evidence"].get("single_vineyard_status"):
        out["single_vineyard_status"] = "Unknown"

    return out


def extract_catalog_record_with_ai(
    evidence_payload: dict[str, Any],
    *,
    producer_hint: str = "",
    deterministic_candidate: dict[str, Any] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Interpret one already-fetched product page with structured output.

    This function makes no website requests. It only sends bounded textual evidence
    already collected by the catalog scanner to the configured OpenAI model.
    """
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. AI-assisted catalog extraction is unavailable, but deterministic scanning can still run."
        )

    from openai import OpenAI

    payload = {
        "producer_hint": producer_hint or None,
        "page_url": evidence_payload.get("page_url"),
        "page_title": evidence_payload.get("page_title"),
        "text_scope": evidence_payload.get("text_scope"),
        "structured_product_data": evidence_payload.get("structured_product_data") or [],
        "product_local_text": evidence_payload.get("product_local_text") or "",
        "deterministic_candidate": deterministic_candidate or None,
    }
    prompt = (
        "Extract the wine-product facts from this single-page evidence bundle. "
        "Use the deterministic candidate only as a hint and follow the evidence hierarchy exactly.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model or get_catalog_ai_model(),
        store=False,
        instructions=AI_CATALOG_INSTRUCTIONS,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        text={
            "format": {
                "type": "json_schema",
                "name": "wine_market_catalog_extraction",
                "description": "Conservative facts extracted from one winery product page.",
                "schema": AI_CATALOG_SCHEMA,
                "strict": True,
            },
            "verbosity": "low",
        },
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("The AI catalog extractor returned no structured output.")
    return validate_ai_catalog_result(json.loads(output_text))
