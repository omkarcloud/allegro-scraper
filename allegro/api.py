"""The /allegro/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs).

Caching (cache.cached_call, keyed on the validated params):
  * one upstream page = one cache row; the seller record (storefront
    header + ratings page) is cached once under allegro.seller and sliced by
    sellers/details and sellers/ratings (the ratings call needs the numeric
    seller id that only the ratings page carries), so a client hitting both
    pays the two page fetches once.
  * paged endpoints return a `pagination` block for route_glue.paginate.
"""
from cache import cached_call
from allegro import cache_config as ttl
from allegro import parsers
from allegro import fetch
from allegro.fetch import AllegroNotFound
from allegro.refs import (DEPARTMENTS, category_link, host, product_link, product_offers_link, seller_link,
                          seller_ratings_link)

_FILTER_KEYS = ("page", "sort", "min_price", "max_price", "condition", "buy_now", "smart", "super_seller")


def _filters(data):
    return {k: data.get(k) for k in _FILTER_KEYS if data.get(k) is not None}


def _paged_listing(parsed, page, served=True):
    """Stamp the requested page; a page Allegro did not serve (it redirects
    past-the-end pages to the first one) is an empty page, not page 1 again."""
    parsed["pagination"]["page"] = page
    if not served or (parsed["pagination"]["total_pages"] and page > parsed["pagination"]["total_pages"]):
        parsed["results"] = []
    return parsed


# ---- search/suggestions -------------------------------------------------------------

def _suggestions(query, country):
    results = parsers.parse_suggestions(fetch.fetch_suggestions(query, country), country)
    return {"query": query, "country": country, "count": len(results), "results": results}


def search_suggestions(**data):
    return cached_call("allegro.suggestions", data, _suggestions, ttl.SUGGESTIONS_CACHE)


# ---- offers/search -----------------------------------------------------------------

def _offers_search(query, category, country, **filters):
    page = filters.get("page", 1)
    if category:
        html, served = fetch.fetch_category_listing(category, country, query=query, **filters)
    else:
        html, served = fetch.fetch_search(query, country, **filters)
    return _paged_listing(parsers.parse_listing(html, country), page, served)


def offers_search(**data):
    return cached_call("allegro.search", data, _offers_search, ttl.LISTING_CACHE)


# ---- offers/details ----------------------------------------------------------------

def _offer_details(offer, country):
    return parsers.parse_offer(fetch.fetch_offer(offer, country), country)


def offers_details(**data):
    return cached_call("allegro.offer", data, _offer_details, ttl.OFFER_CACHE)


# ---- products/details --------------------------------------------------------------

def _product_details(product, country):
    record = parsers.parse_offer(fetch.fetch_product(product, country), country)
    block = record.pop("product", None) or {}
    product_id = block.get("id") or product
    reviews = record.pop("reviews", None)
    return {
        "id": product_id,
        "name": block.get("name") or record.get("name"),
        "link": product_link(product_id, country),
        "offers_link": product_offers_link(product_id, country),
        "brand": block.get("brand") or record.get("brand"),
        "gtin": record.get("gtin"),
        "category": record.get("category"),
        "images": block.get("images") or record.get("images"),
        "rating": block.get("rating"),
        "reviews_count": block.get("reviews_count"),
        "buyers_last_30_days": block.get("buyers_last_30_days"),
        "parameters": record.get("parameters"),
        "reviews": reviews,
        # the offer Allegro shows first for this product (price, stock, seller, delivery)
        "representative_offer": record,
    }


def products_details(**data):
    return cached_call("allegro.product", data, _product_details, ttl.OFFER_CACHE)


# ---- products/offers ---------------------------------------------------------------

def _product_offers(product, country, **filters):
    page = filters.get("page", 1)
    html, served = fetch.fetch_product_offers(product, country, **filters)
    parsed = parsers.parse_listing(html, country)
    parsed.pop("query", None)
    return {"product": {"id": product, "link": product_link(product, country)}, **_paged_listing(parsed, page, served)}


def products_offers(**data):
    return cached_call("allegro.product_offers", data, _product_offers, ttl.LISTING_CACHE)


# ---- products/reviews --------------------------------------------------------------

def _product_reviews(product, page, rating, country):
    payload = fetch.fetch_product_reviews(product, country, page=page, rating=rating)
    parsed = parsers.parse_product_reviews_json(payload)
    results = parsed.pop("results")
    features = parsed.pop("features")
    parsed["page"] = page
    return {
        "product": {"id": product, "link": product_link(product, country)},
        "rating_filter": rating,
        "features": features,
        "results": results,
        "pagination": {"page": page, "items_per_page": parsed["items_per_page"],
                       "total_pages": parsed["total_pages"], "total_count": parsed["total_count"]},
    }


def products_reviews(**data):
    return cached_call("allegro.reviews", data, _product_reviews, ttl.REVIEWS_CACHE)


# ---- the shared seller record ------------------------------------------------------

def _seller_record(seller, country):
    """Ratings page (numeric id, summary, first ratings page) + storefront
    header (kind, offer count, first storefront page stats)."""
    ratings_page = parsers.parse_seller_ratings_page(fetch.fetch_seller_ratings_page(seller, country), country)
    storefront_html, _ = fetch.fetch_seller_listing(seller, country)
    header = parsers.parse_seller_header(storefront_html)
    listing = parsers.parse_listing(storefront_html, country)
    return {
        "seller_id": ratings_page["seller_id"],
        "login": ratings_page["login"] or header["login"] or seller,
        "kind": ratings_page["kind"] or header["kind"],
        "summary": ratings_page["summary"],
        "offers_count": header["offers_count"] if header["offers_count"] is not None else listing["stats"]["total_count"],
        "ratings_total": ratings_page["ratings"]["total_count"],
        "categories": (listing.get("category") or {}).get("subcategories") or [],
    }


def _record(seller, country):
    return cached_call("allegro.seller", {"seller": seller, "country": country}, _seller_record, ttl.SELLER_CACHE)


# ---- sellers/details ---------------------------------------------------------------

def _seller_details(seller, country):
    record = _record(seller, country)
    login = record["login"]
    return {
        "id": record["seller_id"],
        "login": login,
        "link": seller_link(login, country),
        "ratings_link": seller_ratings_link(login, country),
        "is_company": record["kind"] == "firma" if record["kind"] else None,
        "kind": record["kind"],
        "offers_count": record["offers_count"],
        "ratings": {**(record["summary"] or {}), "total_count": record["ratings_total"]},
        "offer_categories": record["categories"],
    }


def sellers_details(**data):
    return _seller_details(**data)


# ---- sellers/offers ----------------------------------------------------------------

def _seller_offers(seller, query, country, **filters):
    page = filters.get("page", 1)
    html, served = fetch.fetch_seller_listing(seller, country, query=query, **filters)
    header = parsers.parse_seller_header(html)
    parsed = _paged_listing(parsers.parse_listing(html, country), page, served)
    return {"seller": {"login": header["login"] or seller, "link": seller_link(header["login"] or seller, country),
                       "kind": header["kind"], "offers_count": header["offers_count"]},
            **parsed}


def sellers_offers(**data):
    return cached_call("allegro.seller_offers", data, _seller_offers, ttl.LISTING_CACHE)


# ---- sellers/ratings ---------------------------------------------------------------

def _seller_ratings(seller, page, recommended, country):
    record = _record(seller, country)
    seller_id, login = record["seller_id"], record["login"]
    if not seller_id:
        raise AllegroNotFound(f"seller {seller!r} has no ratings page")
    payload = fetch.fetch_seller_ratings(seller_id, login, country, page=page, recommended=recommended)
    parsed = parsers.parse_seller_ratings_json(payload, country)
    return {
        "seller": {"id": seller_id, "login": login, "link": seller_link(login, country)},
        "summary": record["summary"],
        "recommended_filter": recommended,
        "results": parsed["results"],
        "pagination": {"page": page, "items_per_page": parsed["items_per_page"],
                       "total_pages": parsed["total_pages"], "total_count": parsed["total_count"]},
    }


def sellers_ratings(**data):
    return cached_call("allegro.seller_ratings", data, _seller_ratings, ttl.RATINGS_CACHE)


# ---- categories/list ---------------------------------------------------------------

def _categories(category, country):
    if not category:
        return {
            "id": None, "name": "Allegro", "alias": "/", "link": host(country), "path": [],
            "subcategories": [{"id": d["id"], "name": d["name"], "alias": d["alias"],
                               "link": category_link(d["alias"], country), "offers_count": None,
                               "has_children": True} for d in DEPARTMENTS],
        }
    html, final_url = fetch.fetch_category_page(category, country)
    if "/dzial/" not in (final_url or ""):
        return parsers.parse_category_tree(html, country)
    # a department alias ("elektronika") lands on its marketing page; its
    # children are on the department's sitemap page (names + aliases only)
    alias = final_url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
    department = next((d for d in DEPARTMENTS if d["alias"] == alias), None)
    return {
        "id": department["id"] if department else None,
        "name": department["name"] if department else alias,
        "alias": alias,
        "link": category_link(alias, country),
        "path": [{"id": None, "name": "Allegro", "alias": "/", "link": host(country)}],
        "subcategories": parsers.parse_sitemap_children(fetch.fetch_sitemap(alias, country), country),
    }


def categories_list(**data):
    return cached_call("allegro.categories", data, _categories, ttl.CATEGORIES_CACHE)
