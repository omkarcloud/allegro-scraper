"""Offline tests for the /allegro/* request schemas.

    python -m pytest allegro/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from allegro import schemas  # noqa: E402

PRODUCT = "3a7c61de-9af0-4d0d-b4b3-17c21650e362"


def _error(schema, data):
    with pytest.raises(ValidationError) as e:
        schema().load(data)
    return e.value.messages


def test_suggestions_schema():
    assert schemas.SuggestionsSchema().load({"query": " iphone "}) == {"query": "iphone", "country": "pl"}
    assert schemas.SuggestionsSchema().load({"query": "x", "country": "CZ"})["country"] == "cz"
    assert "query" in _error(schemas.SuggestionsSchema, {})
    assert "country" in _error(schemas.SuggestionsSchema, {"query": "x", "country": "de"})


def test_offers_search_schema_defaults():
    loaded = schemas.OffersSearchSchema().load({"query": "rower"})
    assert loaded == {"query": "rower", "category": None, "page": 1, "sort": None, "min_price": None,
                      "max_price": None, "condition": None, "buy_now": None, "smart": None,
                      "super_seller": None, "country": "pl"}


def test_offers_search_schema_filters():
    loaded = schemas.OffersSearchSchema().load({
        "category": "https://allegro.pl/kategoria/smartfony-i-telefony-komorkowe-165", "sort": "Price_Asc",
        "min_price": "500", "max_price": "1500.5", "condition": "NEW", "buy_now": "1", "smart": "yes",
        "super_seller": "false", "page": "35"})
    assert loaded["category"] == "165" and loaded["sort"] == "price_asc" and loaded["condition"] == "new"
    assert loaded["min_price"] == 500 and loaded["max_price"] == 1500.5
    assert loaded["buy_now"] is True and loaded["smart"] is True and loaded["super_seller"] is False
    assert loaded["page"] == 35


def test_offers_search_schema_rejects():
    assert "query" in _error(schemas.OffersSearchSchema, {})
    assert "page" in _error(schemas.OffersSearchSchema, {"query": "x", "page": "101"})
    assert "sort" in _error(schemas.OffersSearchSchema, {"query": "x", "sort": "cheapest"})
    assert "max_price" in _error(schemas.OffersSearchSchema, {"query": "x", "min_price": "10", "max_price": "5"})
    assert "condition" in _error(schemas.OffersSearchSchema, {"query": "x", "condition": "mint"})
    assert "category" in _error(schemas.OffersSearchSchema, {"category": "https://example.com/kategoria/x-1"})
    # a sibling id/url pair is rejected as an unknown field
    assert "url" in _error(schemas.OffersSearchSchema, {"query": "x", "url": "https://allegro.pl/listing"})


def test_offer_schema():
    assert schemas.OfferSchema().load({"offer": "18900338789"}) == {"offer": "18900338789", "country": "pl"}
    loaded = schemas.OfferSchema().load({"offer": "https://allegro.pl/oferta/filtr-oleju-18900338789"})
    assert loaded["offer"] == "18900338789"
    messages = _error(schemas.OfferSchema, {"offer": "abc"})
    assert "offer id" in messages["offer"][0]
    assert "offer" in _error(schemas.OfferSchema, {})
    assert "id" in _error(schemas.OfferSchema, {"offer": "1", "id": "1"})


def test_product_schemas():
    assert schemas.ProductSchema().load({"product": PRODUCT.upper()})["product"] == PRODUCT
    loaded = schemas.ProductOffersSchema().load({"product": f"https://allegro.pl/oferty-produktu/x-{PRODUCT}", "sort": "newest"})
    assert loaded["product"] == PRODUCT and loaded["sort"] == "newest" and loaded["page"] == 1
    loaded = schemas.ProductReviewsSchema().load({"product": PRODUCT, "rating": "5", "page": "3"})
    assert loaded == {"product": PRODUCT, "rating": 5, "page": 3, "country": "pl"}
    assert "rating" in _error(schemas.ProductReviewsSchema, {"product": PRODUCT, "rating": "6"})
    assert "product" in _error(schemas.ProductSchema, {"product": "18900338789"})


def test_seller_schemas():
    assert schemas.SellerSchema().load({"seller": "https://allegro.pl/uzytkownik/Auto_Prima/oceny"}) == \
        {"seller": "Auto_Prima", "country": "pl"}
    loaded = schemas.SellerOffersSchema().load({"seller": "Auto_Prima", "query": "filtr", "page": "2"})
    assert loaded["seller"] == "Auto_Prima" and loaded["query"] == "filtr" and loaded["page"] == 2
    loaded = schemas.SellerRatingsSchema().load({"seller": "Auto_Prima", "recommended": "false"})
    assert loaded == {"seller": "Auto_Prima", "page": 1, "recommended": False, "country": "pl"}
    assert "seller" in _error(schemas.SellerSchema, {"seller": "has space"})
    assert "seller" in _error(schemas.SellerSchema, {})


def test_categories_schema():
    assert schemas.CategoriesSchema().load({}) == {"category": None, "country": "pl"}
    assert schemas.CategoriesSchema().load({"category": "Elektronika"})["category"] == "elektronika"
    assert schemas.CategoriesSchema().load({"category": "https://allegro.pl/kategoria/dom-i-ogrod"})["category"] == "dom-i-ogrod"
    assert "category" in _error(schemas.CategoriesSchema, {"category": "https://example.com/x"})
