"""Marshmallow request schemas for every /allegro/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    offer      a numeric offer id OR any allegro.<tld> offer / product link
    product    a product uuid OR a /produkt/ or /oferty-produktu/ link
    seller     a seller login OR a /uzytkownik/<login> link
    category   a category id, a department alias ("elektronika") OR a
               /kategoria/ link
    country    marketplace: pl (default), cz, sk — same page structure,
               each with its own search path and cookie identity
"""
from marshmallow import ValidationError, validate, validates_schema

from allegro import refs
from schema_fields import (BaseSchema, ChoiceField, Flag, PageField, PositiveInt, Price, QueryField,
                           RefField)

MAX_LISTING_PAGE = 100          # Allegro's own lastAvailablePage cap (2026-10-23)


def _max_length(n):
    """Length(max=n) that tolerates the None an optional StrippedString
    yields for an empty value (QueryField's own Length(min=1) would raise
    TypeError on `?query=`, escaping load_query as a bottle 500)."""
    return lambda value: value is None or bool(validate.Length(max=n)(value))
MAX_RATINGS_PAGE = 1000


class OfferRefField(RefField):
    resolver = staticmethod(refs.resolve_offer)


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class SellerRefField(RefField):
    resolver = staticmethod(refs.resolve_seller)


class CategoryRefField(RefField):
    resolver = staticmethod(refs.resolve_category)


def country_field():
    return ChoiceField(list(refs.MARKETS), load_default=refs.DEFAULT_MARKET, metadata={
        "description": "marketplace: pl (allegro.pl, default), cz (allegro.cz) or sk (allegro.sk)"})


def sort_field():
    return ChoiceField(list(refs.SORT_ORDERS), metadata={
        "description": "sort order: relevance (default), price_asc, price_desc, "
                       "price_with_delivery_asc, price_with_delivery_desc, popularity, "
                       "ending_soonest, newest, product_rating"})


class _ListingFilters(BaseSchema):
    """The listing filters shared by search, category, seller and product-offers listings."""
    page = PageField(max_page=MAX_LISTING_PAGE, metadata={"description": "result page, 1-100 (Allegro's cap)"})
    sort = sort_field()
    min_price = Price(metadata={"description": "lowest price to include, in the marketplace currency"})
    max_price = Price(metadata={"description": "highest price to include, in the marketplace currency"})
    condition = ChoiceField(list(refs.CONDITIONS), metadata={
        "description": "item condition: new, used, damaged or refurbished"})
    buy_now = Flag(metadata={"description": "true: only buy-now offers (no auctions)"})
    smart = Flag(metadata={"description": "true: only offers with free Allegro Smart! delivery and returns"})
    super_seller = Flag(metadata={"description": "true: only Super Seller offers"})
    country = country_field()

    @validates_schema
    def _price_range(self, data, **kwargs):
        lo, hi = data.get("min_price"), data.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise ValidationError("min_price must not exceed max_price.", "max_price")


class SuggestionsSchema(BaseSchema):
    query = QueryField(max_length=100, metadata={"description": "partial search phrase to complete"})
    country = country_field()


class OffersSearchSchema(_ListingFilters):
    query = QueryField(required=False, load_default=None, validate=_max_length(200), metadata={
        "description": "search phrase (at least one of query / category)"})
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "category id, department alias (elektronika) or category link to search within"})

    @validates_schema
    def _query_or_category(self, data, **kwargs):
        if not data.get("query") and not data.get("category"):
            raise ValidationError("Give a query, a category, or both.", "query")


class OfferSchema(BaseSchema):
    offer = OfferRefField(metadata={
        "description": "numeric offer id, or an allegro.pl offer / product link (…/oferta/<name>-<id>)"})
    country = country_field()


class ProductSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product id (uuid), or a /produkt/ or /oferty-produktu/ link"})
    country = country_field()


class ProductOffersSchema(_ListingFilters):
    product = ProductRefField(metadata={
        "description": "product id (uuid), or a /produkt/ or /oferty-produktu/ link"})


class ProductReviewsSchema(BaseSchema):
    product = ProductRefField(metadata={
        "description": "product id (uuid), or a /produkt/ or /oferty-produktu/ link"})
    page = PageField(max_page=MAX_RATINGS_PAGE, metadata={"description": "review page (20 per page)"})
    rating = PositiveInt(max_value=5, metadata={"description": "only reviews with this star rating (1-5)"})
    country = country_field()


class SellerSchema(BaseSchema):
    seller = SellerRefField(metadata={
        "description": "seller login, or a seller link (https://allegro.pl/uzytkownik/<login>)"})
    country = country_field()


class SellerOffersSchema(_ListingFilters):
    seller = SellerRefField(metadata={
        "description": "seller login, or a seller link (https://allegro.pl/uzytkownik/<login>)"})
    query = QueryField(required=False, load_default=None, validate=_max_length(200), metadata={
        "description": "search phrase within the seller's offers"})


class SellerRatingsSchema(BaseSchema):
    seller = SellerRefField(metadata={
        "description": "seller login, or a seller link (https://allegro.pl/uzytkownik/<login>)"})
    page = PageField(max_page=MAX_RATINGS_PAGE, metadata={"description": "ratings page (20 per page)"})
    recommended = Flag(metadata={"description": "true: only positive ratings; false: only negative ones"})
    country = country_field()


class CategoriesSchema(BaseSchema):
    category = CategoryRefField(required=False, load_default=None, metadata={
        "description": "category id, department alias (elektronika) or category link; empty = the top-level departments"})
    country = country_field()
