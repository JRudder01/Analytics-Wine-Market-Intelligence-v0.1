from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag

USER_AGENT = (
    "WineCatalogResearch/0.1 "
    "(user-initiated single-page request)"
)
CATALOG_PARSER_BUILD = "v0.3.24"
MAX_HTML_BYTES = 2_000_000
REQUEST_TIMEOUT = (5, 12)
ROBOTS_TTL_SECONDS = 24 * 60 * 60
PAGE_CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_REDIRECTS = 3

_ROBOTS_CACHE: dict[str, tuple[float, RobotFileParser | None, str]] = {}
_PAGE_CACHE: dict[str, tuple[float, str, str, str, str]] = {}  # ts, html, content_type, etag, last_modified
_JSON_CACHE: dict[str, tuple[float, Any]] = {}
VINOSHIPPER_HOSTS = {"vinoshipper.com", "www.vinoshipper.com"}

PRICE_RE = re.compile(
    r"(?:(retail|msrp|regular|list|sale|club|member|membership|wine\s+society)\s*(?:price)?\s*[:\-]?\s*)?"
    r"\$\s*([0-9]{1,4}(?:\.[0-9]{1,2})?)",
    re.I,
)
VINTAGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
NV_RE = re.compile(r"(?:^|\b)(?:NV|N\.V\.|NON[- ]?VINTAGE)(?:\b|$)", re.I)


class CatalogScanError(RuntimeError):
    pass


@dataclass
class CatalogFetch:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    html: str
    bytes_read: int
    robots_status: str
    request_note: str = "network fetch"
    user_agent: str = USER_AGENT
    provider: str = ""
    provider_note: str = ""
    provider_requests: int = 0


@dataclass
class WineOffer:
    wine: str
    vintage: str
    regular_price: float | None
    sale_price: float | None
    club_price: float | None
    currency: str
    product_url: str
    evidence: str
    extraction_method: str
    confidence: str
    varietal: str = ""
    graph_category: str = ""
    general_category: str = ""
    region: str = ""
    subregion: str = ""
    alcohol_pct: float | None = None
    cases_produced: int | None = None
    estate: bool = False
    single_vineyard: bool = False
    product_tier: str = "Core"
    availability_status: str = ""
    provider_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProductLink:
    label: str
    url: str
    context: str
    confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ascii_key(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    return re.sub(r"\s+", " ", text)


def _canonical_wine_name(name: str, vintage: str = "") -> str:
    """Keep the product identity separate from its vintage field."""
    cleaned = _clean_name(name)
    if not cleaned:
        return cleaned
    year = str(vintage or "").strip()
    years = [year] if re.fullmatch(r"(?:19|20)\d{2}", year) else []
    # If no vintage was supplied yet, still strip an obvious terminal year.
    if not years:
        m = re.search(r"(?:^|[\s—–-])((?:19|20)\d{2})$", cleaned)
        if m:
            years = [m.group(1)]
    for y in years:
        cleaned = re.sub(rf"^\s*{re.escape(y)}\s*(?:[—–-]\s*)?", "", cleaned).strip()
        cleaned = re.sub(rf"\s*(?:[—–-]\s*)?{re.escape(y)}\s*$", "", cleaned).strip()
    return cleaned.strip(" —–-")



def is_vinoshipper_url(url: str) -> bool:
    try:
        host = (urlparse(str(url or "")).hostname or "").casefold()
    except Exception:
        return False
    return host in VINOSHIPPER_HOSTS or host.endswith(".vinoshipper.com")


def _producer_id_from_url(url: str) -> str:
    """Extract a VinoShipper producer/winery id when the pasted URL already exposes one."""
    text = str(url or "")
    patterns = [
        r"/api/v3/feeds/vs/(\d+)(?:/|$)",
        r"[?&](?:producerId|producer_id|wineryId|winery_id|id)=(\d+)(?:&|$)",
        r"filters(?:%5B|\[)1(?:%5D|\])\.?(?:value|%2Evalue)?(?:=|%3D)(\d+)",
        r"filters%5B1%5D\.value=(\d+)",
        r"filters\[1\]\.value=(\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    return ""


def infer_vinoshipper_producer_id(html: str, url: str = "") -> str:
    """Best-effort producer-id discovery from VinoShipper's public shop shell.

    VinoShipper's client components need a producer/account id. Different
    generations of their embed code have used slightly different names, so we
    accept several explicit configuration forms but never guess from unrelated
    page numbers.
    """
    url_id = _producer_id_from_url(url)
    if url_id:
        return url_id
    text = str(html or "")
    patterns = [
        r"Vinoshipper\.init\(\s*[\"']?(\d+)",
        r"data-vs-(?:account|producer|winery)-id\s*=\s*[\"'](\d+)[\"']",
        r"[\"'](?:producerId|producerID|producer_id|accountId|accountID|account_id|wineryId|wineryID|winery_id)[\"']\s*[:=]\s*[\"']?(\d+)",
        r"/api/v3/feeds/vs/(\d+)/products",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1)
    return ""


def _json_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.8",
        "Connection": "close",
    }


def _fetch_public_json(url: str) -> Any:
    """Fetch one public JSON feed request with the same conservative controls."""
    target = validate_public_url(url)
    now = time.time()
    cached = _JSON_CACHE.get(target.casefold())
    if cached and now - cached[0] < PAGE_CACHE_TTL_SECONDS:
        return cached[1]
    try:
        response = requests.get(
            target,
            headers=_json_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as exc:
        raise CatalogScanError(f"Provider feed request failed: {exc}") from exc
    if response.status_code in {301, 302, 303, 307, 308}:
        raise CatalogScanError("Provider feed redirected unexpectedly; scan stopped.")
    if response.status_code in {401, 403}:
        raise CatalogScanError(
            f"The provider feed returned HTTP {response.status_code}; the tool will not bypass it."
        )
    if response.status_code == 429:
        raise CatalogScanError("The provider feed returned HTTP 429; the tool will not retry automatically.")
    if response.status_code >= 400:
        raise CatalogScanError(f"The provider feed returned HTTP {response.status_code}.")
    content_type = (response.headers.get("Content-Type") or "").casefold()
    if "json" not in content_type and content_type:
        raise CatalogScanError(f"The provider feed returned {content_type.split(';',1)[0]!r}, not JSON.")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_HTML_BYTES:
            raise CatalogScanError("The provider feed exceeded the 2 MB safety limit.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        payload = json.loads(raw.decode(response.encoding or "utf-8", errors="replace"))
    except Exception as exc:
        raise CatalogScanError("The provider feed returned invalid JSON.") from exc
    _JSON_CACHE[target.casefold()] = (now, payload)
    return payload


def _json_lookup(node: dict[str, Any], *keys: str) -> Any:
    wanted = {_ascii_key(k).replace(" ", "") for k in keys}
    for key, value in node.items():
        norm = _ascii_key(key).replace(" ", "")
        if norm in wanted and value not in (None, ""):
            return value
    return None


def _json_text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, dict):
        for key in ("name", "title", "label", "value", "description"):
            found = _json_lookup(value, key)
            if found not in (None, ""):
                return _json_text(found)
        return " ".join(_json_text(v) for v in value.values() if _json_text(v))
    if isinstance(value, list):
        return ", ".join(x for x in (_json_text(v) for v in value) if x)
    return _clean_name(value)


def _json_bool(node: dict[str, Any], *keys: str) -> bool | None:
    value = _json_lookup(node, *keys)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    key = _ascii_key(value)
    if key in {"true", "yes", "1", "y"}:
        return True
    if key in {"false", "no", "0", "n"}:
        return False
    return None


def _json_lookup_deep(node: Any, *keys: str, max_depth: int = 5) -> Any:
    """Find a named field inside a product object without assuming one feed schema.

    VinoShipper has changed/expanded product-feed shapes over time.  The public
    feed may place vintage, varietal, appellation, or metadata inside nested
    objects.  This helper searches only for explicit key aliases; it does not
    scrape arbitrary numbers or guess from unrelated dates.
    """
    wanted = {_ascii_key(k).replace(" ", "") for k in keys}

    def walk(value: Any, depth: int) -> Any:
        if depth > max_depth:
            return None
        if isinstance(value, dict):
            # Prefer a matching field at the current level before descending.
            for key, child in value.items():
                norm = _ascii_key(key).replace(" ", "")
                if norm in wanted and child not in (None, "", [], {}):
                    return child
            for child in value.values():
                found = walk(child, depth + 1)
                if found not in (None, "", [], {}):
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child, depth + 1)
                if found not in (None, "", [], {}):
                    return found
        return None

    return walk(node, 0)


def _vintage_from_feed_node(node: dict[str, Any], raw_name: str, description: str = "") -> str:
    """Return only a defensible wine vintage (or NV) from a provider record."""
    direct = _json_lookup(
        node,
        "vintage", "vintageYear", "vintage_year", "productVintage", "product_vintage",
        "vintageLabel", "vintageName",
    )
    if direct in (None, "", [], {}):
        direct = _json_lookup_deep(
            node,
            "vintage", "vintageYear", "vintage_year", "productVintage", "product_vintage",
            "vintageLabel", "vintageName",
        )
    text = _json_text(direct)
    m = re.search(r"\b((?:19|20)\d{2})\b", text)
    if m:
        return m.group(1)
    if NV_RE.search(text):
        return "NV"

    # VinoShipper documents that a defined vintage is prepended to a product
    # title in its catalog.  Some feed variants expose only a display/title form.
    for candidate in (raw_name, description):
        year = _vintage_from_name(candidate)
        if year:
            return year
        if NV_RE.search(candidate or ""):
            return "NV"
    return ""


_GRAPE_ALIAS_MAP = {
    "pino noir": "Pinot Noir",
    "pinot noir": "Pinot Noir",
    "petite verdot": "Petit Verdot",
    "petit verdot": "Petit Verdot",
    "cabernet": "Cabernet Sauvignon",
    "cab sauv": "Cabernet Sauvignon",
    "cabernet sauv": "Cabernet Sauvignon",
    "cab franc": "Cabernet Franc",
    "petite syrah": "Petite Sirah",
    "mourvedre": "Mourvèdre",
    "semillon": "Sémillon",
    "albarino": "Albariño",
}

_PRODUCT_LABEL_ALIAS_MAP = {
    "pino noir": "Pinot Noir",
    "petite verdot": "Petit Verdot",
}


# Source-specific corrections are a last-resort quality layer, not the primary parser.
# They are keyed by the public provider ID + canonical product identity + vintage and
# are only used when the provider feed omits or mislabels a stable wine fact.
# Keeping these overrides explicit makes them auditable and prevents source quirks
# from becoming global classification rules.
_VINOSHIPPER_PRODUCT_OVERRIDES: dict[tuple[str, str, str], dict[str, Any]] = {
    ("4112", "better together", "2021"): {
        "alcohol_pct": 15.34,
        "varietal": "85% Zinfandel, 15% Petite Sirah",
        "graph_category": "Zinfandel",
    },
    ("4112", "cabernet and merlot blend", "2018"): {"alcohol_pct": 13.65},
    ("4112", "cabernet franc", "2023"): {"alcohol_pct": 15.3},
    ("4112", "cabernet sauvignon", "2021"): {"alcohol_pct": 15.58},
    ("4112", "distinctive", "2022"): {
        "alcohol_pct": 15.3,
        "varietal": "50% Cabernet Sauvignon, 50% Petite Sirah",
        "graph_category": "Red Blend",
    },
    ("4112", "distinctive", "2023"): {
        "alcohol_pct": 15.4,
        "graph_category": "Red Blend",
    },
    ("4112", "le rhone", "2021"): {
        "alcohol_pct": 14.4,
        "varietal": "67% Mourvèdre, 33% Grenache",
        "graph_category": "Rhône Blend",
    },
    ("4112", "le rhone", "2023"): {
        "alcohol_pct": 15.1,
        "varietal": "38% Grenache, 32% Syrah, 30% Mourvèdre",
        "graph_category": "Rhône Blend",
    },
    ("4112", "merlot", "2019"): {"alcohol_pct": 14.95},
    ("4112", "petit verdot", "2021"): {"alcohol_pct": 14.77},
    ("4112", "petite sirah", "2023"): {"alcohol_pct": 16.0},
    ("4112", "pinot noir", "2023"): {"alcohol_pct": 14.54},
    ("4112", "reserve cabernet sauvignon", "2022"): {"alcohol_pct": 15.4},
    ("4112", "tannat", "2023"): {"alcohol_pct": 15.9},
    ("4112", "trois", "2021"): {
        "alcohol_pct": 15.3,
        "varietal": "69% Malbec, 17% Petit Verdot, 14% Cabernet Sauvignon",
        "graph_category": "Bordeaux Blend",
    },
}


def _normalize_wine_label_aliases(value: str) -> str:
    clean = _clean_name(value)
    exact = _PRODUCT_LABEL_ALIAS_MAP.get(_ascii_key(clean))
    if exact:
        return exact
    # Also fix these provider spelling variants when they occur inside a tiered title.
    clean = re.sub(r"\bPino Noir\b", "Pinot Noir", clean, flags=re.I)
    clean = re.sub(r"\bPetite Verdot\b", "Petit Verdot", clean, flags=re.I)
    return clean


def _canonical_grape_name(value: str) -> str:
    clean = _clean_name(value)
    key = _ascii_key(clean)
    return _GRAPE_ALIAS_MAP.get(key, clean)


def _normalize_varietal_aliases(value: str) -> str:
    """Normalize common provider spelling/label aliases without inventing grapes."""
    text = _clean_name(value)
    if not text:
        return ""
    if _ascii_key(text) in {"gsm", "g s m"}:
        return "Grenache, Syrah, Mourvèdre"
    # Preserve percentages while normalizing the grape phrase following them.
    pieces = re.split(r"\s*(?:,|/|\+|\band\b)\s*", text, flags=re.I)
    normalized: list[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        m = re.match(r"^(\d{1,3}%\s*)?(.*)$", piece)
        pct, grape = (m.group(1) or ""), (m.group(2) or "").strip()
        canonical = _canonical_grape_name(grape)
        normalized.append(f"{pct}{canonical}".strip())
    return ", ".join(normalized) if normalized else text


def _title_explicit_blend(title: str) -> str:
    """Extract a simple multi-grape blend stated directly in a product title."""
    t = _clean_name(title)
    if not t or "blend" not in t.casefold():
        return ""
    body = re.sub(r"\bblend\b.*$", "", t, flags=re.I).strip(" -–—")
    parts = re.split(r"\s*(?:&|\band\b|/|\+)\s*", body, flags=re.I)
    grapes: list[str] = []
    for part in parts:
        key = _ascii_key(part)
        if not key:
            continue
        canonical = _GRAPE_ALIAS_MAP.get(key)
        if canonical is None:
            # Accept full known grape names; reject marketing words.
            known = _extract_varietal(part, part)
            canonical = _canonical_grape_name(known) if known else ""
        if canonical and _ascii_key(canonical) not in {_ascii_key(x) for x in grapes}:
            grapes.append(canonical)
    return ", ".join(grapes) if len(grapes) >= 2 else ""


def _prefer_explicit_blend(provider_varietal: str, title: str, rich_text: str) -> str:
    """Prefer explicit multi-grape evidence over a single provider category label."""
    provider = _normalize_varietal_aliases(provider_varietal)
    title_blend = _title_explicit_blend(title)
    inferred = _normalize_varietal_aliases(_extract_varietal(title, rich_text))

    def grape_count(value: str) -> int:
        if not value:
            return 0
        # Percentage lists and comma-separated normalized lists both count.
        parts = [p for p in re.split(r"\s*,\s*", value) if p.strip()]
        return len(parts)

    # Explicit title/composition evidence wins when it identifies multiple grapes.
    if grape_count(title_blend) >= 2:
        return title_blend
    if grape_count(inferred) >= 2 and grape_count(provider) <= 1:
        return inferred
    return provider or inferred


def _labeled_metadata_value(node: Any, labels: tuple[str, ...], *, max_depth: int = 7) -> Any:
    """Find a value stored as a generic label/value metadata pair.

    Provider feeds often encode technical facts as [{label: "Alcohol Level",
    value: "15.3%"}] rather than as a stable top-level field.  This helper is
    conservative: the label must clearly match one of the requested concepts.
    """
    wanted = {_ascii_key(x) for x in labels}

    def label_matches(value: Any) -> bool:
        key = _ascii_key(_json_text(value))
        if not key:
            return False
        return any(key == w or w in key for w in wanted)

    def walk(value: Any, depth: int) -> Any:
        if depth > max_depth:
            return None
        if isinstance(value, dict):
            label = _json_lookup(value, "label", "name", "key", "type", "code", "field", "metric")
            if label_matches(label):
                candidate = _json_lookup(value, "value", "amount", "number", "text", "displayValue", "display")
                if candidate not in (None, "", [], {}):
                    return candidate
            for child in value.values():
                found = walk(child, depth + 1)
                if found not in (None, "", [], {}):
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child, depth + 1)
                if found not in (None, "", [], {}):
                    return found
        return None

    return walk(node, 0)


def _coerce_percent(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    text = _json_text(value) if isinstance(value, (dict, list)) else str(value)
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%?", text.replace(",", ""))
    if not m:
        return None
    try:
        number = float(m.group(1))
    except ValueError:
        return None
    # Some APIs encode percentages as fractions.
    if 0 < number <= 1:
        number *= 100
    if 5 <= number <= 25:
        return round(number, 3)
    return None


def _extract_vinoshipper_abv(node: dict[str, Any], evidence_text: str = "") -> float | None:
    aliases = (
        "alcohol", "alcoholLevel", "alcohol_level", "alcoholPct", "alcohol_pct",
        "abv", "alcoholByVolume", "alcohol_by_volume", "alcoholPercent",
        "alcoholPercentage", "alcoholContent",
    )
    direct = _json_lookup(node, *aliases)
    if direct in (None, "", [], {}):
        direct = _json_lookup_deep(node, *aliases, max_depth=8)
    value = _coerce_percent(direct)
    if value is not None:
        return value
    labeled = _labeled_metadata_value(
        node,
        ("alcohol level", "abv", "alcohol by volume", "alcohol percentage", "alcohol percent"),
    )
    value = _coerce_percent(labeled)
    if value is not None:
        return value
    return _extract_abv(evidence_text)


def _extract_feed_composition(node: dict[str, Any], evidence_text: str = "") -> str:
    aliases = (
        "composition", "wineComposition", "wine_composition", "blendComposition",
        "blend_composition", "grapeComposition", "grape_composition", "varietals",
        "grapeVarieties", "grape_varieties", "grapes",
    )
    direct = _json_lookup(node, *aliases)
    if direct in (None, "", [], {}):
        direct = _json_lookup_deep(node, *aliases, max_depth=8)
    text = _json_text(direct)
    if text:
        parsed = _normalize_varietal_aliases(_extract_varietal("", text) or text)
        if parsed:
            return parsed
    labeled = _labeled_metadata_value(node, ("composition", "blend", "varietal composition", "grape composition"))
    if labeled not in (None, "", [], {}):
        text = _json_text(labeled)
        parsed = _normalize_varietal_aliases(_extract_varietal("", text) or text)
        if parsed:
            return parsed
    inferred = _normalize_varietal_aliases(_extract_varietal("", evidence_text))
    return inferred if "," in inferred or "%" in inferred else ""


def _normalize_provider_appellation(value: str) -> str:
    """Remove provider display wrappers without inventing a narrower AVA."""
    text = _clean_name(value)
    if not text:
        return ""
    text = re.sub(r"^CA\s*[-–—:]\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s*\((?:Central Coast|North Coast|California)\)\s*$", "", text, flags=re.I).strip()
    # Provider strings sometimes use County - AVA. Prefer the explicit AVA at
    # the end when it is a recognized winegrowing area; otherwise retain county.
    known_specific = [
        "San Antonio Valley", "San Luis Obispo Coast", "Paso Robles", "Napa Valley",
        "El Pomar District", "Templeton Gap District", "Adelaida District",
        "Willow Creek District", "Geneseo District", "Creston District",
        "Estrella District", "San Juan Creek District", "York Mountain",
    ]
    for name in known_specific:
        if re.search(rf"\b{re.escape(name)}\b", text, re.I):
            # If this is an explicit nested AVA (e.g. Monterey County - San Antonio Valley),
            # use the AVA.  Paso Robles remains a broad region and can still have a subregion.
            if " - " in text and text.casefold().rstrip().endswith(name.casefold()):
                return name
    return text


def _provider_varietal_is_title_noise(provider_varietal: str, canonical_name: str) -> bool:
    p = _ascii_key(provider_varietal)
    t = _ascii_key(canonical_name)
    if not p or not t:
        return False
    # A feed typo like "Distinvtive" in the varietal slot is much closer to the
    # marketing product name than to a grape.  Do not propagate it as varietal.
    known_grape = _infer_graph_category(provider_varietal, provider_varietal, provider_varietal) != "Other"
    return (not known_grape) and SequenceMatcher(None, p, t).ratio() >= 0.78


def _apply_vinoshipper_record_override(
    *, producer_id: str, wine: str, vintage: str, varietal: str,
    graph_category: str, alcohol_pct: float | None,
) -> tuple[str, str, float | None]:
    override = _VINOSHIPPER_PRODUCT_OVERRIDES.get(
        (str(producer_id), _ascii_key(wine), str(vintage or "")), {}
    )
    if not override:
        return varietal, graph_category, alcohol_pct
    if override.get("varietal"):
        varietal = str(override["varietal"])
    if override.get("graph_category"):
        graph_category = str(override["graph_category"])
    if alcohol_pct is None and override.get("alcohol_pct") is not None:
        alcohol_pct = float(override["alcohol_pct"])
    return varietal, graph_category, alcohol_pct



def _normalize_offer_geography(region: str, subregion: str = "") -> tuple[str, str]:
    """Normalize provider display geography into the app's region/subregion fields.

    This is deliberately conservative: it strips provider wrappers, preserves a
    broad region when known, and only promotes a trailing AVA/district when it is
    explicit. It never invents a parent AVA from a county name.
    """
    raw_region = _clean_name(region)
    raw_subregion = _clean_name(subregion)
    if not raw_region and not raw_subregion:
        return "", ""

    text = re.sub(r"^CA\s*[-–—:]\s*", "", raw_region, flags=re.I).strip()
    text = re.sub(r"\s*\((?:Central Coast|North Coast|California)\)\s*$", "", text, flags=re.I).strip()

    # Common provider wrapper: "Monterey County - San Antonio Valley".
    if " - " in text:
        parts = [x.strip() for x in text.split(" - ") if x.strip()]
        if len(parts) >= 2:
            trailing = parts[-1]
            recognized_tail = {
                "san antonio valley", "san luis obispo coast", "paso robles",
                "el pomar district", "templeton gap district", "adelaida district",
                "willow creek district", "geneseo district", "creston district",
                "estrella district", "san juan creek district", "york mountain",
            }
            if _ascii_key(trailing) in recognized_tail:
                text = trailing

    # Paso-style comma hierarchy: broad AVA + nested district.
    if "," in text:
        parts = [x.strip() for x in text.split(",") if x.strip()]
        if parts:
            broad = parts[0]
            narrow = parts[1] if len(parts) > 1 else ""
            if _ascii_key(broad) == "paso robles" and narrow:
                return "Paso Robles", narrow
            if len(parts) == 1:
                text = broad

    if _ascii_key(text) in {
        "el pomar district", "templeton gap district", "adelaida district",
        "willow creek district", "geneseo district", "creston district",
        "estrella district", "san juan creek district",
    }:
        return "Paso Robles", text

    # If the dedicated subregion is useful, keep it unless it duplicates region.
    if raw_subregion and _ascii_key(raw_subregion) != _ascii_key(text):
        return text, raw_subregion
    return text, ""


def _finalize_vinoshipper_offer(offer: WineOffer, producer_id: str = "") -> WineOffer:
    """Last-pass provider normalization immediately before review/staging.

    All VinoShipper paths pass through this function, including rows already
    extracted successfully upstream. That prevents provider-shape differences
    from bypassing identity, blend, geography, ABV, and confidence cleanup.
    """
    pid = str(producer_id or offer.provider_id or "").strip()
    offer.provider_id = pid
    offer.wine = _normalize_wine_label_aliases(_canonical_wine_name(offer.wine, offer.vintage))
    offer.vintage = str(offer.vintage or "").strip()
    if re.fullmatch(r"\d{4}\.0", offer.vintage):
        offer.vintage = offer.vintage[:-2]

    # Normalize provider spelling before applying product-specific verified facts.
    offer.varietal = _normalize_varietal_aliases(offer.varietal)
    key = (pid, _ascii_key(offer.wine), offer.vintage)
    override = _VINOSHIPPER_PRODUCT_OVERRIDES.get(key, {})
    if override.get("varietal"):
        offer.varietal = _normalize_varietal_aliases(str(override["varietal"]))
    if override.get("graph_category"):
        offer.graph_category = str(override["graph_category"])
    if override.get("alcohol_pct") is not None:
        # These values are source-verified fallback facts used only for records
        # whose provider feed omitted the field.
        if offer.alcohol_pct is None:
            offer.alcohol_pct = float(override["alcohol_pct"])

    wine_key = _ascii_key(offer.wine)
    varietal_key = _ascii_key(offer.varietal)

    # Generic named-blend guardrails. They apply even if the provider supplied a
    # misleading lead-varietal classification.
    if "cabernet and merlot blend" in wine_key:
        offer.varietal = "Cabernet Sauvignon, Merlot"
        offer.graph_category = "Bordeaux Blend"
    elif wine_key == "distinctive":
        if varietal_key in {"distinctive", "distinvtive", "cabernet sauvignon"} and not override.get("varietal"):
            offer.varietal = ""
        offer.graph_category = "Red Blend"
    elif wine_key == "trois" and not override.get("graph_category"):
        offer.graph_category = "Red Blend"
    elif wine_key == "le rhone":
        if varietal_key in {"gsm", "g s m"}:
            offer.varietal = "Grenache, Syrah, Mourvèdre"
        offer.graph_category = "Rhône Blend"

    # Recompute graph category only when a verified/specific rule has not already
    # supplied it, or when the current category is empty/Other.
    if not offer.graph_category or offer.graph_category == "Other":
        offer.graph_category = _infer_graph_category(offer.varietal, offer.wine, offer.evidence)

    # Multi-grape compositions should not remain classified as a single varietal.
    grape_parts = [p.strip() for p in re.split(r"\s*,\s*", offer.varietal or "") if p.strip()]
    if len(grape_parts) >= 2 and not override.get("graph_category") and offer.graph_category not in {"Bordeaux Blend", "Rhône Blend", "White Blend", "Red Blend", "Zinfandel"}:
        inferred = _infer_graph_category(offer.varietal, offer.wine, offer.evidence)
        offer.graph_category = inferred if "Blend" in inferred else "Red Blend"

    offer.general_category = _infer_general_category(offer.graph_category, offer.varietal, offer.wine)
    offer.region, offer.subregion = _normalize_offer_geography(offer.region, offer.subregion)

    # Reserve/estate/etc. remain whatever the upstream extractor determined unless
    # the title itself supplies an unambiguous stronger tier.
    title_key = _ascii_key(offer.wine)
    if "reserve" in title_key:
        offer.product_tier = "Reserve"

    has_price = any(x is not None for x in (offer.regular_price, offer.sale_price, offer.club_price))
    strong_identity = bool(offer.vintage and offer.varietal and offer.graph_category and offer.graph_category != "Other")
    offer.confidence = "High" if (has_price and strong_identity) else "Moderate"
    return offer


def finalize_vinoshipper_offers(offers: list[WineOffer], producer_id: str = "") -> list[WineOffer]:
    finalized = [_finalize_vinoshipper_offer(o, producer_id) for o in offers]
    return _dedupe(finalized)


def finalize_vinoshipper_offer_dicts(rows: list[dict[str, Any]], producer_id: str = "") -> list[dict[str, Any]]:
    """Re-normalize serialized VinoShipper rows already held in UI session state.

    Streamlit can preserve session_state across a code hot-reload.  Older serialized
    offer dictionaries must therefore be upgraded as well as newly fetched rows;
    otherwise a successful parser deployment can appear to have had no effect.
    """
    offers: list[WineOffer] = []
    pid_default = str(producer_id or "").strip()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        def _none_if_nan(value: Any) -> Any:
            try:
                if value != value:
                    return None
            except Exception:
                pass
            return value
        offers.append(WineOffer(
            wine=str(row.get("wine") or ""),
            vintage=str(row.get("vintage") or ""),
            regular_price=_none_if_nan(row.get("regular_price")),
            sale_price=_none_if_nan(row.get("sale_price")),
            club_price=_none_if_nan(row.get("club_price")),
            currency=str(row.get("currency") or "USD"),
            product_url=str(row.get("product_url") or ""),
            evidence=str(row.get("evidence") or ""),
            extraction_method=str(row.get("extraction_method") or "VinoShipper Product Feed"),
            confidence=str(row.get("confidence") or "Moderate"),
            varietal=str(row.get("varietal") or ""),
            graph_category=str(row.get("graph_category") or ""),
            general_category=str(row.get("general_category") or ""),
            region=str(row.get("region") or ""),
            subregion=str(row.get("subregion") or ""),
            alcohol_pct=_none_if_nan(row.get("alcohol_pct")),
            cases_produced=_none_if_nan(row.get("cases_produced")),
            estate=bool(row.get("estate", False)),
            single_vineyard=bool(row.get("single_vineyard", False)),
            product_tier=str(row.get("product_tier") or "Core"),
            availability_status=str(row.get("availability_status") or ""),
            provider_id=str(row.get("provider_id") or pid_default),
        ))
    return [o.to_dict() for o in finalize_vinoshipper_offers(offers, pid_default)]

def _looks_like_vinoshipper_product_node(node: dict[str, Any]) -> bool:
    name = _json_lookup(node, "name", "title", "productName", "wineName", "displayName")
    price = _json_lookup(node, "price", "consumerPrice", "retailPrice", "msrp", "unitPrice")
    product_id = _json_lookup(node, "id", "productId", "wineId")
    return bool(name and (price is not None or product_id is not None))


def _vinoshipper_product_nodes(payload: Any) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for node in _iter_json_nodes(payload):
        if _looks_like_vinoshipper_product_node(node):
            nodes.append(node)
    # Prefer the deepest/product-specific nodes and de-dupe by product id/name.
    unique: dict[str, dict[str, Any]] = {}
    for node in nodes:
        product_id = _json_text(_json_lookup(node, "id", "productId", "wineId"))
        name = _json_text(_json_lookup(node, "name", "title", "productName", "wineName", "displayName"))
        key = product_id or _ascii_key(name)
        if not key:
            continue
        current = unique.get(key)
        # Keep the richer object if duplicates occur in nested wrappers.
        if current is None or len(node) > len(current):
            unique[key] = node
    return list(unique.values())


def extract_vinoshipper_feed_offers(payload: Any, *, producer_id: str, shop_url: str) -> list[WineOffer]:
    """Convert the documented VinoShipper product feed into editable WineOffer rows.

    Field names have varied across versions, so extraction intentionally accepts
    several documented/common aliases and leaves uncertain fields blank instead
    of guessing.
    """
    results: list[WineOffer] = []
    for node in _vinoshipper_product_nodes(payload):
        raw_name = _json_text(_json_lookup(node, "name", "title", "productName", "wineName", "displayName"))
        if not raw_name:
            raw_name = _json_text(_json_lookup_deep(node, "productName", "wineName", "displayName", "title"))
        if not raw_name:
            continue

        description_value = _json_lookup(node, "description", "shortDescription", "productDescription", "notes", "tastingNotes")
        if description_value in (None, "", [], {}):
            description_value = _json_lookup_deep(
                node, "description", "shortDescription", "productDescription", "notes", "tastingNotes"
            )
        description = _json_text(description_value)
        vintage = _vintage_from_feed_node(node, raw_name, description)
        canonical_name = _canonical_wine_name(raw_name, vintage)
        canonical_name = _normalize_wine_label_aliases(canonical_name)

        consumer = _coerce_price(_json_lookup(node, "price", "consumerPrice", "retailPrice", "unitPrice", "currentPrice"))
        msrp = _coerce_price(_json_lookup(node, "msrp", "listPrice", "regularPrice"))
        sale = _coerce_price(_json_lookup(node, "salePrice", "discountPrice", "promotionalPrice"))
        club = _coerce_price(_json_lookup(node, "clubPrice", "memberPrice", "membershipPrice"))
        regular = msrp or consumer
        if sale is None and msrp is not None and consumer is not None and consumer < msrp:
            sale = consumer
        if regular is None and sale is None and club is None:
            continue

        provider_varietal_value = _json_lookup(
            node, "varietal", "variety", "grape", "grapes", "composition", "blend",
            "wineVarietal", "wine_varietal", "varietalName", "productVarietal"
        )
        if provider_varietal_value in (None, "", [], {}):
            provider_varietal_value = _json_lookup_deep(
                node, "varietal", "variety", "grape", "grapes", "composition", "blend",
                "wineVarietal", "wine_varietal", "varietalName", "productVarietal"
            )
        provider_varietal = _json_text(provider_varietal_value)
        if _provider_varietal_is_title_noise(provider_varietal, canonical_name):
            provider_varietal = ""

        appellation_value = _json_lookup(node, "appellation", "ava", "region", "origin")
        if appellation_value in (None, "", [], {}):
            appellation_value = _json_lookup_deep(node, "appellation", "ava", "region", "origin")
        appellation = _normalize_provider_appellation(_json_text(appellation_value))

        abv = _extract_vinoshipper_abv(node, " ".join(x for x in [raw_name, description] if x))

        cases_raw = _json_lookup(node, "casesProduced", "caseProduction", "productionCases")
        if cases_raw in (None, "", [], {}):
            cases_raw = _json_lookup_deep(node, "casesProduced", "caseProduction", "productionCases")
        cases = None
        if cases_raw not in (None, ""):
            m = re.search(r"[0-9][0-9,]*", str(cases_raw))
            if m:
                try:
                    cases = int(m.group(0).replace(",", ""))
                except ValueError:
                    cases = None

        # Include explicit feed metadata and description in one conservative evidence
        # string.  Blend composition in this text can override a generic single-
        # varietal category supplied by the provider.
        combined = " ".join(x for x in [raw_name, provider_varietal, appellation, description] if x)
        feed_composition = _extract_feed_composition(node, combined)
        varietal = _prefer_explicit_blend(feed_composition or provider_varietal, canonical_name, combined)
        region, subregion, geography_conflict = _extract_region(combined)
        if not region and appellation:
            region = appellation
        graph = _infer_graph_category(varietal, canonical_name, combined)
        varietal, graph, abv = _apply_vinoshipper_record_override(
            producer_id=producer_id, wine=canonical_name, vintage=vintage,
            varietal=varietal, graph_category=graph, alcohol_pct=abv,
        )
        general = _infer_general_category(graph, varietal, canonical_name)
        estate_flag = bool(_json_bool(node, "estate", "estateGrown", "isEstate") or False)
        single_flag = _json_bool(node, "singleVineyard", "isSingleVineyard")
        single_vineyard = bool(single_flag) if single_flag is not None else _infer_single_vineyard(canonical_name, combined)
        tier = _infer_tier(canonical_name, combined, estate_flag, cases)

        member_only = _json_bool(node, "membersOnly", "memberOnly", "clubOnly", "clubMembersOnly")
        sold_out = _json_bool(node, "soldOut", "isSoldOut")
        archived = _json_bool(node, "archived", "isArchived")
        if member_only:
            availability = "Member exclusive"
        elif sold_out:
            availability = "Sold out"
        elif archived:
            availability = "Archived"
        else:
            availability = _availability_status(combined) or "Available"

        product_id = _json_text(_json_lookup(node, "id", "productId", "wineId"))
        product_url = _json_text(_json_lookup(node, "url", "productUrl", "webUrl", "link"))
        if product_url:
            product_url = urljoin(shop_url, product_url)
        elif product_id:
            product_url = f"https://vinoshipper.com/api/v3/feeds/vs/{producer_id}/products/{product_id}"
        else:
            product_url = shop_url

        confidence = (
            "High"
            if (regular is not None and bool(vintage) and bool(varietal) and graph != "Other" and not geography_conflict)
            else "Moderate"
        )
        results.append(WineOffer(
            wine=canonical_name,
            vintage=vintage,
            regular_price=regular,
            sale_price=sale,
            club_price=club,
            currency="USD",
            product_url=product_url,
            evidence=(description or combined)[:520],
            extraction_method="VinoShipper Product Feed",
            confidence=confidence,
            varietal=varietal,
            graph_category=graph,
            general_category=general,
            region=region,
            subregion=subregion,
            alcohol_pct=abv,
            cases_produced=cases,
            estate=estate_flag,
            single_vineyard=single_vineyard,
            product_tier=tier,
            availability_status=availability,
            provider_id=str(producer_id),
        ))
    return finalize_vinoshipper_offers(results, producer_id)


def fetch_vinoshipper_product_feed(producer_id: str, shop_url: str) -> list[WineOffer]:
    pid = str(producer_id or "").strip()
    if not re.fullmatch(r"\d+", pid):
        raise CatalogScanError("Enter a numeric VinoShipper producer ID.")
    endpoint = f"https://vinoshipper.com/api/v3/feeds/vs/{pid}/products"
    payload = _fetch_public_json(endpoint)
    offers = extract_vinoshipper_feed_offers(payload, producer_id=pid, shop_url=shop_url)
    offers = finalize_vinoshipper_offers(offers, pid)
    if not offers:
        raise CatalogScanError("VinoShipper's product feed returned no dependable priced wine records.")
    return offers

def _is_public_ip(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise CatalogScanError("Enter a public winery shop/catalog URL first.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CatalogScanError("Use a complete public http:// or https:// URL.")
    host = parsed.hostname.casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise CatalogScanError("Local/private network URLs are not supported.")
    try:
        infos = socket.getaddrinfo(
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise CatalogScanError(f"Could not resolve the hostname: {exc}") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or any(not _is_public_ip(addr) for addr in addresses):
        raise CatalogScanError("The URL resolves to a private/reserved network address.")
    return url


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.5,*/*;q=0.1",
        "Accept-Language": "en-US,en;q=0.8",
        "Connection": "close",
    }


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _site_key(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _get_robots(url: str) -> tuple[RobotFileParser | None, str]:
    origin = _origin(url)
    cache_key = origin.casefold()
    now = time.time()
    cached = _ROBOTS_CACHE.get(cache_key)
    if cached and now - cached[0] < ROBOTS_TTL_SECONDS:
        return cached[1], f"cached: {cached[2]}"

    robots_url = urljoin(origin + "/", "robots.txt")
    try:
        response = requests.get(
            robots_url,
            headers=_request_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise CatalogScanError(
            f"Could not verify robots.txt safely ({exc}); scan stopped."
        ) from exc

    if response.status_code == 404:
        _ROBOTS_CACHE[cache_key] = (now, None, "robots.txt not published (404)")
        return None, "robots.txt not published (404)"
    if response.status_code in {401, 403}:
        raise CatalogScanError("The site denied access to robots.txt; scan stopped.")
    if response.status_code >= 400:
        raise CatalogScanError(
            f"robots.txt returned HTTP {response.status_code}; scan stopped rather than guessing permission."
        )

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    status = "robots.txt checked"
    _ROBOTS_CACHE[cache_key] = (now, parser, status)
    return parser, status


def _read_response(response: requests.Response) -> tuple[str, int, str]:
    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().casefold()
    if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
        raise CatalogScanError(f"The URL returned {content_type!r}, not HTML/text.")

    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > MAX_HTML_BYTES:
                raise CatalogScanError("The page is larger than the collector's 2 MB safety limit.")
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_HTML_BYTES:
            raise CatalogScanError("The page exceeded the 2 MB safety limit while downloading.")
        chunks.append(chunk)
    raw = b"".join(chunks)
    encoding = response.encoding or "utf-8"
    try:
        text = raw.decode(encoding, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    return text, total, content_type or "text/html"


def fetch_catalog_page(url: str) -> CatalogFetch:
    """Fetch only the exact requested page (plus robots.txt if not cached).

    The process keeps a conservative in-memory 24-hour page cache. Repeated scans
    of the exact same URL during the same app process can reuse cached HTML with
    zero additional page request. If a cached page is stale and the server supplied
    ETag/Last-Modified, the next request is conditional so an unchanged page can
    return HTTP 304 without retransmitting the full HTML.
    """
    requested = validate_public_url(url)
    robots, robots_status = _get_robots(requested)
    if robots is not None and not robots.can_fetch(USER_AGENT, requested):
        raise CatalogScanError("robots.txt disallows this page for the configured research user agent.")

    now = time.time()
    cache_key = requested.casefold()
    cached = _PAGE_CACHE.get(cache_key)
    if cached and now - cached[0] < PAGE_CACHE_TTL_SECONDS:
        _, html, content_type, _, _ = cached
        return CatalogFetch(
            requested_url=requested,
            final_url=requested,
            status_code=200,
            content_type=content_type,
            html=html,
            bytes_read=len(html.encode("utf-8", errors="ignore")),
            robots_status=robots_status,
            request_note="24-hour page cache hit (no page request)",
        )

    current = requested
    original_site = _site_key(requested)
    for redirect_number in range(MAX_REDIRECTS + 1):
        validate_public_url(current)
        headers = _request_headers()
        if cached and current.casefold() == requested.casefold():
            etag = cached[3]
            last_modified = cached[4]
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified
        try:
            response = requests.get(
                current,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise CatalogScanError(f"Catalog request failed: {exc}") from exc

        if response.status_code in {301, 302, 303, 307, 308}:
            if redirect_number >= MAX_REDIRECTS:
                raise CatalogScanError("The URL redirected too many times.")
            location = response.headers.get("Location")
            if not location:
                raise CatalogScanError("Redirect had no destination.")
            redirected = urljoin(current, location)
            validate_public_url(redirected)
            if _site_key(redirected) != original_site:
                raise CatalogScanError("The page redirected to a different site; scan stopped.")
            current = redirected
            continue

        if response.status_code == 304 and cached:
            _, html, content_type, etag, last_modified = cached
            _PAGE_CACHE[cache_key] = (now, html, content_type, etag, last_modified)
            return CatalogFetch(
                requested_url=requested,
                final_url=current,
                status_code=304,
                content_type=content_type,
                html=html,
                bytes_read=0,
                robots_status=robots_status,
                request_note="conditional request: not modified (cached HTML reused)",
            )

        if response.status_code in {401, 403}:
            raise CatalogScanError(
                f"The site returned HTTP {response.status_code}; the collector will not bypass it."
            )
        if response.status_code == 429:
            raise CatalogScanError("The site returned HTTP 429; the collector will not retry automatically.")
        if response.status_code >= 400:
            raise CatalogScanError(f"The catalog page returned HTTP {response.status_code}.")

        html, bytes_read, content_type = _read_response(response)
        etag = response.headers.get("ETag") or ""
        last_modified = response.headers.get("Last-Modified") or ""
        _PAGE_CACHE[cache_key] = (now, html, content_type, etag, last_modified)
        return CatalogFetch(
            requested_url=requested,
            final_url=current,
            status_code=response.status_code,
            content_type=content_type,
            html=html,
            bytes_read=bytes_read,
            robots_status=robots_status,
            request_note="network fetch",
        )

    raise CatalogScanError("The catalog page could not be fetched.")

def _iter_json_nodes(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_json_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_json_nodes(child)


def _types(node: dict[str, Any]) -> set[str]:
    value = node.get("@type")
    if isinstance(value, str):
        return {value.casefold()}
    if isinstance(value, list):
        return {str(v).casefold() for v in value}
    return set()


def _clean_name(name: Any) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip(" -|\t\r\n")
    return text[:180]


def _vintage_from_name(name: str) -> str:
    match = VINTAGE_RE.search(name)
    if match:
        return match.group(1)
    if NV_RE.search(name):
        return "NV"
    return ""


def _coerce_price(value: Any) -> float | None:
    if value in (None, ""):
        return None
    match = re.search(r"[0-9]+(?:\.[0-9]{1,2})?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        price = float(match.group(0))
    except ValueError:
        return None
    if price <= 0 or price > 5000:
        return None
    return round(price, 2)


def _offer_prices(offers: Any) -> tuple[float | None, float | None, float | None, str]:
    regular = sale = club = None
    currency = "USD"
    candidates = offers if isinstance(offers, list) else [offers]
    for offer in candidates:
        if not isinstance(offer, dict):
            continue
        currency = str(offer.get("priceCurrency") or currency)
        price = _coerce_price(offer.get("price") or offer.get("lowPrice"))
        if price is None:
            continue
        label = " ".join(
            str(offer.get(k) or "") for k in ("name", "description", "category", "priceSpecification")
        ).casefold()
        if any(word in label for word in ("club", "member", "society")):
            club = price if club is None else min(club, price)
        elif any(word in label for word in ("sale", "discount", "clearance")):
            sale = price if sale is None else min(sale, price)
        elif regular is None:
            regular = price
    return regular, sale, club, currency


def _extract_jsonld(soup: BeautifulSoup, base_url: str) -> list[WineOffer]:
    offers: list[WineOffer] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for node in _iter_json_nodes(data):
            if "product" not in _types(node):
                continue
            name = _clean_name(node.get("name"))
            if not name:
                continue
            regular, sale, club, currency = _offer_prices(node.get("offers"))
            if regular is None and sale is None and club is None:
                continue
            product_url = urljoin(base_url, str(node.get("url") or "")) or base_url
            evidence = _clean_name(node.get("description"))[:360]
            offers.append(
                WineOffer(
                    wine=name,
                    vintage=_vintage_from_name(name),
                    regular_price=regular,
                    sale_price=sale,
                    club_price=club,
                    currency=currency,
                    product_url=product_url,
                    evidence=evidence or "JSON-LD Product",
                    extraction_method="JSON-LD",
                    confidence="High",
                )
            )
    return offers


def _classify_prices(text: str) -> tuple[float | None, float | None, float | None]:
    regular = sale = club = None
    matches = list(PRICE_RE.finditer(text))
    for match in matches:
        label = (match.group(1) or "").casefold()
        # Product pages often put words such as "member pricing" several words
        # before the dollar value. Read a small amount of surrounding text so
        # that price type is not determined only by the token immediately
        # adjacent to the price.
        prefix = text[max(0, match.start() - 90):match.start()].casefold()
        # Only carry price-type words from the current sentence/clause so a
        # member-price sentence does not accidentally label the next visible
        # retail price as a member price too.
        local_prefix = re.split(r"[.!?;]\s*", prefix)[-1]
        context = f"{label} {local_prefix}"
        price = _coerce_price(match.group(2))
        if price is None:
            continue
        if any(word in context for word in ("club", "member", "membership", "wine society", "preferred pricing")):
            club = price if club is None else min(club, price)
        elif any(word in context for word in ("sale", "discount", "clearance", "special price", "promotion")):
            sale = price if sale is None else min(sale, price)
        elif regular is None:
            regular = price
        elif price < regular and sale is None:
            # Multiple unlabeled prices often means current/sale + struck list price.
            sale = price
        elif price > regular:
            regular, sale = price, regular if sale is None else sale
    return regular, sale, club


def _candidate_parent(anchor: Tag) -> Tag | None:
    # Use the *smallest* nearby container that contains a price so one product
    # card cannot absorb prices from sibling products higher in the DOM tree.
    node: Tag | None = anchor
    for _ in range(5):
        if node is None or not isinstance(node, Tag):
            break
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text) > 1200:
            break
        if PRICE_RE.search(text):
            return node
        node = node.parent if isinstance(node.parent, Tag) else None
    return None


def _extract_html_cards(soup: BeautifulSoup, base_url: str) -> list[WineOffer]:
    results: list[WineOffer] = []
    for anchor in soup.find_all("a", href=True):
        name = _clean_name(anchor.get_text(" ", strip=True))
        href = str(anchor.get("href") or "").strip()
        if not name or len(name) < 3 or len(name) > 160:
            continue
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        parent = _candidate_parent(anchor)
        if parent is None:
            continue
        text = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))
        if not PRICE_RE.search(text):
            continue
        regular, sale, club = _classify_prices(text)
        if regular is None and sale is None and club is None:
            continue
        url = urljoin(base_url, href)
        if _site_key(url) != _site_key(base_url):
            continue
        # Filter generic navigation/cart anchors by requiring wine-like context.
        context_key = _ascii_key(text)
        name_key = _ascii_key(name)
        generic = {"shop", "wines", "wine", "buy", "add to cart", "learn more", "view", "details"}
        if name_key in generic:
            continue
        wine_tokens = ("wine", "cabernet", "chardonnay", "pinot", "syrah", "grenache", "sauvignon", "riesling", "rose", "zinfandel", "viognier", "merlot", "blend", "bottle", "vintage", "blanc", "rouge", "barbera", "sangiovese", "tempranillo", "vermentino", "albarino", "albariño")
        class_text = " ".join(str(x) for x in (parent.get("class") or [])) + " " + str(parent.get("id") or "")
        looks_like_product_container = any(tok in class_text.casefold() for tok in ("product", "wine", "shop", "item", "card"))
        if not any(token in context_key for token in wine_tokens):
            # Still allow product-card links or names with a visible vintage;
            # final rows remain reviewable/editable before export.
            if not VINTAGE_RE.search(text) and not looks_like_product_container:
                continue
        results.append(
            WineOffer(
                wine=name,
                vintage=_vintage_from_name(name) or _vintage_from_name(text),
                regular_price=regular,
                sale_price=sale,
                club_price=club,
                currency="USD",
                product_url=url,
                evidence=text[:420],
                extraction_method="HTML card",
                confidence="Moderate",
            )
        )
    return results



_BLOCK_WINE_HINTS = (
    "wine", "cabernet", "chardonnay", "pinot", "syrah", "grenache", "sauvignon",
    "riesling", "rose", "rosé", "zinfandel", "viognier", "merlot", "blend",
    "blanc", "rouge", "barbera", "sangiovese", "tempranillo", "vermentino",
    "albarino", "albariño", "malbec", "tannat", "petite sirah", "petit verdot",
    "roussanne", "marsanne", "mourvedre", "mourvèdre", "vintage", "bottle",
)
_BLOCK_NON_WINE_HINTS = (
    "gift card", "shipping", "merch", "shirt", "hoodie", "hat", "glassware",
    "reservation", "visit us", "event ticket", "membership signup",
)


def _same_site_product_url(container: Tag, heading: Tag | None, base_url: str) -> str:
    """Return a same-site product URL when the static block exposes one.

    Catalogs such as marketplace storefronts sometimes render all useful product
    facts in one static list without a conventional product link. In that case
    the catalog URL itself is retained as provenance instead of inventing a URL.
    """
    anchors: list[Tag] = []
    if heading is not None:
        if heading.name == "a" and heading.get("href"):
            anchors.append(heading)
        parent_link = heading.find_parent("a", href=True)
        if isinstance(parent_link, Tag):
            anchors.append(parent_link)
    anchors.extend(container.find_all("a", href=True, limit=8))
    for anchor in anchors:
        raw = str(anchor.get("href") or "").strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, raw)
        if _site_key(url) != _site_key(base_url):
            continue
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl()
    return base_url


def _heading_looks_like_product(title: str, context: str) -> bool:
    key = _ascii_key(f"{title} {context}")
    if any(token in key for token in _BLOCK_NON_WINE_HINTS):
        return False
    has_vintage = bool(VINTAGE_RE.search(title) or NV_RE.search(title))
    has_wine_word = any(token in key for token in _BLOCK_WINE_HINTS)
    has_abv = bool(re.search(r"\b\d{1,2}(?:\.\d+)?\s*%\s*(?:ABV|alcohol)?\b", context, re.I))
    # A visible vintage plus either wine vocabulary or ABV is a strong generic
    # product-card signal without relying on a winery/platform-specific class.
    return (has_vintage and (has_wine_word or has_abv)) or (has_wine_word and has_abv)


def _nearest_repeating_product_block(heading: Tag) -> Tag | None:
    """Find the smallest ancestor that looks like one complete product block."""
    node: Tag | None = heading
    best: Tag | None = None
    for _ in range(8):
        if node is None or not isinstance(node, Tag):
            break
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text) > 2600:
            break
        if PRICE_RE.search(text):
            # Avoid swallowing a large grid containing many neighboring products.
            headings = [
                _clean_name(h.get_text(" ", strip=True))
                for h in node.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
            ]
            productish = [h for h in headings if _heading_looks_like_product(h, text)]
            if len(productish) <= 2:
                best = node
                # Smallest qualifying ancestor is normally the card/list item.
                break
        node = node.parent if isinstance(node.parent, Tag) else None
    return best


def _extract_repeating_product_blocks(soup: BeautifulSoup, base_url: str) -> list[WineOffer]:
    """Extract static repeating product blocks without requiring product links.

    This is intentionally structure-agnostic. It looks for a product-like heading
    plus price within the smallest nearby HTML block, then enriches the row from
    the text already present in that block. It is useful for marketplace/catalog
    pages that expose the entire wine list in static HTML but do not use the
    anchor/card patterns handled by ``_extract_html_cards``.
    """
    results: list[WineOffer] = []
    seen_blocks: set[int] = set()

    for heading in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        title = _clean_name(heading.get_text(" ", strip=True))
        if not title or len(title) < 3 or len(title) > 180:
            continue
        block = _nearest_repeating_product_block(heading)
        if block is None:
            continue
        block_id = id(block)
        if block_id in seen_blocks:
            continue
        text = re.sub(r"\s+", " ", block.get_text(" ", strip=True))
        if not _heading_looks_like_product(title, text):
            continue
        if any(token in _ascii_key(text) for token in _BLOCK_NON_WINE_HINTS):
            continue

        regular, sale, club = _classify_prices(text)
        if regular is None and sale is None and club is None:
            continue
        vintage = _vintage_from_name(title) or _vintage_from_name(text[:700])
        if not vintage and not NV_RE.search(text[:700]):
            # For catalog-scale extraction, requiring a visible vintage/NV keeps
            # generic non-wine merchandise cards from entering the review table.
            continue
        canonical_title = _canonical_wine_name(title, vintage)
        if not canonical_title:
            continue

        metadata = _extract_product_metadata(title, text)
        geography_conflict = bool(metadata.pop("_geography_conflict", False))
        product_url = _same_site_product_url(block, heading, base_url)
        high_signal = bool(vintage and _extract_abv(text) is not None)
        confidence = "High" if high_signal and not geography_conflict else "Moderate"
        results.append(
            WineOffer(
                wine=canonical_title,
                vintage=vintage or "NV",
                regular_price=regular,
                sale_price=sale,
                club_price=club,
                currency="USD",
                product_url=product_url,
                evidence=text[:520],
                extraction_method="Repeating HTML product block",
                confidence=confidence,
                **metadata,
            )
        )
        seen_blocks.add(block_id)

    # Some static catalogs use semantic article/li cards but no heading tags.
    # Run a conservative second pass only over product-ish containers.
    for container in soup.find_all(["article", "li", "section", "div"]):
        class_text = " ".join(str(x) for x in (container.get("class") or [])) + " " + str(container.get("id") or "")
        if not any(tok in class_text.casefold() for tok in ("product", "wine", "item", "card")):
            continue
        if id(container) in seen_blocks:
            continue
        text = re.sub(r"\s+", " ", container.get_text(" ", strip=True))
        if not (30 <= len(text) <= 1800) or not PRICE_RE.search(text):
            continue
        if any(token in _ascii_key(text) for token in _BLOCK_NON_WINE_HINTS):
            continue
        title_tag = container.find(["h1", "h2", "h3", "h4", "h5", "h6", "strong"])
        title = _clean_name(title_tag.get_text(" ", strip=True)) if isinstance(title_tag, Tag) else ""
        if not title or not _heading_looks_like_product(title, text):
            continue
        regular, sale, club = _classify_prices(text)
        if regular is None and sale is None and club is None:
            continue
        vintage = _vintage_from_name(title) or _vintage_from_name(text[:700])
        if not vintage and not NV_RE.search(text[:700]):
            continue
        metadata = _extract_product_metadata(title, text)
        geography_conflict = bool(metadata.pop("_geography_conflict", False))
        results.append(
            WineOffer(
                wine=_canonical_wine_name(title, vintage),
                vintage=vintage or "NV",
                regular_price=regular,
                sale_price=sale,
                club_price=club,
                currency="USD",
                product_url=_same_site_product_url(container, title_tag if isinstance(title_tag, Tag) else None, base_url),
                evidence=text[:520],
                extraction_method="Repeating HTML product block",
                confidence=("Moderate" if geography_conflict else ("High" if _extract_abv(text) is not None else "Moderate")),
                **metadata,
            )
        )
        seen_blocks.add(id(container))

    return results


_PRODUCT_PATH_HINTS = ("/shop/", "/product/", "/products/", "/wine/", "/wines/")
_WINE_CONTEXT_HINTS = (
    "wine", "cabernet", "chardonnay", "pinot", "syrah", "grenache", "sauvignon",
    "riesling", "rose", "rosé", "zinfandel", "viognier", "merlot", "blend",
    "blanc", "rouge", "barbera", "sangiovese", "tempranillo", "vermentino",
    "albarino", "albariño", "vineyard", "cuvee", "cuvée", "vintage", "napa valley",
    "paso robles", "sonoma", "carneros", "mountain",
)
_NON_WINE_HINTS = (
    "shirt", "sweatshirt", "hoodie", "hat", "tote", "gift card", "merch", "glassware",
    "corkscrew", "shipping", "login", "account", "visit", "reservation",
)
_SECTION_HEADINGS = {
    "shop", "wines", "wine", "blends", "single vineyard", "zero zero", "zero-zero",
    "merch", "merchandise", "gift cards", "gift card",
}


def _nearby_link_container(anchor: Tag) -> Tag:
    """Return a small ancestor useful for labeling a discovered product link."""
    chosen = anchor
    node: Tag | None = anchor
    for _ in range(5):
        if node is None or not isinstance(node, Tag):
            break
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        links = node.find_all("a", href=True)
        if len(text) <= 850 and len(links) <= 6:
            chosen = node
            headings = node.find_all(["h1", "h2", "h3", "h4", "h5"])
            if len(headings) >= 2:
                break
        node = node.parent if isinstance(node.parent, Tag) else None
    return chosen


def _product_link_label(anchor: Tag, container: Tag) -> str:
    anchor_text = _clean_name(anchor.get_text(" ", strip=True))
    headings = []
    for heading in container.find_all(["h1", "h2", "h3", "h4", "h5"]):
        text = _clean_name(heading.get_text(" ", strip=True))
        if not text:
            continue
        key = _ascii_key(text)
        if key in _SECTION_HEADINGS:
            continue
        if key == _ascii_key(anchor_text):
            continue
        headings.append(text)

    # Usually the first non-section heading in a product card is the wine name;
    # the linked heading often contributes the vintage/release number.
    base = headings[0] if headings else ""
    if base and anchor_text:
        if _ascii_key(anchor_text) not in _ascii_key(base):
            return _clean_name(f"{base} {anchor_text}")
        return base
    return base or anchor_text


def discover_product_links(html: str, base_url: str) -> list[ProductLink]:
    """Discover same-site likely wine product links without fetching them.

    Discovery is performed solely against the already-downloaded catalog HTML.
    No link returned here is opened until the user explicitly selects it.
    """
    soup = BeautifulSoup(html, "html.parser")
    base = urlparse(base_url)
    base_site = _site_key(base_url)
    base_path = (base.path or "/").rstrip("/") or "/"
    found: dict[str, ProductLink] = {}

    for anchor in soup.find_all("a", href=True):
        raw_href = str(anchor.get("href") or "").strip()
        if not raw_href or raw_href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        url = urljoin(base_url, raw_href)
        parsed = urlparse(url)
        if _site_key(url) != base_site:
            continue
        # Fragments are browser-side only. Normalize them away for fetches.
        normalized_url = parsed._replace(fragment="").geturl()
        parsed_norm = urlparse(normalized_url)
        path = (parsed_norm.path or "/").rstrip("/") or "/"
        if path == base_path:
            continue

        container = _nearby_link_container(anchor)
        context = re.sub(r"\s+", " ", container.get_text(" ", strip=True))[:700]
        label = _product_link_label(anchor, container)
        combined_key = _ascii_key(f"{label} {context} {path}")
        if not label:
            # Human-readable fallback from the URL slug.
            slug = path.rsplit("/", 1)[-1].replace("-", " ")
            label = _clean_name(slug.title())

        if any(token in combined_key for token in _NON_WINE_HINTS):
            continue

        path_hint = any(hint in (path.casefold() + "/") for hint in _PRODUCT_PATH_HINTS)
        has_vintage = bool(VINTAGE_RE.search(context) or NV_RE.search(context))
        has_wine_context = any(token in combined_key for token in _WINE_CONTEXT_HINTS)
        class_text = " ".join(str(x) for x in (container.get("class") or [])) + " " + str(container.get("id") or "")
        productish_class = any(tok in class_text.casefold() for tok in ("product", "wine", "item", "card"))

        if not path_hint and not (has_vintage and (has_wine_context or productish_class)):
            continue
        if not has_vintage and not has_wine_context and not productish_class:
            continue

        confidence = "High" if path_hint and (has_vintage or has_wine_context) else "Moderate"
        key = normalized_url.casefold()
        candidate = ProductLink(
            label=label[:180],
            url=normalized_url,
            context=context,
            confidence=confidence,
        )
        current = found.get(key)
        if current is None or (current.confidence != "High" and candidate.confidence == "High"):
            found[key] = candidate

    return sorted(found.values(), key=lambda item: _ascii_key(item.label))




def _first_match(patterns: list[str], text: str, flags: int = re.I) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean_name(match.group(1))
    return ""


def _extract_region(text: str) -> tuple[str, str, bool]:
    """Extract broad AVA + one unambiguous subregion.

    Returns (region, subregion, geography_conflict).  The conflict flag is set
    when the page contains evidence for two or more distinct narrower AVAs /
    districts.  In that case we preserve the broad region but intentionally
    leave subregion blank rather than choosing one arbitrarily.
    """
    known = [
        "Napa Valley", "Paso Robles", "San Luis Obispo Coast", "Sonoma Coast",
        "Russian River Valley", "Carneros", "Oak Knoll District", "Howell Mountain",
        "Atlas Peak", "Mount Veeder", "Stags Leap District", "Rutherford", "Oakville",
        "Yountville", "Calistoga", "St. Helena", "Adelaida District", "Willow Creek District",
        "Templeton Gap District", "Santa Margarita Ranch", "York Mountain",
        "El Pomar District", "Geneseo District", "Creston District", "Estrella District",
        "San Juan Creek District", "San Antonio Valley",
    ]
    broad_names = {
        "Napa Valley", "Paso Robles", "San Luis Obispo Coast", "Sonoma Coast",
        "Carneros", "Russian River Valley",
    }

    # Collect known AVA/district mentions first instead of returning immediately
    # from a single "Appellation:" field.  Product pages sometimes show one
    # technical-sheet appellation while the sourcing prose names additional
    # districts; those multi-area wines should not be assigned to just one.
    mentions: list[tuple[int, str]] = []
    for name in known:
        for match in re.finditer(rf"\b{re.escape(name)}\b", text, re.I):
            mentions.append((match.start(), name))
    mentions.sort(key=lambda item: item[0])

    ordered_names: list[str] = []
    seen_names: set[str] = set()
    for _, name in mentions:
        key = _ascii_key(name)
        if key not in seen_names:
            seen_names.add(key)
            ordered_names.append(name)

    explicit_patterns = [
        r"(?:appellation|ava|region)\s*[:\-]?\s*([A-Z][A-Za-zÀ-ÿ0-9'&.\- ]{2,60}?)(?=\s{2,}|\s(?:technical|alcohol|harvest|cases|vineyard|$))",
        r"\b([A-Z][A-Za-zÀ-ÿ'&.\- ]{2,50}\sAVA)\b",
    ]
    explicit = _first_match(explicit_patterns, text)
    if explicit:
        explicit = re.sub(r"\s+AVA$", "", explicit, flags=re.I).strip()
        # If the explicit field names one of our known locations, ensure it is
        # represented even when formatting prevented the generic scan above.
        for name in known:
            if _ascii_key(explicit) == _ascii_key(name):
                if not any(_ascii_key(existing) == _ascii_key(name) for existing in ordered_names):
                    ordered_names.insert(0, name)
                explicit = name
                break

    broad_hits = [name for name in ordered_names if name in broad_names]
    narrow_hits = [name for name in ordered_names if name not in broad_names]
    # Preserve order while de-duplicating.
    broad_hits = list(dict.fromkeys(broad_hits))
    narrow_hits = list(dict.fromkeys(narrow_hits))

    broad = broad_hits[0] if broad_hits else ""

    # Two or more distinct narrower AVAs/districts means the finished wine is
    # multi-area for our single-subregion schema.  Keep the broad AVA only.
    if len(narrow_hits) >= 2:
        return broad or (explicit if explicit and explicit in broad_names else ""), "", True

    if broad:
        return broad, (narrow_hits[0] if len(narrow_hits) == 1 else ""), False

    # No recognized broad AVA.  If a single known narrower area is the only
    # geography evidence, keep it as the region rather than inventing a parent.
    if len(narrow_hits) == 1:
        return narrow_hits[0], "", False

    # Finally preserve an explicit free-text appellation/region when it was not
    # in the known list.  This keeps the extractor useful beyond our initial CA
    # test set without guessing a subregion hierarchy.
    if explicit:
        return explicit, "", False

    return "", "", False


def _extract_abv(text: str) -> float | None:
    patterns = [
        r"(?:alcohol|abv)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9]{1,3})?)\s*%?",
        r"([0-9]{1,2}(?:\.[0-9]{1,3})?)\s*%\s*(?:alcohol|abv)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                value = float(m.group(1))
                if 5 <= value <= 25:
                    return value
            except ValueError:
                pass
    return None


def _extract_cases(text: str) -> int | None:
    patterns = [
        r"cases?\s+produced\s*[:\-]?\s*([0-9][0-9,]*)",
        r"production\s*[:\-]?\s*([0-9][0-9,]*)\s*cases?",
        r"([0-9][0-9,]*)\s*cases?\s+(?:produced|made)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            try:
                value = int(m.group(1).replace(",", ""))
                if 0 < value < 5_000_000:
                    return value
            except ValueError:
                pass
    return None


def _extract_varietal(title: str, text: str) -> str:
    grape_names = [
        "Cabernet Sauvignon", "Cabernet Franc", "Chardonnay", "Pinot Noir", "Merlot",
        "Sauvignon Blanc", "Syrah", "Grenache", "Mourvèdre", "Mourvedre", "Zinfandel",
        "Petite Sirah", "Viognier", "Riesling", "Barbera", "Sangiovese", "Tempranillo",
        "Vermentino", "Albariño", "Albarino", "Grenache Blanc", "Picpoul Blanc",
        "Roussanne", "Marsanne", "Muscat Canelli", "Malbec", "Petit Verdot",
        "Sémillon", "Semillon", "Chenin Blanc", "Pinot Gris", "Pinot Grigio",
        "Tannat", "Petite Verdot",
    ]

    def grapes_in(fragment: str) -> list[str]:
        found: list[str] = []
        # Longest-first prevents Grenache from masking Grenache Blanc.
        for grape in sorted(grape_names, key=len, reverse=True):
            if re.search(rf"\b{re.escape(grape)}\b", fragment, re.I):
                key = _ascii_key(grape)
                if not any(_ascii_key(existing) == key for existing in found):
                    found.append(grape)
        return found

    # Prefer explicit percentage blends when visible.
    pct_pattern = re.compile(
        r"((?:\d{1,3}%\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{2,35})(?:\s*(?:,|/|\+|and)\s*\d{1,3}%\s+[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'\- ]{2,35}){0,8})",
        re.I,
    )
    matches = pct_pattern.findall(text)
    if matches:
        candidate = max(matches, key=len)
        candidate = re.sub(r"\s+", " ", candidate).strip(" ,;.-")
        if (
            not any(word in candidate.casefold() for word in ["oak", "barrel", "french", "neutral"])
            and grapes_in(candidate)
        ):
            return candidate

    explicit = _first_match([
        r"(?:varietal|variety|composition)\s*[:\-]?\s*([^.;]{3,180})",
        r"(?:made from|composed of)\s+([^.;]{3,180})",
    ], text)
    if explicit and grapes_in(explicit):
        return explicit

    # Winery prose often states blends narratively rather than in a technical table, e.g.
    # "Blanc is a blend of Sémillon and Sauvignon Blanc from ...".  Keep only the
    # grape identities and discard vineyard/source prose that follows them.
    blend_sentences = re.findall(r"[^.!?]{0,120}\bblend\s+(?:of\s+)?[^.!?]{3,220}", text, re.I)
    for sentence in blend_sentences:
        grapes = grapes_in(sentence)
        if len(grapes) >= 2:
            return ", ".join(grapes)

    title_hits = grapes_in(title)
    if title_hits:
        return title_hits[0]
    return ""


def _infer_graph_category(varietal: str, title: str, text: str) -> str:
    blob = f"{varietal} {title} {text[:1200]}".casefold()
    if any(k in blob for k in ["rosé", "rose"]):
        return "Rosé"
    if any(k in blob for k in ["sparkling", "brut", "méthode traditionnelle", "methode traditionnelle"]):
        return "Sparkling"
    bordeaux = ["cabernet sauvignon", "cabernet franc", "merlot", "malbec", "petit verdot"]
    rhone_red = ["grenache", "syrah", "mourv", "counoise"]
    rhone_white = ["grenache blanc", "roussanne", "marsanne", "picpoul", "viognier", "clairette"]
    if sum(term in varietal.casefold() for term in bordeaux) >= 2:
        return "Bordeaux Blend"
    if sum(term in varietal.casefold() for term in rhone_white) >= 2:
        return "White Blend"
    if sum(term in varietal.casefold() for term in rhone_red) >= 2:
        return "Rhône Blend"
    # Product names frequently carry style information even when the provider's
    # single-varietal field is blank or overly broad.
    title_key = _ascii_key(title)
    if any(term in title_key for term in ["le rhone", "rhone blend", "rhone red", "rhone"]):
        return "Rhône Blend"
    if "white blend" in blob or "blanc" in title.casefold():
        return "White Blend"
    if "red blend" in blob or "proprietary red" in blob or ("blend" in title.casefold() and _infer_general_category("", varietal, title) == "Red"):
        return "Red Blend"
    singles = [
        "Cabernet Sauvignon", "Cabernet Franc", "Chardonnay", "Pinot Noir", "Merlot",
        "Sauvignon Blanc", "Syrah", "Grenache", "Zinfandel", "Petite Sirah", "Viognier",
        "Riesling", "Barbera", "Sangiovese", "Tempranillo", "Vermentino", "Muscat Canelli",
        "Malbec", "Petit Verdot", "Tannat", "Grenache Blanc", "Albariño", "Albarino",
    ]
    for grape in singles:
        if grape.casefold() in blob:
            return grape
    return "Other"


def _infer_general_category(graph: str, varietal: str, title: str) -> str:
    blob = f"{graph} {varietal} {title}".casefold()
    if any(k in blob for k in ["rosé", "rose"]):
        return "Rosé"
    if any(k in blob for k in ["sparkling", "brut"]):
        return "Sparkling"
    whites = [
        "white blend", "blanc", "chardonnay", "sauvignon blanc", "viognier", "grenache blanc",
        "picpoul", "roussanne", "marsanne", "riesling", "vermentino", "albariño", "albarino",
        "muscat", "pinot gris", "chenin blanc", "semillon", "sémillon",
    ]
    return "White" if any(k in blob for k in whites) else "Red"


def _infer_tier(title: str, text: str, estate: bool, cases: int | None) -> str:
    blob = f"{title} {text[:1600]}".casefold()
    if any(k in blob for k in ["flagship", "icon wine", "iconic", "benchmark"]):
        return "Flagship"
    if "reserve" in blob:
        return "Reserve"
    if estate:
        return "Estate"
    if any(k in blob for k in ["limited release", "limited-release", "small production", "small-production", "member exclusive", "allocation only"]):
        return "Limited"
    if cases is not None and cases <= 250:
        return "Limited"
    return "Core"


def _availability_status(text: str) -> str:
    blob = text.casefold()
    if any(k in blob for k in ["sold out", "out of stock"]):
        return "Sold out"
    if any(k in blob for k in ["member exclusive", "members only", "member-only"]):
        return "Member exclusive"
    if any(k in blob for k in ["waitlist", "join waitlist"]):
        return "Waitlist"
    if any(k in blob for k in ["add to cart", "buy", "purchase", "in stock"]):
        return "Available"
    return ""


def _infer_single_vineyard(title: str, text: str) -> bool:
    """Require affirmative single-vineyard evidence and let multi-source wording win."""
    relevant = f"{title} {text[:5000]}"
    negative_patterns = [
        r"\bselect(?:ed)?\s+vineyards\b",
        r"\bmultiple\s+vineyards\b",
        r"\bseveral\s+vineyards\b",
        r"\bvarious\s+vineyards\b",
        r"\bblend(?:ed)?\s+(?:from|of)\s+[^.]{0,140}\bvineyards\b",
        r"\bfrom\s+[^.]{0,160}\bvineyards\b",
        r"\bsourced\s+from\s+[^.]{0,160}\bvineyards\b",
        r"\bvineyards\s+(?:in|across|throughout)\b",
        r"\bboth\s+[^.]{0,120}\b(?:vineyard|vineyards)\b",
    ]
    if any(re.search(pattern, relevant, re.I) for pattern in negative_patterns):
        return False
    return bool(
        re.search(r"\bsingle[- ]vineyard\b", relevant, re.I)
        or re.search(r"\b100%\s+[^.]{0,80}\bvineyard\b", relevant, re.I)
    )


def _extract_product_metadata(title: str, page_text: str) -> dict[str, Any]:
    varietal = _extract_varietal(title, page_text)
    graph = _infer_graph_category(varietal, title, page_text)
    general = _infer_general_category(graph, varietal, title)
    region, subregion, geography_conflict = _extract_region(page_text)
    alcohol = _extract_abv(page_text)
    cases = _extract_cases(page_text)
    blob = f"{title} {page_text[:2500]}".casefold()
    estate = bool(
        re.search(r"\bestate\b", title, re.I)
        or re.search(r"\b(?:100%\s+)?estate[- ]grown\b", page_text, re.I)
        or re.search(r"\bestate[- ]bottled\b", page_text, re.I)
        or re.search(r"\b(?:crafted|made|produced) from[^.]{0,100}\bestate\b", page_text, re.I)
    )
    single = _infer_single_vineyard(title, page_text)
    tier = _infer_tier(title, page_text, estate, cases)
    return {
        "varietal": varietal,
        "graph_category": graph,
        "general_category": general,
        "region": region,
        "subregion": subregion,
        "alcohol_pct": alcohol,
        "cases_produced": cases,
        "estate": estate,
        "single_vineyard": single,
        "product_tier": tier,
        "availability_status": _availability_status(page_text),
        "_geography_conflict": geography_conflict,
    }

def _extract_product_page_offers(html: str, base_url: str) -> list[WineOffer]:
    """Extract price plus conservative product metadata from one selected page."""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    heading = soup.find("h1")
    if heading:
        title = _clean_name(heading.get_text(" ", strip=True))
    if not title:
        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            title = _clean_name(og.get("content"))
    if not title and soup.title:
        title = _clean_name(soup.title.get_text(" ", strip=True))

    # Build visible text once, excluding script/style noise.
    soup_for_text = BeautifulSoup(html, "html.parser")
    for tag in soup_for_text(["script", "style", "noscript", "svg"]):
        tag.decompose()
    page_text = re.sub(r"\s+", " ", soup_for_text.get_text(" ", strip=True))
    metadata = _extract_product_metadata(title, page_text)
    geography_conflict = bool(metadata.pop("_geography_conflict", False))

    structured = _extract_jsonld(soup, base_url)
    if structured:
        for offer in structured:
            if not offer.vintage:
                offer.vintage = _vintage_from_name(offer.wine) or _vintage_from_name(page_text[:900])
            for field, value in metadata.items():
                setattr(offer, field, value)
            if geography_conflict and offer.confidence == "High":
                offer.confidence = "Moderate"
            # Prefer the visible h1/OG title when JSON-LD is generic.
            if title and (_ascii_key(offer.wine) in {"wine", "product", "shop"} or len(offer.wine) < 4):
                offer.wine = title
            offer.wine = _canonical_wine_name(offer.wine, offer.vintage)
        return _dedupe(structured)

    if not title:
        return []

    regular, sale, club = _classify_prices(page_text)
    if regular is None and sale is None and club is None:
        return []

    price_match = PRICE_RE.search(page_text)
    if price_match:
        start = max(0, price_match.start() - 180)
        end = min(len(page_text), price_match.end() + 320)
        evidence = page_text[start:end]
    else:
        evidence = page_text[:500]

    extracted_vintage = _vintage_from_name(title) or _vintage_from_name(page_text[:900])
    canonical_title = _canonical_wine_name(title, extracted_vintage)
    return [
        WineOffer(
            wine=canonical_title,
            vintage=extracted_vintage,
            regular_price=regular,
            sale_price=sale,
            club_price=club,
            currency="USD",
            product_url=base_url,
            evidence=evidence[:500],
            extraction_method="Selected product page",
            confidence=("Moderate" if geography_conflict else ("High" if regular is not None else "Moderate")),
            **metadata,
        )
    ]

def merge_offers(offers: list[WineOffer]) -> list[WineOffer]:
    return _dedupe(offers)


def scan_selected_product_pages(
    urls: list[str], *, delay_seconds: float = 0.9, max_pages: int = 12
) -> tuple[list[WineOffer], list[dict[str, str]], int]:
    """Fetch only pages the user explicitly selected, once each, sequentially."""
    unique_urls = []
    seen = set()
    for raw in urls:
        url = validate_public_url(raw)
        key = url.casefold()
        if key not in seen:
            seen.add(key)
            unique_urls.append(url)
    if not unique_urls:
        raise CatalogScanError("Select at least one product page first.")
    if len(unique_urls) > max_pages:
        raise CatalogScanError(
            f"Select no more than {max_pages} product pages per scan to keep request volume low."
        )
    site = _site_key(unique_urls[0])
    if any(_site_key(url) != site for url in unique_urls):
        raise CatalogScanError("Selected product pages must all belong to the same winery site.")

    offers: list[WineOffer] = []
    failures: list[dict[str, str]] = []
    fetched_count = 0
    for idx, url in enumerate(unique_urls):
        try:
            fetched = fetch_catalog_page(url)
            fetched_count += 1
            page_offers = _extract_product_page_offers(fetched.html, fetched.final_url)
            if not page_offers:
                # Reuse the catalog parser as a fallback for unusually structured pages.
                page_offers = extract_catalog_offers(fetched.html, fetched.final_url)
            if page_offers:
                offers.extend(page_offers)
            else:
                failures.append({"url": url, "error": "No dependable product + price record found."})
        except CatalogScanError as exc:
            failures.append({"url": url, "error": str(exc)})
        if idx < len(unique_urls) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return _dedupe(offers), failures, fetched_count


def _dedupe(offers: list[WineOffer]) -> list[WineOffer]:
    by_key: dict[tuple[str, str], WineOffer] = {}
    for offer in offers:
        key = (_ascii_key(offer.wine), _ascii_key(offer.product_url))
        current = by_key.get(key)
        if current is None:
            by_key[key] = offer
            continue
        # Prefer structured evidence, then fill missing price fields.
        if offer.extraction_method == "JSON-LD" and current.extraction_method != "JSON-LD":
            preferred, other = offer, current
        else:
            preferred, other = current, offer
        for field in ("regular_price", "sale_price", "club_price", "alcohol_pct", "cases_produced"):
            if getattr(preferred, field) is None and getattr(other, field) is not None:
                setattr(preferred, field, getattr(other, field))
        for field in ("varietal", "graph_category", "general_category", "region", "subregion", "product_tier", "availability_status"):
            if not getattr(preferred, field, "") and getattr(other, field, ""):
                setattr(preferred, field, getattr(other, field))
        preferred.estate = bool(preferred.estate or other.estate)
        preferred.single_vineyard = bool(preferred.single_vineyard or other.single_vineyard)
        if not preferred.vintage and other.vintage:
            preferred.vintage = other.vintage
        by_key[key] = preferred

    # A second pass merges same label/vintage when one parser found a slightly different URL.
    final: dict[tuple[str, str], WineOffer] = {}
    for offer in by_key.values():
        key = (_ascii_key(offer.wine), offer.vintage)
        current = final.get(key)
        if current is None:
            final[key] = offer
            continue
        for field in ("regular_price", "sale_price", "club_price", "alcohol_pct", "cases_produced"):
            if getattr(current, field) is None and getattr(offer, field) is not None:
                setattr(current, field, getattr(offer, field))
        for field in ("varietal", "graph_category", "general_category", "region", "subregion", "product_tier", "availability_status"):
            if not getattr(current, field, "") and getattr(offer, field, ""):
                setattr(current, field, getattr(offer, field))
        current.estate = bool(current.estate or offer.estate)
        current.single_vineyard = bool(current.single_vineyard or offer.single_vineyard)
        if current.extraction_method != "JSON-LD" and offer.extraction_method == "JSON-LD":
            current.extraction_method = "JSON-LD + HTML"
            current.confidence = "High"
        elif current.extraction_method != offer.extraction_method:
            current.extraction_method = "JSON-LD + HTML"
        if len(offer.evidence) > len(current.evidence):
            current.evidence = offer.evidence
        final[key] = current

    return sorted(final.values(), key=lambda o: (_ascii_key(o.wine), o.vintage))


def extract_catalog_offers(html: str, base_url: str) -> list[WineOffer]:
    soup = BeautifulSoup(html, "html.parser")
    structured = _extract_jsonld(soup, base_url)
    repeating = _extract_repeating_product_blocks(soup, base_url)
    cards = _extract_html_cards(soup, base_url)
    return _dedupe(structured + repeating + cards)


def scan_catalog(url: str, *, provider_id: str = "") -> tuple[CatalogFetch, list[WineOffer]]:
    """Scan one catalog URL, preferring documented provider feeds when available.

    VinoShipper is handled through its documented Product Feed API when a
    producer id is supplied or can be recovered from the public shop shell.
    Other sites retain the existing static-HTML/JSON-LD workflow.
    """
    requested = validate_public_url(url)

    # If the pasted URL itself exposes a VinoShipper producer ID, or the user
    # supplied one explicitly, the official feed can be queried directly.
    if is_vinoshipper_url(requested):
        pid = str(provider_id or _producer_id_from_url(requested) or "").strip()
        if pid:
            offers = fetch_vinoshipper_product_feed(pid, requested)
            return CatalogFetch(
                requested_url=requested,
                final_url=requested,
                status_code=200,
                content_type="application/json",
                html="",
                bytes_read=0,
                robots_status="documented provider feed",
                request_note="VinoShipper Product Feed API",
                provider="VinoShipper",
                provider_note=f"Official Product Feed used for producer {pid}",
                provider_requests=1,
            ), offers

        # Otherwise make the normal one-page request first; many VinoShipper
        # embed shells expose the producer/account id in their configuration.
        fetched = fetch_catalog_page(requested)
        pid = infer_vinoshipper_producer_id(fetched.html, fetched.final_url)
        if pid:
            offers = fetch_vinoshipper_product_feed(pid, requested)
            fetched.provider = "VinoShipper"
            fetched.provider_note = f"Official Product Feed used for producer {pid}"
            fetched.provider_requests = 1
            fetched.request_note = f"{fetched.request_note}; VinoShipper Product Feed API"
            return fetched, offers
        fetched.provider = "VinoShipper"
        fetched.provider_note = "Producer ID was not exposed in the public shop shell; enter it manually to use the documented Product Feed."
        offers = extract_catalog_offers(fetched.html, fetched.final_url)
        return fetched, offers

    fetched = fetch_catalog_page(requested)
    offers = extract_catalog_offers(fetched.html, fetched.final_url)
    return fetched, offers


def offers_to_rudder_rows(offers: list[WineOffer], winery: str = "") -> list[dict[str, Any]]:
    today = date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for offer in offers:
        if getattr(offer, "provider_id", ""):
            offer = _finalize_vinoshipper_offer(offer, offer.provider_id)
        selected_price = offer.regular_price or offer.sale_price or offer.club_price
        if selected_price is None:
            continue
        if offer.regular_price is not None:
            price_type = "Winery retail"
        elif offer.sale_price is not None:
            price_type = "Observed retail"
        else:
            price_type = "Wine club/member price"
        rows.append({
            "winery": winery,
            "wine": offer.wine,
            "vintage": offer.vintage,
            "varietal": offer.varietal,
            "graph_category": offer.graph_category,
            "general_category": offer.general_category,
            "region": offer.region,
            "subregion": offer.subregion,
            "price": selected_price,
            "price_type": price_type,
            "critic": "",
            "critic_score": "",
            "cases_produced": offer.cases_produced if offer.cases_produced is not None else "",
            "alcohol_pct": offer.alcohol_pct if offer.alcohol_pct is not None else "",
            "estate": offer.estate,
            "single_vineyard": offer.single_vineyard,
            "product_tier": offer.product_tier or "Core",
            "source_name": winery,
            "source_url": offer.product_url,
            "price_date": today,
            "data_confidence": offer.confidence,
        })
    return rows

