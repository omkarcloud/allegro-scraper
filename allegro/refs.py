"""Reference resolvers, market table and link builders for /allegro/*.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): each resolver takes a bare id OR any allegro.<tld> link and
returns the id; it raises ValueError with a user-facing message (RefField
turns that into a 400).

Identifier shapes (captured 2026-10-23):
  * offer     9–12 digits; links /oferta/<slug>-<id> (slug optional) and
              /produkt/<slug>-<uuid>?offerId=<id>
  * product   uuid; links /produkt/<slug>-<uuid> and
              /oferty-produktu/<slug>-<uuid> (slug optional)
  * seller    login (letters, digits, _ . -); links /uzytkownik/<login>[/...]
  * category  digits (or a uuid for the department roots); links
              /kategoria/<slug>-<id> — a department alias such as
              /kategoria/elektronika carries no id, so it is kept as the
              alias and resolved by the page itself

Markets: the three Allegro marketplaces share one opbox page structure and
the edge host; only the search path differs (home page search-box config,
2026-10-23: pl /listing, cz /vyhledavani, sk /vyhladavanie). A DataDome
identity is per domain, so every market mints its own.
"""
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

MARKETS = {
    "pl": {"host": "https://allegro.pl", "edge": "https://edge.allegro.pl",
           "search_path": "/listing", "marketplace_id": "allegro-pl",
           "timezone": "Europe/Warsaw", "language": "pl-PL"},
    "cz": {"host": "https://allegro.cz", "edge": "https://edge.allegro.cz",
           "search_path": "/vyhledavani", "marketplace_id": "allegro-cz",
           "timezone": "Europe/Prague", "language": "cs-CZ"},
    "sk": {"host": "https://allegro.sk", "edge": "https://edge.allegro.sk",
           "search_path": "/vyhladavanie", "marketplace_id": "allegro-sk",
           "timezone": "Europe/Bratislava", "language": "sk-SK"},
}
DEFAULT_MARKET = "pl"
SITE = MARKETS[DEFAULT_MARKET]["host"]

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
OFFER_ID_RE = re.compile(r"^[0-9]{6,14}$")
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{2,60}$")
CATEGORY_ID_RE = re.compile(r"^[0-9]{1,9}$")
CATEGORY_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,120}$")

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_LINK_OFFER_RE = re.compile(r"/oferta/(?:[^/?#]*?-)?([0-9]{6,14})(?:[/?#]|$)")
_LINK_OFFER_PARAM_RE = re.compile(r"[?&]offerId=([0-9]{6,14})")
_LINK_PRODUCT_RE = re.compile(r"/(?:produkt|oferty-produktu)/(?:[^/?#]*?-)?(" + _UUID + r")(?:[/?#]|$)", re.I)
_LINK_SELLER_RE = re.compile(r"/uzytkownik/([A-Za-z0-9_.\-]{2,60})(?:[/?#]|$)")
_LINK_CATEGORY_RE = re.compile(r"/kategoria/([^/?#]+)")

_HOSTS = tuple(urlparse(m["host"]).hostname for m in MARKETS.values())


def _is_link(value):
    return value.startswith(("http://", "https://", "//"))


def _parse_link(value):
    url = value if not value.startswith("//") else "https:" + value
    host = (urlparse(url).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _HOSTS):
        raise ValueError("Must be an allegro.pl / allegro.cz / allegro.sk link.")
    return url


def resolve_offer(value):
    """Bare offer id or an offer / product-with-offerId link -> the offer id."""
    value = (value or "").strip()
    if OFFER_ID_RE.match(value):
        return value
    if _is_link(value):
        url = _parse_link(value)
        match = _LINK_OFFER_RE.search(url) or _LINK_OFFER_PARAM_RE.search(url)
        if match:
            return match.group(1)
        raise ValueError("Must be an Allegro offer link (https://allegro.pl/oferta/<name>-<id>).")
    raise ValueError("Must be a numeric Allegro offer id or an offer link.")


def resolve_product(value):
    """Bare product uuid or a /produkt/ / /oferty-produktu/ link -> the uuid."""
    value = (value or "").strip()
    if UUID_RE.match(value):
        return value.lower()
    if _is_link(value):
        url = _parse_link(value)
        match = _LINK_PRODUCT_RE.search(url)
        if match:
            return match.group(1).lower()
        raise ValueError("Must be an Allegro product link (https://allegro.pl/produkt/<name>-<uuid>).")
    raise ValueError("Must be an Allegro product id (uuid) or a product link.")


def resolve_seller(value):
    """Bare seller login or a /uzytkownik/<login> link -> the login."""
    value = (value or "").strip()
    if _is_link(value):
        url = _parse_link(value)
        match = _LINK_SELLER_RE.search(url)
        if match and match.group(1).lower() != "notfound":
            return match.group(1)
        raise ValueError("Must be an Allegro seller link (https://allegro.pl/uzytkownik/<login>).")
    if LOGIN_RE.match(value):
        return value
    raise ValueError("Must be an Allegro seller login or a seller link.")


def resolve_category(value):
    """Bare category id, a department alias ("elektronika") or a /kategoria/
    link -> the id when the slug carries one, else the alias."""
    value = (value or "").strip()
    if _is_link(value):
        url = _parse_link(value)
        match = _LINK_CATEGORY_RE.search(url)
        if not match:
            raise ValueError("Must be an Allegro category link (https://allegro.pl/kategoria/<name>-<id>).")
        slug = match.group(1).lower()
        tail = slug.rsplit("-", 1)[-1]
        return tail if CATEGORY_ID_RE.match(tail) else slug
    low = value.lower()
    if CATEGORY_ID_RE.match(low) or UUID_RE.match(low):
        return low
    if CATEGORY_ALIAS_RE.match(low):
        tail = low.rsplit("-", 1)[-1]
        return tail if CATEGORY_ID_RE.match(tail) and "-" in low else low
    raise ValueError("Must be an Allegro category id, a category alias (elektronika) or a category link.")


# ---- link builders -------------------------------------------------------------

def host(country=DEFAULT_MARKET):
    return MARKETS[country]["host"]


def edge_host(country=DEFAULT_MARKET):
    return MARKETS[country]["edge"]


def offer_link(offer_id, country=DEFAULT_MARKET):
    return f"{host(country)}/oferta/{offer_id}"


def product_link(product_id, country=DEFAULT_MARKET):
    return f"{host(country)}/produkt/{product_id}"


def product_offers_link(product_id, country=DEFAULT_MARKET):
    return f"{host(country)}/oferty-produktu/{product_id}"


def seller_link(login, country=DEFAULT_MARKET):
    return f"{host(country)}/uzytkownik/{login}"


def seller_ratings_link(login, country=DEFAULT_MARKET):
    return f"{host(country)}/uzytkownik/{login}/oceny"


def category_link(category, country=DEFAULT_MARKET):
    """`category` is an id or an alias (department roots have no id slug)."""
    return f"{host(country)}/kategoria/{category}"


def search_link(country=DEFAULT_MARKET):
    return f"{host(country)}{MARKETS[country]['search_path']}"


def clean_offer_link(url, offer_id=None, country=DEFAULT_MARKET):
    """Sponsored cards link through /events/clicks?...&redirect=<offer url>
    and every card URL carries bi_* / navCategoryId tracking params. On
    allegro.pl the canonical /oferta/<id> link is enough; the other markets
    keep the card's own link (their offer path is not verified), unwrapped
    and stripped of tracking params."""
    if offer_id and country == DEFAULT_MARKET:
        return offer_link(offer_id, country)
    if not url:
        return offer_link(offer_id, country) if offer_id else None
    parts = urlparse(url)
    query = parse_qs(parts.query)
    if "/events/clicks" in parts.path and query.get("redirect"):
        return clean_offer_link(query["redirect"][0], None, country)
    kept = {k: v for k, v in query.items() if not k.startswith("bi_") and k not in ("navCategoryId", "sig", "placement")}
    return urlunparse(parts._replace(query=urlencode(kept, doseq=True), fragment=""))


# ---- departments (the site's top level, allegro.pl search-box scopes, 2026-10-23) ----
# /kategoria/<alias> pages carry no numeric id in the slug; the page's own
# categories box returns the department's id (a uuid for some) and children.
DEPARTMENTS = (
    {"id": "5", "name": "Dom i Ogród", "alias": "dom-i-ogrod"},
    {"id": "11763", "name": "Dziecko", "alias": "dziecko"},
    {"id": "42540aec-367a-4e5e-b411-17c09b08e41f", "name": "Elektronika", "alias": "elektronika"},
    {"id": "4bd97d96-f0ff-46cb-a52c-2992bd972bb1", "name": "Firma i usługi", "alias": "firma"},
    {"id": "a408e75a-cede-4587-8526-54e9be600d9f", "name": "Kolekcje i sztuka", "alias": "kolekcje-i-sztuka"},
    {"id": "38d588fd-7e9c-4c42-a4ae-6831775eca45", "name": "Kultura i rozrywka", "alias": "kultura-i-rozrywka"},
    {"id": "ea5b98dd-4b6f-4bd0-8c80-22c2629132d0", "name": "Moda", "alias": "moda"},
    {"id": "3", "name": "Motoryzacja", "alias": "motoryzacja"},
    {"id": "20782", "name": "Nieruchomości", "alias": "nieruchomosci"},
    {"id": "3919", "name": "Sport i turystyka", "alias": "sport-i-turystyka"},
    {"id": "258832", "name": "Supermarket", "alias": "supermarket"},
    {"id": "1429", "name": "Uroda", "alias": "uroda"},
    {"id": "121882", "name": "Zdrowie", "alias": "zdrowie"},
)

# Listing sort keys (allegro.listing.sort <select>, 2026-10-23): public value -> order=
SORT_ORDERS = {
    "relevance": "m",
    "price_asc": "p",
    "price_desc": "pd",
    "price_with_delivery_asc": "d",
    "price_with_delivery_desc": "dd",
    "popularity": "qd",
    "ending_soonest": "t",
    "newest": "n",
    "product_rating": "prd",
}

# Condition filter (`stan=`; the "Stan" NESTED_MULTI filter, 2026-10-23)
CONDITIONS = {"new": "nowe", "used": "używane", "damaged": "uszkodzone", "refurbished": "odnowione"}
