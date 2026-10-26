"""Use the scraper straight from Python — no server needed.

    ALLEGRO_PROXY=http://user:pass@host:port python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from allegro.api import offers_details, offers_search, products_reviews

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # an offer ID or any allegro.pl offer link: price, stock, seller, delivery, reviews
    save("offer_pandora_bracelet.json", offers_details(offer="18907429591", country="pl"))

    # 60 offers per page, with price / condition / seller filters
    save("search_raspberry_pi.json", offers_search(query="raspberry pi", category=None, page=1, country="pl"))

    # 20 reviews per page for Apple AirPods Pro (2nd gen)
    save("reviews_airpods_pro.json", products_reviews(product="2061a0fd-c345-4957-b4f4-f6dad730071e",
                                                      page=1, rating=None, country="pl"))
