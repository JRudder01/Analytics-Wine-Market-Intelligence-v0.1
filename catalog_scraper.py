from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
import unicodedata
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
MAX_HTML_BYTES = 2_000_000
REQUEST_TIMEOUT = (5, 12)
ROBOTS_TTL_SECONDS = 24 * 60 * 60
PAGE_CACHE_TTL_SECONDS = 24 * 60 * 60
MAX_REDIRECTS = 3

_ROBOTS_CACHE: dict[str, tuple[float, RobotFileParser | None, str]] = {}
_PAGE_CACHE: dict[str, tuple[float, str, str, str, str]] = {}  # ts, html, content_type, etag, last_modified

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


def _extract_region(text: str) -> tuple[str, str]:
    """Extract an appellation conservatively from visible product-page text."""
    patterns = [
        r"(?:appellation|ava|region)\s*[:\-]?\s*([A-Z][A-Za-zÀ-ÿ0-9'&.\- ]{2,60}?)(?=\s{2,}|\s(?:technical|alcohol|harvest|cases|vineyard|$))",
        r"\b([A-Z][A-Za-zÀ-ÿ'&.\- ]{2,50}\sAVA)\b",
    ]
    found = _first_match(patterns, text)
    if found:
        found = re.sub(r"\s+AVA$", "", found, flags=re.I).strip()
        return found, ""

    known = [
        "Napa Valley", "Paso Robles", "San Luis Obispo Coast", "Sonoma Coast",
        "Russian River Valley", "Carneros", "Oak Knoll District", "Howell Mountain",
        "Atlas Peak", "Mount Veeder", "Stags Leap District", "Rutherford", "Oakville",
        "Yountville", "Calistoga", "St. Helena", "Adelaida District", "Willow Creek District",
        "Templeton Gap District", "Santa Margarita Ranch", "York Mountain",
    ]
    hits = [name for name in known if re.search(rf"\b{re.escape(name)}\b", text, re.I)]
    if not hits:
        return "", ""
    # Broad region first, narrower district as subregion when both are present.
    broad = next((x for x in hits if x in {"Napa Valley", "Paso Robles", "San Luis Obispo Coast", "Sonoma Coast", "Carneros", "Russian River Valley"}), hits[0])
    sub = next((x for x in hits if x != broad), "")
    return broad, sub


def _extract_abv(text: str) -> float | None:
    patterns = [
        r"(?:alcohol|abv)\s*[:\-]?\s*([0-9]{1,2}(?:\.[0-9])?)\s*%?",
        r"([0-9]{1,2}(?:\.[0-9])?)\s*%\s*(?:alcohol|abv)",
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
    ]

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
            and any(g.casefold() in candidate.casefold() for g in grape_names)
        ):
            return candidate

    explicit = _first_match([
        r"(?:varietal|variety|composition)\s*[:\-]?\s*([^.;]{3,180})",
        r"(?:made from|composed of)\s+([^.;]{3,180})",
    ], text)
    if explicit and any(g.casefold() in explicit.casefold() for g in grape_names):
        return explicit

    title_hits = [g for g in grape_names if re.search(rf"\b{re.escape(g)}\b", title, re.I)]
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
    if "white blend" in blob or "blanc" in title.casefold():
        return "White Blend"
    if "red blend" in blob or "proprietary red" in blob:
        return "Red Blend"
    singles = [
        "Cabernet Sauvignon", "Cabernet Franc", "Chardonnay", "Pinot Noir", "Merlot",
        "Sauvignon Blanc", "Syrah", "Grenache", "Zinfandel", "Petite Sirah", "Viognier",
        "Riesling", "Barbera", "Sangiovese", "Tempranillo", "Vermentino", "Muscat Canelli",
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


def _extract_product_metadata(title: str, page_text: str) -> dict[str, Any]:
    varietal = _extract_varietal(title, page_text)
    graph = _infer_graph_category(varietal, title, page_text)
    general = _infer_general_category(graph, varietal, title)
    region, subregion = _extract_region(page_text)
    alcohol = _extract_abv(page_text)
    cases = _extract_cases(page_text)
    blob = f"{title} {page_text[:2500]}".casefold()
    estate = bool(
        re.search(r"\bestate\b", title, re.I)
        or re.search(r"\b(?:100%\s+)?estate[- ]grown\b", page_text, re.I)
        or re.search(r"\bestate[- ]bottled\b", page_text, re.I)
        or re.search(r"\b(?:crafted|made|produced) from[^.]{0,100}\bestate\b", page_text, re.I)
    )
    single = bool(re.search(r"\bsingle[- ]vineyard\b", page_text, re.I))
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

    structured = _extract_jsonld(soup, base_url)
    if structured:
        for offer in structured:
            if not offer.vintage:
                offer.vintage = _vintage_from_name(offer.wine) or _vintage_from_name(page_text[:900])
            for field, value in metadata.items():
                setattr(offer, field, value)
            # Prefer the visible h1/OG title when JSON-LD is generic.
            if title and (_ascii_key(offer.wine) in {"wine", "product", "shop"} or len(offer.wine) < 4):
                offer.wine = title
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

    return [
        WineOffer(
            wine=title,
            vintage=_vintage_from_name(title) or _vintage_from_name(page_text[:900]),
            regular_price=regular,
            sale_price=sale,
            club_price=club,
            currency="USD",
            product_url=base_url,
            evidence=evidence[:500],
            extraction_method="Selected product page",
            confidence="High" if regular is not None else "Moderate",
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
    cards = _extract_html_cards(soup, base_url)
    return _dedupe(structured + cards)


def scan_catalog(url: str) -> tuple[CatalogFetch, list[WineOffer]]:
    fetched = fetch_catalog_page(url)
    offers = extract_catalog_offers(fetched.html, fetched.final_url)
    return fetched, offers


def offers_to_rudder_rows(offers: list[WineOffer], winery: str = "") -> list[dict[str, Any]]:
    today = date.today().isoformat()
    rows: list[dict[str, Any]] = []
    for offer in offers:
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

