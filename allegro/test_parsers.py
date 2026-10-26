"""Offline tests for the Allegro parsers, reference resolvers and value
helpers.

    python -m pytest allegro/test_parsers.py -q

Fixtures are real allegro.pl / allegro.cz pages captured 2026-10-23
(allegro/fixtures/, gzipped): a search listing (page 2), a category page
with and without filters, an ENDED offer page, a product page, the
product's /oferty-produktu/ page, a seller storefront and ratings page, the
404 page, the "użytkownik nieznaleziony" page, the DataDome 403 and
Allegro-captcha 429 bodies, an ended-offers listing, an allegro.cz category
page and the three edge JSON payloads. No network.
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from allegro import parsers as P, refs  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    path = os.path.join(FX, name)
    if name.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


@pytest.fixture(scope="module")
def listing():
    return P.parse_listing(fixture("listing_search_p2.html.gz"))


@pytest.fixture(scope="module")
def category():
    return P.parse_listing(fixture("category_165.html.gz"))


@pytest.fixture(scope="module")
def offer():
    return P.parse_offer(fixture("offer_ended_18900338789.html.gz"))


@pytest.fixture(scope="module")
def product():
    return P.parse_offer(fixture("product_3a7c61de.html.gz"))


# ---- refs ----------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("18900338789", "18900338789"),
    ("https://allegro.pl/oferta/filtr-oleju-bosch-wklad-diesel-66-mm-x-106-mm-18900338789", "18900338789"),
    ("https://allegro.pl/oferta/18900338789?bi_s=ads", "18900338789"),
    ("https://allegro.pl/produkt/bosch-3a7c61de-9af0-4d0d-b4b3-17c21650e362?offerId=18553287646", "18553287646"),
    ("//allegro.cz/oferta/x-18832750115", "18832750115"),
])
def test_resolve_offer(value, expected):
    assert refs.resolve_offer(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "https://example.com/oferta/18900338789",
                                   "https://allegro.pl/produkt/3a7c61de-9af0-4d0d-b4b3-17c21650e362"])
def test_resolve_offer_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_offer(value)


@pytest.mark.parametrize("value,expected", [
    ("3A7C61DE-9AF0-4D0D-B4B3-17C21650E362", "3a7c61de-9af0-4d0d-b4b3-17c21650e362"),
    ("https://allegro.pl/produkt/bosch-filtr-3a7c61de-9af0-4d0d-b4b3-17c21650e362", "3a7c61de-9af0-4d0d-b4b3-17c21650e362"),
    ("https://allegro.pl/oferty-produktu/3a7c61de-9af0-4d0d-b4b3-17c21650e362?p=2", "3a7c61de-9af0-4d0d-b4b3-17c21650e362"),
    ("https://allegro.pl/produkt/x-3a7c61de-9af0-4d0d-b4b3-17c21650e362?offerId=1", "3a7c61de-9af0-4d0d-b4b3-17c21650e362"),
])
def test_resolve_product(value, expected):
    assert refs.resolve_product(value) == expected


@pytest.mark.parametrize("value", ["", "18900338789", "https://allegro.pl/oferta/18900338789"])
def test_resolve_product_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("Auto_Prima", "Auto_Prima"),
    ("https://allegro.pl/uzytkownik/Auto_Prima", "Auto_Prima"),
    ("https://allegro.pl/uzytkownik/Auto_Prima/oceny?page=2", "Auto_Prima"),
    ("https://allegro.pl/uzytkownik/x-kom/filtry-49239", "x-kom"),
])
def test_resolve_seller(value, expected):
    assert refs.resolve_seller(value) == expected


@pytest.mark.parametrize("value", ["", "a b", "https://allegro.pl/oferta/1", "https://allegro.pl/uzytkownik/notfound"])
def test_resolve_seller_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_seller(value)


@pytest.mark.parametrize("value,expected", [
    ("165", "165"),
    ("elektronika", "elektronika"),
    ("smartfony-i-telefony-komorkowe-165", "165"),
    ("https://allegro.pl/kategoria/smartfony-i-telefony-komorkowe-165?p=2", "165"),
    ("https://allegro.pl/kategoria/elektronika", "elektronika"),
    ("42540aec-367a-4e5e-b411-17c09b08e41f", "42540aec-367a-4e5e-b411-17c09b08e41f"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", ["", "https://allegro.pl/oferta/1", "https://example.com/kategoria/x-1", "a b c"])
def test_resolve_category_invalid(value):
    with pytest.raises(ValueError):
        refs.resolve_category(value)


def test_clean_offer_link():
    tracked = ("https://allegro.pl/events/clicks?emission_unit_id=x&redirect=https%3A%2F%2Fallegro.pl%2Foferta%2F"
               "16566093973%3Fbi_s%3Dads%26bi_m%3Dproductlisting&placement=p&sig=1")
    assert refs.clean_offer_link(tracked, "16566093973") == "https://allegro.pl/oferta/16566093973"
    assert refs.clean_offer_link(tracked, "16566093973", "cz") == "https://allegro.pl/oferta/16566093973"
    assert refs.clean_offer_link("https://allegro.cz/produkt/x-1?offerId=2&bi_s=a&navCategoryId=5", None, "cz") == \
        "https://allegro.cz/produkt/x-1?offerId=2"


# ---- value helpers ---------------------------------------------------------------------

def test_num_and_counts():
    assert P._num("2389.00") == 2389.0
    assert P._num("98,9%") == 98.9
    assert P._num("1 512") == 1512.0
    assert P._num(None) is None and P._num("") is None and P._num(True) is None
    assert P._count_from_label("39 osób kupiło ostatnio") == 39
    assert P._count_from_label("9999+") == 9999
    assert P._count_from_label("1 512 ofert") == 1512
    assert P._count_from_label(None) is None
    assert P._money({"amount": "45.00", "currency": "PLN"}) == {"amount": 45.0, "currency": "PLN"}
    assert P._money(None) is None and P._money({"amount": None}) is None
    assert P._text("<b>a</b>&nbsp; b ") == "a b"


# ---- page kinds ----------------------------------------------------------------------

@pytest.mark.parametrize("name,kind", [
    ("offer_404.html.gz", "not_found"),
    ("seller_notfound.html.gz", "not_found"),
    ("datadome_403.html", "datadome"),
    ("allegro_captcha_429.html", "captcha"),
    ("listing_search_p2.html.gz", "page"),
    ("offer_ended_18900338789.html.gz", "page"),
])
def test_page_kind(name, kind):
    assert P.page_kind(fixture(name)) == kind


def test_page_kind_status_404():
    assert P.page_kind("<html><title>x</title></html>", 404) == "not_found"
    assert P.page_kind("", 200) == "page"


# ---- listings -------------------------------------------------------------------------

def test_listing_meta(listing):
    assert listing["query"] == "iphone 15"
    assert listing["sort"] == "relevance"
    assert listing["stats"]["total_count"] == 198414
    assert listing["pagination"] == {"page": None, "items_per_page": 60, "total_pages": 100, "total_count": 198414}
    assert listing["applied_filters"] == []
    assert listing["category"]["name"] == "Allegro"
    assert listing["category"]["subcategories"][0]["name"] == "Telefony i Akcesoria"
    assert listing["category"]["subcategories"][0]["offers_count"] == 9999


def test_listing_cards(listing):
    cards = listing["results"]
    assert len(cards) == 73
    assert {c["placement"] for c in cards} == {"regular", "promoted", "sponsored"}
    assert all(c["id"] and c["link"].startswith("https://allegro.pl/oferta/") for c in cards)
    sponsored = cards[0]
    assert sponsored["is_sponsored"] is True and sponsored["placement"] == "sponsored"
    assert sponsored["link"] == "https://allegro.pl/oferta/16566093973"      # the /events/clicks wrapper is gone
    assert sponsored["price"] == {"amount": 2389.0, "currency": "PLN"}
    assert sponsored["condition"] == "Powystawowy"
    assert sponsored["product"]["rating"] == 4.94 and sponsored["product"]["ratings_count"] == 105
    assert sponsored["product"]["buyers_last_30_days"] == 39
    assert sponsored["seller"]["login"] == "luxtrade-pl" and sponsored["seller"]["positive_feedback_percent"] == 97.4
    assert sponsored["delivery"]["estimate"] == "dostawa we wtorek"
    regular = next(c for c in cards if c["placement"] == "regular")
    assert regular["seller"]["is_super_seller"] is True
    assert regular["delivery"]["has_smart"] is True
    assert regular["product"]["offers_count"] == 10
    assert regular["images"] and all(i.startswith("https://") for i in regular["images"])
    assert "eventData" not in json.dumps(cards) and "analyticsId" not in json.dumps(cards)


def test_category_page(category):
    cat = category["category"]
    assert cat["id"] == "165" and cat["name"] == "Smartfony i telefony komórkowe"
    assert [p["name"] for p in cat["path"]] == ["Allegro", "Elektronika", "Telefony i Akcesoria", "Smartfony i telefony komórkowe"]
    assert "offers_count" not in cat["path"][0]
    assert len(cat["subcategories"]) == 35
    assert cat["subcategories"][1] == {"id": "48978", "name": "Apple", "alias": "smartfony-i-telefony-komorkowe-apple-48978",
                                       "link": "https://allegro.pl/kategoria/smartfony-i-telefony-komorkowe-apple-48978",
                                       "offers_count": 9999, "has_children": True}
    assert category["query"] is None
    tree = P.parse_category_tree(fixture("category_165.html.gz"))
    assert tree["id"] == "165" and len(tree["subcategories"]) == 35 and len(tree["path"]) == 4


def test_filtered_category_page():
    parsed = P.parse_listing(fixture("category_165_filtered.html.gz"))
    assert parsed["sort"] == "price_asc"
    assert {(f["key"], f["value"]) for f in parsed["applied_filters"]} == {("stan", "nowe"), ("price_from", "500"), ("price_to", "1500")}
    assert parsed["pagination"]["total_pages"] == 35
    prices = [c["price"]["amount"] for c in parsed["results"] if c["placement"] != "sponsored"]
    assert prices == sorted(prices)


def test_product_offers_listing():
    parsed = P.parse_listing(fixture("product_offers_3a7c61de.html.gz"))
    assert parsed["stats"]["total_count"] == 799 and parsed["pagination"]["total_pages"] == 14
    cards = parsed["results"]
    assert len(cards) == 62
    regular = next(c for c in cards if c["placement"] == "regular")
    assert regular["offer_type"] == "buyNow" and regular["quantity_available"] == 49
    assert regular["seller"]["positive_feedback_count"] == 4218


def test_seller_storefront():
    html = fixture("seller_auto_prima.html.gz")
    assert P.parse_seller_header(html) == {"login": "Auto_Prima", "kind": "firma", "offers_count": 1512}
    parsed = P.parse_listing(html)
    assert parsed["stats"]["total_count"] == 1512 and parsed["pagination"]["total_pages"] == 26
    assert len(parsed["results"]) == 60
    assert P.parse_seller_header("<html></html>") == {"login": None, "kind": None, "offers_count": None}


def test_ended_listing():
    parsed = P.parse_listing(fixture("ended_listing.html.gz"))
    assert parsed["results"] and all(c["is_ended"] for c in parsed["results"])


def test_cz_listing():
    parsed = P.parse_listing(fixture("cz_category_165.html.gz"), "cz")
    assert parsed["results"][0]["price"]["currency"] == "CZK"
    assert parsed["results"][0]["link"].startswith("https://allegro.cz/")
    assert parsed["category"]["name"] == "Smartphony a mobilní telefony"


def test_sitemap_children():
    children = P.parse_sitemap_children(fixture("sitemap_elektronika.html.gz"))
    assert [c["name"] for c in children] == ["Fotografia", "Komputery", "Konsole i automaty", "Roboty AI", "RTV i AGD",
                                             "Sprzęt estradowy, studyjny i DJ-ski", "Telefony i Akcesoria"]
    assert children[0]["link"] == "https://allegro.pl/kategoria/fotografia" and children[0]["id"] is None
    with pytest.raises(ValueError):
        P.parse_sitemap_children(fixture("offer_404.html.gz"))


def test_listing_without_state_raises():
    with pytest.raises(ValueError):
        P.parse_listing(fixture("offer_404.html.gz"))


# ---- offer / product pages ---------------------------------------------------------

def test_offer_identity_and_price(offer):
    assert offer["id"] == "18900338789"
    assert offer["name"] == "Filtr oleju Bosch wkład diesel 66 mm x 106 mm"
    assert offer["link"].endswith("-18900338789")
    assert offer["status"] == "ended" and offer["ended_message"] == "Sprzedaż zakończona"
    assert offer["price"]["amount"] == 45.0 and offer["price"]["currency"] == "PLN"
    assert offer["price"]["is_buy_now"] is False
    assert offer["auction"] is None
    assert offer["stock"]["available_quantity"] == 1
    assert offer["sold"]["buyers_last_30_days"] == 7
    assert offer["condition"] == "Nowy" and offer["brand"] == "Bosch" and offer["gtin"] == "4047024807570"
    assert offer["publication"]["ended_at"] == "2026-10-13T21:02:13Z"
    assert offer["marketplace"] == "allegro-pl"


def test_offer_category_and_parameters(offer):
    assert offer["category"]["id"] == "49239"
    assert [c["name"] for c in offer["category"]["path"]] == ["Allegro", "Motoryzacja", "Części samochodowe", "Filtry", "Filtry oleju"]
    assert offer["breadcrumbs"][-1]["link"] == "https://allegro.pl/kategoria/filtry-filtry-oleju-49239"
    assert offer["parameters"][0] == {"id": "11323", "name": "Stan", "values": ["Nowy"], "is_shown_on_listing": True}
    assert len(offer["images"]) == 16
    assert offer["description"]["items"][0]["type"] == "text"
    assert any(i["type"] == "image" and i["link"].startswith("https://") for i in offer["description"]["items"])
    assert "VIN" in offer["description"]["text"]


def test_seller_description_shapes():
    assert P._seller_description({"text": " <p>Jesteśmy <b>dystrybutorem</b></p> "}) == "Jesteśmy dystrybutorem"
    assert P._seller_description("plain text") == "plain text"
    assert P._seller_description(None) is None and P._seller_description({"x": 1}) is None


def test_offer_seller(offer):
    seller = offer["seller"]
    assert seller["id"] == "94972268" and seller["login"] == "Auto_Prima"
    assert seller["link"] == "https://allegro.pl/uzytkownik/Auto_Prima"
    assert seller["is_company"] is True and seller["is_super_seller"] is False
    assert seller["ratings"] == {"period": "last_12_months", "positive_count": 5214, "positive_percent": 98.9,
                                 "negative_count": 61, "negative_percent": 1.1}
    assert seller["company"]["tax_id"] == "5322049799" and seller["company"]["city"] == "Wiązowna"
    assert seller["contact"]["opening_hours"][0] == {"days": "poniedziałek - piątek", "hours": ["09:00–17:00"]}
    assert seller["epr_registrations"] == [{"name": "BDO", "value": "000530684"}]


def test_offer_delivery_returns_warranty(offer):
    delivery = offer["delivery"]
    assert delivery["handling_time"] == "natychmiast"
    assert delivery["methods"][0]["name"] == "Allegro One Box, Allegro One"
    assert delivery["methods"][0]["first_item_cost"] == {"amount": 10.49, "currency": "PLN"}
    assert delivery["methods"][0]["delivery_time"] == "wt. 27 paź. w punkcie"
    assert {m["group"] for m in delivery["methods"]} == {"Odbiór w punkcie", "Odbiór w punkcie za pobraniem", "Na adres", "Na adres za pobraniem"}
    assert delivery["summary"][0]["tag"] == "Smart"
    assert offer["returns"]["withdrawal_period"] == "14 dni"
    assert offer["warranty"]["period"] == "24 miesiące" and offer["warranty"]["implied_period"] == "2 lata"
    assert offer["location"] == {"city": "Wiązowna", "province": "mazowieckie", "country": "Polska", "country_code": "PL"}


def test_offer_product_and_reviews(offer):
    product = offer["product"]
    assert product["id"] == "3a7c61de-9af0-4d0d-b4b3-17c21650e362"
    assert product["link"] == "https://allegro.pl/produkt/3a7c61de-9af0-4d0d-b4b3-17c21650e362"
    assert product["rating"] == {"average": 4.94, "label": "Rewelacyjny", "count": 224, "removed_count": 0,
                                 "distribution": {"5": 213, "4": 8, "3": 3, "2": 0, "1": 0}}
    assert product["reviews_count"] == 25 and product["buyers_last_30_days"] == 27
    reviews = offer["reviews"]
    assert reviews["total_count"] == 25 and reviews["total_pages"] == 2 and len(reviews["results"]) == 20
    first = reviews["results"][0]
    assert first["rating"] == 5.0 and first["is_best"] is True and first["seller_login"] == "euro_parts_pl"
    assert first["created_at"] == "2025-12-16T20:16:05.485Z"
    assert reviews["features"][0] == {"label": "Dopasowanie", "sentiment": "positive", "mentions": 5,
                                      "positive": 4, "negative": 0, "neutral": 1}


def test_product_page(product):
    assert product["id"] == "18553287646" and product["status"] == "active"
    assert product["price"]["amount"] == 50.13 and product["price"]["is_buy_now"] is True
    assert product["stock"]["available_quantity"] == 999 and product["stock"]["unit"] == "UNIT"
    assert product["product"]["id"] == "3a7c61de-9af0-4d0d-b4b3-17c21650e362"
    assert product["seller"]["login"] == "BrumBrumSklep24"


def test_offer_page_without_facade_raises():
    with pytest.raises(ValueError):
        P.parse_offer(fixture("listing_search_p2.html.gz"))


def test_parse_offer_never_crashes_on_sparse_facade():
    sparse = '<script type="application/json" data-serialize-box-id="x">{"facade": {"id": "1"}, "reviews": {}}</script>'
    out = P.parse_offer(sparse)
    assert out["id"] == "1" and out["price"]["amount"] is None and out["seller"] is None
    assert out["product"] is None and out["reviews"] is None and out["delivery"]["methods"] == []


# ---- seller ratings ----------------------------------------------------------------

def test_seller_ratings_page():
    parsed = P.parse_seller_ratings_page(fixture("seller_auto_prima_ratings.html.gz"))
    assert parsed["seller_id"] == "94972268" and parsed["login"] == "Auto_Prima" and parsed["kind"] == "firma"
    assert parsed["summary"] == {"recommended_percent": 98.9, "positive_count": 5214, "negative_count": 61,
                                 "period": "last_12_months", "on_allegro_since_label": "od 5 lat i 10 miesięcy",
                                 "removed_ratings_count": 2, "excluded_ratings_count": 28}
    ratings = parsed["ratings"]
    assert ratings["total_count"] == 5275 and ratings["total_pages"] == 264 and ratings["page"] == 1
    assert len(ratings["results"]) == 20
    first = ratings["results"][0]
    assert first["is_recommended"] is True and first["justifications"] == ["Miła obsługa"]
    assert first["offers"][0]["link"] == "https://allegro.pl/oferta/18764107046"


def test_seller_ratings_json():
    parsed = P.parse_seller_ratings_json(fixture("seller_ratings_p2.json"))
    assert parsed["page"] == 2 and parsed["items_per_page"] == 20 and parsed["total_pages"] == 264
    assert len(parsed["results"]) == 20
    assert P.parse_seller_ratings_json({})["results"] == []


def test_seller_ratings_page_without_box_raises():
    with pytest.raises(ValueError):
        P.parse_seller_ratings_page(fixture("seller_notfound.html.gz"))


# ---- edge JSON -------------------------------------------------------------------------

def test_product_reviews_json():
    parsed = P.parse_product_reviews_json(fixture("product_reviews_p1.json"))
    assert parsed["total_count"] == 25 and parsed["total_pages"] == 2 and parsed["page"] == 1
    assert len(parsed["results"]) == 20 and len(parsed["features"]) == 5
    page2 = P.parse_product_reviews_json(fixture("product_reviews_p2.json"))
    assert page2["page"] == 2 and len(page2["results"]) == 5
    assert P.parse_product_reviews_json({"count": 0, "pagination": {"currentPage": 1, "totalPages": 0}, "opinions": []})["results"] == []


def test_suggestions():
    parsed = P.parse_suggestions(fixture("suggestions_iphone.json"))
    assert len(parsed) == 24
    tiles = [s for s in parsed if s["type"] == "carousel"]
    phrases = [s for s in parsed if s["type"] == "suggestion"]
    assert tiles[0]["text"] == "iphone 17" and tiles[0]["link"] == "https://allegro.pl/listing?string=iphone%2017"
    assert tiles[0]["image"].startswith("https://")
    assert phrases[0]["text"] == "iphone" and phrases[0]["action"] == "offer_list"
    assert P.parse_suggestions({}) == [] and P.parse_suggestions(None) == []
