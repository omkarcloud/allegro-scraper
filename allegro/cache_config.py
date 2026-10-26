"""Cache TTL per /allegro/* endpoint (cache.py, keyed on the validated params)."""
from datetime import timedelta

# Listing pages (search, category, seller storefront, product offers, ended):
# prices and stock move, but a marketplace listing is a snapshot anyway.
LISTING_CACHE = timedelta(minutes=30)
# One offer / product page: price + stock are the point, keep it short.
OFFER_CACHE = timedelta(minutes=15)
# Product reviews change slowly; a new review a day on a popular product.
REVIEWS_CACHE = timedelta(hours=6)
# Seller record (ratings page + storefront header): feedback % moves daily.
SELLER_CACHE = timedelta(hours=6)
# Seller ratings list: new ratings land hourly for big sellers.
RATINGS_CACHE = timedelta(hours=1)
# Search suggestions: a popularity model, refreshed by Allegro rarely.
SUGGESTIONS_CACHE = timedelta(hours=24)
# Category tree: changes a few times a year.
CATEGORIES_CACHE = timedelta(hours=24)
