# 🛒 Allegro Scraper

Allegro Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Allegro data for free.

## ✨ What Can I Get?

- 🛒 **Full details on any offer from 160,000+ Allegro sellers** — price, stock, sales, seller company, delivery options & photos
- 🔍 **Search the marketplace 20M+ shoppers use every month** — keyword or category, price, condition, Smart! & Super Seller filters
- ⭐ **Products, reviews & every seller's price** — star breakdown, full reviews with pros & cons, all offers for one product
- 🏪 **Seller profiles, ratings & storefronts** — recommendation %, every buyer rating, years on Allegro, full offer list

## 🎥 Example: A Full Allegro Offer

```json
{
  "id": "18907429591",
  "name": "Bransoletka Pandora Moments - Z zapięciem w kształcie Serca 594594C00 20cm",
  "link": "https://allegro.pl/oferta/bransoletka-pandora-moments-z-zapieciem-w-ksztalcie-serca-594594c00-20cm-18907429591",
  "status": "active",
  "price": { "amount": 285.0, "currency": "PLN", "is_buy_now": true, "is_cart_available": true },
  "stock": { "available_quantity": 14, "unit": "UNIT" },
  "condition": "Nowy",
  "brand": "Pandora",
  "gtin": "5700303289267",
  "category": { "id": "257987", "name": "Bransoletki" },
  "images": ["https://a.allegroimg.com/original/111a29/9421ceef47af9cbe151f6eb716f4/Bransoletka-Pandora-Moments-Z-zapieciem-w-ksztalcie-Serca-594594C00-20cm"],
  "product": {
    "id": "e861e81f-3549-474d-8e66-a1cf4f672799",
    "rating": { "average": 5, "count": 5, "distribution": { "5": 5, "4": 0, "3": 0, "2": 0, "1": 0 } },
    "buyers_last_30_days": 20
  },
  "seller": {
    "login": "TylkoOryginalna",
    "is_super_seller": true,
    "ratings": { "positive_count": 1070, "positive_percent": 99.6, "negative_count": 4 },
    "company": { "name": "TYLKOORYGINALNA.PL SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ", "city": "Toruń", "tax_id": "9562320795", "is_verified": true }
  },
  "delivery": {
    "handling_time": "24 godziny",
    "methods": [
      { "name": "Allegro One Box, Allegro One", "first_item_cost": { "amount": 10.49, "currency": "PLN" }, "delivery_time": "wt. 27 paź. w punkcie" }
    ]
  },
  "returns": { "withdrawal_period": "14 dni" }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Allegro Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/allegro-scraper
cd allegro-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
ALLEGRO_PROXY="http://user:pass@host:port" python run.py
```

Allegro's DataDome blocks direct connections, so point `ALLEGRO_PROXY` at a residential proxy in Poland. On the first request, Google Chrome opens once to pass DataDome (about 40 seconds); every request after that is plain HTTP.

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/offers/details?offer=18907429591"
```

```json
{
  "id": "18907429591",
  "name": "Bransoletka Pandora Moments - Z zapięciem w kształcie Serca 594594C00 20cm",
  "status": "active",
  "price": { "amount": 285.0, "currency": "PLN", "is_buy_now": true },
  "stock": { "available_quantity": 14, "unit": "UNIT" },
  "sold": { "buyers_last_30_days": 1, "label": "1 osoba kupiła 1 sztukę" },
  "condition": "Nowy",
  "brand": "Pandora",
  "gtin": "5700303289267",
  "seller": {
    "login": "TylkoOryginalna",
    "is_super_seller": true,
    "ratings": { "positive_count": 1070, "positive_percent": 99.6, "negative_count": 4 }
  },
  "delivery": { "handling_time": "24 godziny", "price_with_delivery_label": "295,49 zł z dostawą" },
  "returns": { "withdrawal_period": "14 dni" }
}
```

All 10 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

10 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Offer Details | `/offers/details` | Price, stock, seller company, delivery, parameters and reviews in one call |
| Search Offers | `/offers/search` | 60 offers per page; filter by price, condition, Smart! or Super Seller |
| Search Suggestions | `/search/suggestions` | Typeahead phrases and product tiles for any partial query |
| Product Details | `/products/details` | Rating breakdown, reviews, parameters and the featured offer |
| Product Offers | `/products/offers` | Every seller's price for one product, 60 per page |
| Product Reviews | `/products/reviews` | Full reviews with pros, cons and photos, 20 per page |
| Seller Details | `/sellers/details` | Recommendation %, ratings, years on Allegro, offer count |
| Seller Offers | `/sellers/offers` | A seller's whole storefront, searchable and filterable |
| Seller Ratings | `/sellers/ratings` | Every buyer rating with comment and the offers bought |
| List Categories | `/categories/list` | The category tree with subcategories and offer counts |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-allegro-scraper-free-200-calls/pricing) — 200 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-allegro-scraper-free-200-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-allegro-scraper-free-200-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/offers/details",
    params={"offer": "18907429591"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Allegro Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Allegro%20Scraper%20API.)

[![Ask Us by Email about Allegro Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Allegro%20Scraper%20API&body=I%20need%20help%20using%20the%20Allegro%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/allegro-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/allegro-scraper)
