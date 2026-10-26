"""HTML / JSON -> clean dicts for every /allegro/* endpoint (pure functions).

Every Allegro page is "opbox": the data a page renders is server-side
serialized into `<script type="application/json" data-serialize-box-id=…>`
boxes, one per UI box. The parsers read those boxes, never the DOM, except
for three tiny header bits (seller name / company label / offer count, and
the ratings summary) that the site renders as plain HTML.

  * listing pages (search, category, seller storefront, product offers,
    ended) carry `{"__listing_StoreState": {items: {elements[],
    searchMeta, order, searchPhrase}}}` plus a filters box
    (`{"slots": [...], "categories": {...}, "selectedFilters": ...}`) and a
    category-nav box (`{"categories": [...], "path": [...]}`)
  * offer and product pages carry `{"facade": {...}, "reviews": {...}}`
    (one record for the offer, the product and the seller) and a price box
    (`{"price", "transactionSection", "schema", ...}`) with the stock
  * the seller ratings page carries `{"sellerId", "ratings": {...}}`
  * edge.allegro.pl answers JSON for suggestions, product reviews and
    seller ratings

Value conventions (shared with the other scraper packages):
  * money   {"amount": 2389.0, "currency": "PLN"} (numbers, never strings)
  * dates   ISO as the site gives them (UTC "Z" timestamps on reviews)
  * keys    snake_case; `link` not `url`; booleans as questions; null for
            anything the page does not carry (never "" / "N/A")
  * noise   tracking ids, emission ids, analytics signatures, label
            styling, icons and experiment maps are dropped

Fixtures captured 2026-10-23 (allegro/fixtures/, gzipped): a search listing
page 2, a category page with and without filters, an ENDED offer page, a
product page (representative offer), the product's /oferty-produktu/ page,
a seller storefront, the seller ratings page, the 404 page, the
"użytkownik nieznaleziony" page, the DataDome 403 and the Allegro-captcha
429 bodies, an ended-offers listing, an allegro.cz category page and the
three edge JSON payloads.
"""
import html as html_lib
import json
import re

from allegro.refs import DEFAULT_MARKET, SORT_ORDERS, clean_offer_link, host, product_link, seller_link

_BOX_RE = re.compile(
    r'<script[^>]*type="application/json"[^>]*data-serialize-box-id="[^"]*"[^>]*>(.*?)</script>', re.S)
_TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_INT_RE = re.compile(r"-?\d[\d\s ]*")
_NUM_RE = re.compile(r"-?\d[\d\s ]*(?:[.,]\d+)?")

DD_MARKERS = ("var dd=", "captcha-delivery", "enable js and disable")
CAPTCHA_MARKERS = ("allegrocaptcha.com",)
NOT_FOUND_TITLES = ("błąd 404", "chyba 404", "nieznaleziony", "nenalezen", "nenájdený", "error 404")

LISTING_PAGE_SIZE = 60     # organic cards per listing page (sponsored ones come on top)
REVIEWS_PAGE_SIZE = 20     # edge /product-reviews
RATINGS_PAGE_SIZE = 20     # edge /ratings-api (`size` accepted up to 50)

_SORT_BY_ORDER = {v: k for k, v in SORT_ORDERS.items()}


# ---- generic helpers -------------------------------------------------------------

def boxes(html):
    """Every JSON box on the page, parsed (unparseable ones skipped)."""
    out = []
    for body in _BOX_RE.findall(html or ""):
        try:
            out.append(json.loads(body))
        except ValueError:
            continue
    return out


def find_box(boxes_, *keys, where=None):
    """The first dict box carrying every key in `keys` (and passing `where`)."""
    for box in boxes_:
        if isinstance(box, dict) and all(k in box for k in keys) and (where is None or where(box)):
            return box
    return None


def page_title(html):
    m = _TITLE_RE.search(html or "")
    return html_lib.unescape(" ".join(m.group(1).split())) if m else None


def page_kind(html, status=None):
    """"datadome" | "captcha" | "not_found" | "page" — the block pages are
    tiny and carry their vendor's markers; a 404 says so in its title."""
    head = (html or "")[:8000].lower()
    # Allegro's own captcha page (HTTP 429) borrows DataDome's "enable JS"
    # copy, so its iframe host is checked first.
    if any(m in head for m in CAPTCHA_MARKERS):
        return "captcha"
    if any(m in head for m in DD_MARKERS):
        return "datadome"
    if status == 404:
        return "not_found"
    title = (page_title(html) or "").lower()
    if any(t in title for t in NOT_FOUND_TITLES):
        return "not_found"
    return "page"


def _text(value):
    """Collapse whitespace, strip tags; empty -> None."""
    if value is None:
        return None
    value = html_lib.unescape(_TAG_RE.sub(" ", str(value)))
    value = " ".join(value.replace(" ", " ").split())
    return value or None


def _num(value):
    """"2389.00" / "98,9%" / "1 512" -> float; None for nothing numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    m = _NUM_RE.search(str(value))
    if not m:
        return None
    raw = m.group(0).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _int(value):
    n = _num(value)
    return int(n) if n is not None else None


def _count_from_label(label):
    """"39 osób kupiło ostatnio" / "224 oceny" / "9999+" -> 39 / 224 / 9999."""
    if not label:
        return None
    m = _INT_RE.search(str(label))
    return int(m.group(0).replace(" ", "").replace(" ", "")) if m else None


def _money(value):
    """{"amount": "45.00", "currency": "PLN"} -> {"amount": 45.0, "currency": "PLN"}."""
    if not isinstance(value, dict) or value.get("amount") in (None, ""):
        return None
    return {"amount": _num(value.get("amount")), "currency": value.get("currency")}


def _label_parts_text(labels):
    """[{labelParts:[{text}...]}...] -> ["dostawa we wtorek", ...] (icons dropped)."""
    out = []
    for label in labels or []:
        parts = [p.get("text") for p in (label or {}).get("labelParts") or [] if isinstance(p, dict) and p.get("text")]
        text = _text(" ".join(parts))
        if text:
            out.append(text)
    return out


def _first(*values):
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


# ---- listing pages (search / category / seller / product offers / ended) ---------

def _card(element, country):
    """One listing element of type product / buyNow / offer -> a card."""
    e = element
    offer_id = e.get("offerId")
    seller = e.get("seller") or {}
    product_id = e.get("id") if e.get("type") == "product" else None
    url = e.get("url") or ""
    if "/produkt/" in url and not product_id:
        m = re.search(r"/produkt/(?:[^/?#]*?-)?([0-9a-f-]{36})", url)
        product_id = m.group(1) if m else None
    review = (e.get("productReview") or {}).get("rating") or {}
    shipping = e.get("shipping") or {}
    badges = e.get("badges") or {}
    popularity = e.get("productPopularity") or {}
    condition = None
    parameters = []
    for p in e.get("parameters") or []:
        name, values = p.get("name"), p.get("values") or []
        if name == "Stan" and values and condition is None:
            condition = values[0]
        parameters.append({"name": name, "values": values})
    return {
        "id": offer_id,
        "title": _text((e.get("title") or {}).get("text")),
        "link": clean_offer_link(url, offer_id, country) if offer_id else None,
        "product": {
            "id": product_id,
            "link": product_link(product_id, country) if product_id else None,
            "rating": _num(review.get("average")),
            "ratings_count": review.get("count"),
            "offers_count": e.get("productOffersCount"),
            "buyers_last_30_days": _count_from_label(popularity.get("label")),
            "variants_label": e.get("productVariantsLabel"),
        } if (product_id or review or e.get("productOffersCount")) else None,
        "price": _money((e.get("price") or {}).get("mainPrice")),
        "price_per_unit": _text(e.get("pricePerUnit")) if isinstance(e.get("pricePerUnit"), str) else None,
        "delivery": {
            "lowest_cost": _money(shipping.get("lowest")),
            "price_with_delivery": _money(shipping.get("itemWithDelivery")),
            "is_free": shipping.get("freeDelivery"),
            "has_free_return": shipping.get("freeReturn"),
            "estimate": _first(*_label_parts_text((badges.get("logistics") or {}).get("labels"))),
            "has_smart": bool(e.get("freebox")),
        },
        "condition": condition,
        "parameters": parameters,
        "quantity_available": e.get("quantity"),
        "seller": {
            "id": seller.get("id"),
            "login": seller.get("login"),
            "link": seller.get("userListingUrl") or (seller_link(seller["login"], country) if seller.get("login") else None),
            "is_company": seller.get("company"),
            "is_super_seller": seller.get("superSeller"),
            "positive_feedback_percent": _num(seller.get("positiveFeedbackPercent")),
            "positive_feedback_count": seller.get("positiveFeedbackCount"),
            "logo": (seller.get("brandzone") or {}).get("logotypeUrl"),
        } if seller else None,
        "images": [p.get("medium") or p.get("small") for p in e.get("photos") or [] if isinstance(p, dict)],
        "thumbnail": e.get("mainThumbnail"),
        "category_id": (e.get("navigationCategory") or {}).get("id"),
        "placement": (e.get("context") or "regular").lower(),
        "is_sponsored": bool(e.get("isSponsored")),
        "is_promoted": bool(e.get("promoted")),
        "is_featured": bool(e.get("featured")),
        "is_best_price_guarantee": bool(e.get("isBestPriceGuarantee")),
        "is_ended": bool(e.get("isEnded")),
        "has_installments": "installments" in badges,
        "offer_type": e.get("type"),
    }


def _listing_state(boxes_):
    box = find_box(boxes_, "__listing_StoreState")
    return box["__listing_StoreState"] if box else None


def _filters_box(boxes_):
    return find_box(boxes_, "slots", "categories", "selectedFilters")


def _nav_box(boxes_):
    return find_box(boxes_, "categories", "path", "baseUrl")


def _category_node(node, country, with_counts=True):
    """A node of the filters box's category tree / the nav box's path.
    Path (ancestor) nodes carry a meaningless 0 counter: with_counts=False
    drops it."""
    if not isinstance(node, dict):
        return None
    alias = node.get("alias")
    out = {
        "id": node.get("id"),
        "name": node.get("name"),
        "alias": alias,
        "link": f"{host(country)}/kategoria/{alias}" if alias and alias != "/" else host(country),
    }
    if with_counts:
        count = node.get("count")
        out["offers_count"] = count if count is not None else _count_from_label((node.get("counter") or {}).get("text"))
        out["has_children"] = node.get("hasChildren")
    return out


def _category_path(nav, country):
    return [_category_node(p, country, with_counts=False) for p in (nav or {}).get("path") or [] if isinstance(p, dict)]


def _applied_filters(filters_box):
    out = []
    for value in (filters_box or {}).get("selectedFilters", {}).values() or []:
        if not isinstance(value, dict):
            continue
        url = value.get("url") or {}
        out.append({"id": value.get("filterId"), "key": url.get("key"), "value": url.get("value")})
    return out


def parse_listing(html, country=DEFAULT_MARKET):
    """A listing page -> {query, sort, category, applied_filters, results,
    stats, pagination}. A page past the end has no cards."""
    bx = boxes(html)
    state = _listing_state(bx)
    if state is None:
        raise ValueError("no listing state on the page")
    items = state.get("items") or {}
    meta = items.get("searchMeta") or {}
    cards = [_card(e, country) for e in items.get("elements") or []
             if isinstance(e, dict) and e.get("offerId")]
    filters_box = _filters_box(bx)
    nav = _nav_box(bx)
    category = None
    tree = (filters_box or {}).get("categories")
    if isinstance(tree, dict) and tree.get("id"):
        category = _category_node(tree, country)
        category["path"] = _category_path(nav, country)
        category["subcategories"] = [_category_node(s, country) for s in tree.get("subcategories") or []]
    total_pages = _int(meta.get("lastAvailablePage"))
    return {
        "query": items.get("searchPhrase") or None,
        "sort": _SORT_BY_ORDER.get(items.get("order"), items.get("order")),
        "category": category,
        "applied_filters": _applied_filters(filters_box),
        "results": cards,
        "stats": {
            "total_count": _int(meta.get("totalCount")),
            "available_count": _int(meta.get("availableCount")),
            "products_count": _int(meta.get("productsCount")),
            "is_result_set_too_large": str(meta.get("resultSetTooLarge")).lower() == "true",
        },
        "pagination": {
            "page": None,                # the caller knows the page it asked for
            "items_per_page": LISTING_PAGE_SIZE,
            "total_pages": total_pages,
            "total_count": _int(meta.get("totalCount")),
        },
    }


def parse_category_tree(html, country=DEFAULT_MARKET):
    """A category page -> the node with its ancestors and children."""
    bx = boxes(html)
    filters_box = _filters_box(bx)
    tree = (filters_box or {}).get("categories")
    if not isinstance(tree, dict) or not tree.get("id"):
        raise ValueError("no category tree on the page")
    node = _category_node(tree, country)
    node["path"] = _category_path(_nav_box(bx), country)
    node["subcategories"] = [_category_node(s, country) for s in tree.get("subcategories") or []]
    return node


def parse_sitemap_children(html, country=DEFAULT_MARKET):
    """/mapa-strony/<department>: the department's direct children are the
    one allegro.navigation.links box whose links carry the /kategoria
    prefix (names + aliases only; the site publishes no ids or counts
    there)."""
    for box in boxes(html):
        if not (isinstance(box, dict) and box.get("prototypeName") == "allegro.navigation.links"):
            continue
        prefix = box.get("prefix") or ""
        items = [i for i in box.get("items") or [] if isinstance(i, dict) and i.get("url")]
        if prefix.rstrip("/") != "/kategoria" or not items:
            continue
        out = []
        for item in items:
            alias = (prefix.rstrip("/") + item["url"]).split("/kategoria/", 1)[-1].strip("/")
            tail = alias.rsplit("-", 1)[-1]
            out.append({"id": tail if tail.isdigit() else None, "name": _text(item.get("name")), "alias": alias,
                        "link": f"{host(country)}/kategoria/{alias}", "offers_count": None, "has_children": None})
        return out
    raise ValueError("no category map on the page")


# ---- seller pages ----------------------------------------------------------------

_SELLER_HEADER_RE = re.compile(
    r'data-prototype-id="allegro\.userInfo".*?<h1[^>]*>(.*?)</h1>(.*?)</div>', re.S)
_COUNTER_RE = re.compile(r'data-role="counter-value"[^>]*>(.*?)</span>', re.S)
_TESTID_RE = r'data-testid="{}"[^>]*>(.*?)</{}>'


def parse_seller_header(html):
    """The allegro.userInfo header: login, account kind label, offer count."""
    m = _SELLER_HEADER_RE.search(html or "")
    if not m:
        return {"login": None, "kind": None, "offers_count": None}
    login = _text(m.group(1))
    tail = m.group(2)
    kind = None
    km = re.search(r"<span[^>]*>([^<]+)</span>", tail)
    if km:
        kind = _text(km.group(1))
    cm = _COUNTER_RE.search(tail)
    return {"login": login, "kind": kind, "offers_count": _count_from_label(_text(cm.group(1))) if cm else None}


def _testid(html, name, close="span"):
    """Text of the first element carrying data-testid=`name`, read up to
    its closing `close` tag (the summary's blocks nest spans inside divs)."""
    m = re.search(_TESTID_RE.format(re.escape(name), close), html or "", re.S)
    return _text(m.group(1)) if m else None


def parse_seller_ratings_page(html, country=DEFAULT_MARKET):
    """/uzytkownik/<login>/oceny -> {seller_id, login, kind, summary, ratings}."""
    bx = boxes(html)
    box = find_box(bx, "sellerId", "ratings")
    if box is None:
        raise ValueError("no ratings box on the page")
    header = parse_seller_header(html)
    account = _testid(html, "account-details", close="div")
    removed = _testid(html, "removed-and-excluded-ratings-detailed", close="div")
    excluded = None
    if removed:
        em = re.search(r"(\d[\d\s ]*)\s+ocen[a-z]*\s+wykluczon", removed)
        excluded = _count_from_label(em.group(1)) if em else None
    summary = {
        "recommended_percent": _num(_testid(html, "recommended-percentage", close="h3")),
        "positive_count": _count_from_label(_testid(html, "recommended-total")),
        "negative_count": _count_from_label(_testid(html, "not-recommended-total")),
        "period": "last_12_months",
        "on_allegro_since_label": account.replace("na Allegro", "").strip() if account else None,
        "removed_ratings_count": _count_from_label(removed) if removed and "usuni" in removed else None,
        "excluded_ratings_count": excluded,
    }
    ratings = box.get("ratings") or {}
    return {
        "seller_id": box.get("sellerId"),
        "login": header["login"],
        "kind": header["kind"],
        "summary": summary,
        "ratings": parse_seller_ratings_json(ratings, country),
    }


def _rating(r, country):
    return {
        "id": r.get("id"),
        "is_recommended": r.get("recommended"),
        "comment": _text(r.get("comment")) if isinstance(r.get("comment"), str) else _text((r.get("comment") or {}).get("content")) if isinstance(r.get("comment"), dict) else None,
        "justifications": r.get("justifications") or [],
        "offers": [{"id": o.get("id"), "title": _text(o.get("title")),
                    "link": clean_offer_link(o.get("url"), o.get("id"), country)}
                   for o in r.get("offers") or [] if isinstance(o, dict)],
        "created_at": r.get("creationDate"),
        "updated_at": r.get("lastChangeDate"),
        "is_rated_again": r.get("ratedAgain"),
        "is_excluded": r.get("excluded"),
        "exclusion_reason": r.get("exclusionReason") or r.get("excludedReason"),
        "seller_reply": _text((r.get("sellerReply") or r.get("response") or {}).get("content"))
        if isinstance(r.get("sellerReply") or r.get("response"), dict) else None,
    }


def parse_seller_ratings_json(payload, country=DEFAULT_MARKET):
    """edge /ratings-api/sellers/<id>/ratings (or the page box's `ratings`)."""
    payload = payload or {}
    pageable = payload.get("pageable") or {}
    return {
        "results": [_rating(r, country) for r in payload.get("content") or [] if isinstance(r, dict)],
        "page": (_int(pageable.get("pageNumber")) or _int(payload.get("number")) or 0) + 1,
        "items_per_page": _int(pageable.get("pageSize")) or _int(payload.get("size")) or RATINGS_PAGE_SIZE,
        "total_pages": _int(payload.get("totalPages")),
        "total_count": _int(payload.get("totalElements")),
    }


# ---- offer / product pages -------------------------------------------------------

def _facade_box(boxes_):
    return find_box(boxes_, "facade", "reviews")


def _price_box(boxes_):
    return find_box(boxes_, "price", "transactionSection", "schema")


def _parameters(params):
    out = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        values = [v.get("valueLabel") for v in p.get("values") or [] if isinstance(v, dict) and v.get("valueLabel")]
        out.append({"id": p.get("id"), "name": p.get("name"), "values": values,
                    "is_shown_on_listing": (p.get("display") or {}).get("listing")})
    return out


def _description(descriptions):
    sections = ((descriptions or {}).get("standardized") or {}).get("sections") or []
    items, text_parts = [], []
    for section in sections:
        for item in (section or {}).get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "IMAGE":
                items.append({"type": "image", "link": item.get("url"), "alt": item.get("alt")})
            else:
                content = item.get("content") or ""
                items.append({"type": "text", "html": content})
                text = _text(content)
                if text:
                    text_parts.append(text)
    return {"items": items, "text": "\n".join(text_parts) or None}


def _seller_description(main):
    """The seller's "about" text: a plain string on some pages, {"text": ...}
    (HTML) on others (offer page of TylkoOryginalna, 2026-10-26)."""
    if isinstance(main, dict):
        main = main.get("text") or main.get("content")
    return _text(main) if isinstance(main, str) else None


def _seller(seller, country):
    if not isinstance(seller, dict) or not seller:
        return None
    company = seller.get("company") or {}
    address = company.get("address") or {}
    ratings = ((seller.get("ratings") or {}).get("lastYear")) or {}
    contact = seller.get("contact") or {}
    login = seller.get("login")
    return {
        "id": seller.get("id"),
        "login": login,
        "name": seller.get("name"),
        "link": (seller.get("listing") or {}).get("url") or (seller_link(login, country) if login else None),
        "is_company": bool(company) or None,
        "is_super_seller": (seller.get("superSeller") or {}).get("active") if isinstance(seller.get("superSeller"), dict) else seller.get("superSeller"),
        "logo": seller.get("logotype") if isinstance(seller.get("logotype"), str) else (seller.get("logotype") or {}).get("url") if isinstance(seller.get("logotype"), dict) else None,
        "ratings": {
            "period": "last_12_months",
            "positive_count": (ratings.get("positive") or {}).get("count"),
            "positive_percent": _num((ratings.get("positive") or {}).get("percentage")),
            "negative_count": (ratings.get("negative") or {}).get("count"),
            "negative_percent": _num((ratings.get("negative") or {}).get("percentage")),
        } if ratings else None,
        "company": {
            "name": company.get("name"),
            "representative": company.get("representativeLabel"),
            "street": address.get("street"),
            "postal_code": address.get("zipCode"),
            "city": address.get("city"),
            "country": address.get("country"),
            "country_code": address.get("countryCode"),
            "tax_id": company.get("taxIdentificationNumber"),
            "court_register_number": company.get("nationalCourtRegisterNumber"),
            "statistical_number": company.get("statisticalIdentificationNumber"),
            "is_verified": company.get("verified"),
        } if company else None,
        "contact": {
            "phones": [p.get("number") if isinstance(p, dict) else p for p in contact.get("phones") or []],
            "emails": [e.get("address") if isinstance(e, dict) else e for e in contact.get("emails") or []],
            "opening_hours": [{"days": h.get("daysLabel"), "hours": h.get("hoursLabels") or []}
                              for h in contact.get("openHours") or [] if isinstance(h, dict)],
        } if contact else None,
        "epr_registrations": [{"name": r.get("name"), "value": r.get("value")}
                              for r in seller.get("eprRegistrations") or [] if isinstance(r, dict)],
        "description": _seller_description((seller.get("descriptions") or {}).get("main")),
    }


def _delivery_methods(shipping):
    groups = ((shipping or {}).get("delivery") or {}).get("groups") or []
    out = []
    for group in groups:
        for m in (group or {}).get("deliveryMethods") or []:
            if not isinstance(m, dict):
                continue
            first = (m.get("firstItemCost") or {}).get("price")
            nxt = (m.get("nextItemCost") or {}).get("price")
            discounted = m.get("discountedPrice") or {}
            out.append({
                "name": m.get("name"),
                "group": group.get("name"),
                "country_code": group.get("countryCode"),
                "is_abroad": group.get("abroad"),
                "first_item_cost": _money(first),
                "next_item_cost": _money(nxt),
                "smart_label": _text((discounted.get("label") or {}).get("text")) if discounted else None,
                "smart_condition": _text((discounted.get("additionalInfo") or {}).get("text")) if discounted else None,
                "delivery_time": _text(m.get("deliveryTimeLabel")),
                "max_items_per_package": m.get("packageSize"),
                "has_free_return": m.get("freeReturn"),
                "is_personal_pickup": m.get("personal"),
            })
    return out


def _delivery_summary(delivery):
    out = []
    for row in (delivery or {}).get("summary") or []:
        if not isinstance(row, dict):
            continue
        name = _text((row.get("name") or {}).get("text"))
        value = _text((row.get("value") or {}).get("text")) if isinstance(row.get("value"), dict) else None
        out.append({"label": name, "value": value, "tag": row.get("analyticTag")})
    return out


def _rating_block(product):
    rating = (product or {}).get("rating") or {}
    average = rating.get("averageRating") or {}
    distribution = {}
    for row in rating.get("scoreStats") or []:
        if isinstance(row, dict) and row.get("score") is not None:
            distribution[str(row["score"])] = row.get("count")
    if not rating:
        return None
    return {
        "average": _num(average.get("value")),
        "label": average.get("title"),
        "count": rating.get("count"),
        "removed_count": rating.get("deletedCount"),
        "distribution": distribution or None,
    }


def _review(op):
    rating = op.get("rating") or {}
    helpful = op.get("helpfulness") or {}
    return {
        "id": op.get("id"),
        "author": (op.get("author") or {}).get("name"),
        "rating": _num(rating.get("label")) if rating.get("label") is not None else None,
        "text": _text(op.get("opinion")),
        "pros": _text(op.get("pros")),
        "cons": _text(op.get("cons")),
        "images": [i.get("url") if isinstance(i, dict) else i for i in op.get("images") or []],
        "created_at": op.get("createdAt"),
        "helpful_count": (helpful.get("positive") or {}).get("count"),
        "unhelpful_count": (helpful.get("negative") or {}).get("count"),
        "language": op.get("sourceLanguage"),
        "seller_login": (op.get("seller") or {}).get("login"),
        "source": op.get("sourceType"),
        "is_best": "BEST" in (op.get("flags") or []),
        "product_variant": op.get("productVariant") or [],
    }


def _features(features):
    out = []
    for f in features or []:
        if not isinstance(f, dict):
            continue
        counts = (f.get("mentions") or {}).get("count") or {}
        out.append({"label": f.get("label"), "sentiment": (f.get("sentiment") or "").lower() or None,
                    "mentions": counts.get("total"), "positive": counts.get("positive"),
                    "negative": counts.get("negative"), "neutral": counts.get("neutral")})
    return out


def parse_product_reviews_json(payload):
    """edge /product-reviews or the page's `reviews` block."""
    payload = payload or {}
    pagination = payload.get("pagination") or {}
    return {
        "results": [_review(op) for op in payload.get("opinions") or [] if isinstance(op, dict)],
        "features": _features(payload.get("features")),
        "page": _int(pagination.get("currentPage")) or 1,
        "items_per_page": REVIEWS_PAGE_SIZE,
        "total_pages": _int(pagination.get("totalPages")) or 0,
        "total_count": _int(payload.get("count")),
    }


def _price_block(facade, price_box):
    buy_now = ((facade.get("sellingMode") or {}).get("buyNow")) or {}
    price = buy_now.get("price") or {}
    sale = price.get("sale") or {}
    original = price.get("original") or {}
    schema = (price_box or {}).get("schema") or {}
    amount = _first(_num(sale.get("amount")), _num(schema.get("price")))
    currency = _first(sale.get("currency"), schema.get("priceCurrency"), (facade.get("sellingMode") or {}).get("currency"))
    return {
        "amount": amount,
        "currency": currency,
        "original_amount": _num(original.get("amount")) if original else None,
        "discount": buy_now.get("discount") if not isinstance(buy_now.get("discount"), dict) else _text((buy_now.get("discount") or {}).get("label")),
        "per_unit": _text(sale.get("pricePerUnit")) if isinstance(sale.get("pricePerUnit"), str) else None,
        "net_amount": _num((buy_now.get("netPrice") or {}).get("amount")) if isinstance(buy_now.get("netPrice"), dict) else None,
        "is_buy_now": buy_now.get("active"),
        "is_cart_available": ((facade.get("sellingMode") or {}).get("cart") or {}).get("active"),
    }


def _auction_block(facade, price_box):
    auction = (facade.get("sellingMode") or {}).get("auction")
    bidding = (price_box or {}).get("biddingSection") or {}
    if not auction and not bidding.get("visible"):
        return None
    auction = auction or {}
    return {
        "current_price": _money(auction.get("currentPrice") or auction.get("price")) or
                         ({"amount": _num((bidding.get("currentPrice") or {}).get("formatted")), "currency": None}
                          if bidding.get("currentPrice") else None),
        "bids_count": _first(auction.get("bidsCount"), auction.get("bids")),
        "has_bids": bidding.get("hasBids"),
        "ending_at": _first(auction.get("endingAt"), bidding.get("endingDate")),
        "minimum_bid": _money(auction.get("minimalPrice") or auction.get("nextPrice")),
    }


def parse_offer(html, country=DEFAULT_MARKET):
    """An /oferta/<id> or /produkt/<uuid> page -> one full record of the
    offer, its product and its seller (variant "product" pages carry a
    representative offer)."""
    bx = boxes(html)
    box = _facade_box(bx)
    if box is None:
        raise ValueError("no offer facade on the page")
    facade = box.get("facade") or {}
    reviews = box.get("reviews") or {}
    price_box = _price_box(bx)
    transaction = (price_box or {}).get("transactionSection") or {}
    quantity = transaction.get("availableQuantity") or {}
    limits = transaction.get("purchaseLimits") or {}
    view = facade.get("view") or {}
    seo = facade.get("seo") or {}
    product = facade.get("product") or {}
    publication = facade.get("publication") or {}
    popularity = facade.get("popularity") or {}
    location = facade.get("location") or {}
    category = facade.get("category") or {}
    warranty = facade.get("warranty") or {}
    implied = facade.get("impliedWarranty") or {}
    returns = facade.get("returnPolicy") or {}
    shipping = facade.get("shipping") or {}
    product_id = product.get("id")
    if not product_id:
        m = re.search(r"/produkt/(?:[^/?#]*?-)?([0-9a-f-]{36})", view.get("productUrl") or "")
        product_id = m.group(1) if m else None
    status = (view.get("type") or "").lower() or None
    offer_id = facade.get("id")
    marketplace = box.get("marketplace") or {}
    return {
        "id": offer_id,
        "name": _text(facade.get("name")),
        "link": view.get("offerUrl") or (clean_offer_link(None, offer_id, country) if offer_id else None),
        "status": status,
        "ended_message": _text(((view.get("ended") or {}).get("message") or {}).get("title")) if view.get("ended") else None,
        "price": _price_block(facade, price_box),
        "auction": _auction_block(facade, price_box),
        "stock": {
            "available_quantity": _int(quantity.get("value")),
            "unit": quantity.get("type"),
            "purchase_limit": _int(limits.get("quantityLimit")),
        },
        "sold": {
            "buyers_last_30_days": popularity.get("buyersQuantity"),
            "label": popularity.get("label"),
        },
        "condition": seo.get("condition"),
        "brand": _first(seo.get("brandName"), facade.get("brand") if isinstance(facade.get("brand"), str) else None),
        "gtin": seo.get("gtin"),
        "is_recommerce": seo.get("isRecommerce"),
        "category": {
            "id": category.get("id"),
            "name": category.get("name"),
            "path": [{"id": c.get("id"), "name": c.get("name")} for c in facade.get("assortmentCategoryPath") or [] if isinstance(c, dict)],
        },
        "breadcrumbs": [{"id": b.get("id"), "name": b.get("name"), "link": b.get("url"), "type": (b.get("type") or "").lower() or None}
                        for b in facade.get("breadcrumbs") or [] if isinstance(b, dict)],
        "parameters": _parameters(facade.get("parameters")),
        "description": _description(facade.get("descriptions")),
        "images": [i.get("url") for i in facade.get("images") or [] if isinstance(i, dict) and i.get("url")],
        "attachments": [a.get("url") if isinstance(a, dict) else a for a in facade.get("attachments") or []],
        "product": {
            "id": product_id,
            "name": _text(product.get("name")),
            "link": product_link(product_id, country) if product_id else None,
            "offers_link": (product.get("listing") or {}).get("url") if isinstance(product.get("listing"), dict) else None,
            "brand": product.get("brand") if isinstance(product.get("brand"), str) else _text((product.get("brand") or {}).get("name")) if isinstance(product.get("brand"), dict) else None,
            "images": [i.get("url") for i in product.get("images") or [] if isinstance(i, dict) and i.get("url")],
            "rating": _rating_block(product),
            "buyers_last_30_days": (product.get("popularity") or {}).get("buyersQuantity"),
            "reviews_count": (product.get("reviews") or {}).get("count"),
        } if product_id else None,
        "reviews": parse_product_reviews_json(reviews) if reviews else None,
        "seller": _seller(facade.get("seller"), country),
        "delivery": {
            "handling_time": _text(shipping.get("handlingTimeLabel")),
            "price_with_delivery_label": _text(shipping.get("priceWithDeliveryLabel")),
            "is_dispatched_abroad": shipping.get("foreignCountryOfDispatch"),
            "summary": _delivery_summary(facade.get("delivery")),
            "methods": _delivery_methods(shipping),
            "has_smart": bool(facade.get("freebox")),
        },
        "returns": {
            "summary": _text(returns.get("subtitle")),
            "withdrawal_period": returns.get("withdrawalPeriodLabel"),
            "restriction": _text(returns.get("restrictionCauseLabel")),
            "cost_covered_by": _text((returns.get("returnCost") or {}).get("coveredByLabel")),
        } if returns else None,
        "warranty": {
            "summary": _text(warranty.get("subtitle")),
            "period": warranty.get("individualPeriodLabel"),
            "type": warranty.get("typeLabel"),
            "implied_period": implied.get("individualPeriodLabel"),
        } if (warranty or implied) else None,
        "location": {
            "city": location.get("city"),
            "province": location.get("province"),
            "country": location.get("country"),
            "country_code": location.get("countryCode"),
        } if location else None,
        "publication": {
            "started_at": publication.get("startingAt"),
            "ending_at": publication.get("endingAt"),
            "ended_at": publication.get("endedAt"),
        },
        "marketplace": marketplace.get("id"),
        "info_boxes": [{"id": b.get("id"), "title": _text((b.get("title") or {}).get("text")),
                        "text": _first(*_label_parts_text(b.get("labels")))}
                       for b in facade.get("infoBoxes") or [] if isinstance(b, dict)],
    }


# ---- edge JSON: suggestions --------------------------------------------------------

def parse_suggestions(payload, country=DEFAULT_MARKET):
    """edge /search-suggester/suggestions -> phrase + tile suggestions."""
    out = []
    for group in (payload or {}).get("suggestions") or []:
        if not isinstance(group, dict):
            continue
        entries = group.get("items") if isinstance(group.get("items"), list) else [group]
        group_type = (group.get("type") or "").lower() if group.get("items") is not None else None
        for item in entries:
            if not isinstance(item, dict):
                continue
            view = item.get("view") or {}
            label = _text(" ".join(p.get("text") or "" for p in view.get("labelItems") or [] if isinstance(p, dict)))
            action = item.get("action") or {}
            url = item.get("url")
            out.append({
                "text": _first(item.get("completionText"), action.get("query"), label),
                "label": label,
                "link": (host(country) + url) if url and url.startswith("/") else url,
                "type": (item.get("type") or group_type or "suggestion").lower(),
                "action": (action.get("type") or "").lower() or None,
                "image": (view.get("image") or {}).get("url"),
                "category": ({"id": item["category"].get("id"), "name": item["category"].get("name")}
                             if isinstance(item.get("category"), dict) else None),
            })
    return out
