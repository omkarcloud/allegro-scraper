"""Allegro transport: curl_cffi with a DataDome cookie identity minted on
the browser box (recipes/allegro.py), replayed on the SAME sticky exit.

Every Allegro host — allegro.pl / .cz / .sk pages and the edge.allegro.<tld>
JSON gateway — sits behind DataDome: a bare curl_cffi request answers 403
with the `var dd=` challenge page on every exit (Mac probes 2026-10-23).
A headed browserforge Chrome passes the device check, and its `datadome`
cookie + user agent make plain curl pass every surface this scraper uses
(listing, category, offer, product, product-offers, seller, seller
ratings, the three edge JSON calls) — but only the cookie of the browser's
SECOND page load (the recipe does both navigations). The replay TLS
profile matters on the /uzytkownik/* seller pages: from the pod
(curl_cffi 0.16.3, 2026-10-24) chrome116 / chrome110 / safari17_0 /
edge101 pass them while chrome120 / chrome123 / chrome124 / "chrome" /
safari get the DataDome 403 with the very same cookie and port (the
listing / offer / product / edge surfaces pass with every profile), so
IMPERSONATE pins chrome116 (also fine on the Mac's 0.7.1).

Identity model (etsy pattern): one identity per MARKET (cookie domain),
process-wide, minted lazily by browser_client.identity("allegro",
proxy=<sticky exit>, variant=<market>) and shared by every worker thread;
thread-local curl sessions rebuild onto the identity's exit through a
generation counter. A block (DataDome 403, Allegro's own captcha 429) drops
the identity and the retry mints a new one on a FRESH sticky exit (new
port = new IP). The pod never contacts Allegro from its own IP (owner rule
2026-10-20): config.allegro_proxy() must return a proxy.

Allegro's own rate limiter (HTTP 429 with an allegrocaptcha.com iframe and
the `wdctx` cookie) fires on bursts from one identity and clears in ~80 s;
here it counts as a block (fresh identity + exit).

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  AllegroUpstreamError  transport failure / 5xx                 — retryable
  AllegroBoxDown        browser box down / busy                 — fails at once
  AllegroBlocked        DataDome 403 / captcha 429 / challenge  — retryable after a re-mint
  AllegroBadRequest     upstream 400                            — never retried
  AllegroNotFound       404 page, unknown seller                 — never retried
"""
import json
import os
import sys
import threading
import time
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
from browser_client import BoxRefused, BoxUnavailable, RemintBudgetExceeded
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from allegro import parsers
from allegro.refs import (CONDITIONS, DEFAULT_MARKET, MARKETS, SORT_ORDERS, category_link, edge_host,
                          host, offer_link, product_link, product_offers_link, search_link,
                          seller_link, seller_ratings_link)

BOX_SITE = "allegro"               # recipes/allegro.py
IMPERSONATE = "chrome116"          # see the module docstring
PAGE_TIMEOUT = 40                  # listing pages are 2.5–4 MB
JSON_TIMEOUT = 20
MINT_ATTEMPTS = 3                  # fresh exit per attempt

ACCEPT_HTML = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8")
ACCEPT_SUGGESTIONS = "application/vnd.allegro.internal.v7+json"
ACCEPT_REVIEWS = "application/vnd.allegro.public.v2+json"
ACCEPT_RATINGS = "application/vnd.allegro.public.v5+json"


class AllegroUpstreamError(UpstreamError):
    """Transport failure / 5xx / browser box unavailable — retryable."""


class AllegroBoxDown(AllegroUpstreamError):
    """The browser box is down, draining or full: fail the request at once
    (a retry would only wait on the box again)."""


class AllegroBlocked(AllegroUpstreamError, Blocked):
    """DataDome challenge, Allegro captcha or 403/429 — retryable after a fresh identity."""


class AllegroBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class AllegroNotFound(NotFound):
    """Offer / product / seller / page does not exist — never retried."""


# ---- identity per market -----------------------------------------------------------
# {market: {"ident": <box identity>, "proxy": <sticky url>, "gen": n}}
_identities = {}
_identity_lock = threading.Lock()
_local = threading.local()


def _mint(market):
    """One identity for `market` on a fresh sticky exit; MINT_ATTEMPTS exits."""
    last = None
    for attempt in range(1, MINT_ATTEMPTS + 1):
        proxy = config.allegro_proxy(market)
        if not proxy:
            raise AllegroUpstreamError("allegro: no proxy configured (config.allegro_proxy() returned "
                                       "none); Allegro's DataDome blocks direct requests, so every "
                                       "request goes through a proxy")
        try:
            print(f"allegro[{market}]: minting DataDome identity on the browser box "
                  f"(exit port {proxy.rsplit(':', 1)[-1]}, attempt {attempt}/{MINT_ATTEMPTS})...")
            ident = browser_client.identity(BOX_SITE, proxy=proxy, variant=market)
        except BoxUnavailable as e:
            raise AllegroBoxDown(f"browser box unavailable for the identity mint: {e}")
        except RemintBudgetExceeded as e:
            raise AllegroBlocked(f"identity re-mint budget exhausted: {e}")
        except BoxRefused as e:
            last = e
            print(f"allegro[{market}]: mint attempt {attempt} refused: {e}")
            continue
        cookies = {c["name"]: c["value"] for c in ident.get("cookies") or []}
        if "datadome" not in cookies or not ident.get("user_agent"):
            last = RuntimeError("the box answered without a datadome cookie / user agent")
            continue
        print(f"allegro[{market}]: identity minted (exit {ident.get('exit_ip')}, "
              f"ua={ident['user_agent'][:40]}..., cookie_changed={ident.get('tokens', {}).get('cookie_changed')})")
        return {"ident": ident, "proxy": proxy, "cookies": cookies}
    raise AllegroBlocked(f"identity mint failed after {MINT_ATTEMPTS} attempts (last: {last})")


def _identity(market):
    with _identity_lock:
        entry = _identities.get(market)
        if entry is not None:
            return entry
        gen = _identities.get(("gen", market), 0) + 1
        entry = _mint(market)
        entry["gen"] = gen
        _identities[("gen", market)] = gen
        _identities[market] = entry
        return entry


def _invalidate(market, stale):
    """Drop the market's identity iff it is still the one that got blocked
    (another thread may already have re-minted)."""
    with _identity_lock:
        if _identities.get(market) is stale:
            del _identities[market]
            browser_client.invalidate(BOX_SITE, proxy=stale["proxy"], variant=market)


def _session(entry):
    """Thread-local curl session on the identity's exit; rebuilt when the
    identity generation moved (a re-mint rotated the exit)."""
    store = getattr(_local, "sessions", None)
    if store is None:
        store = _local.sessions = {}
    key = entry["proxy"]
    sess, gen = store.get(key, (None, None))
    if sess is not None and gen != entry["gen"]:
        _drop_session(entry)
        sess = None
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        sess.proxies = {"http": entry["proxy"], "https": entry["proxy"]}
        store[key] = (sess, entry["gen"])
    return sess


def _drop_session(entry):
    store = getattr(_local, "sessions", None)
    if not store:
        return
    sess, _ = store.pop(entry["proxy"], (None, None))
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _headers(entry, accept, referer, market=DEFAULT_MARKET):
    return {
        "user-agent": entry["ident"]["user_agent"],
        "cookie": browser_client.cookie_header(entry["ident"]),
        "accept": accept,
        "accept-language": MARKETS[market]["language"] + ",en;q=0.8",
        "referer": referer,
    }


def _once(market, url, accept, referer, timeout, expect_json=False, what=None):
    entry = _identity(market)
    try:
        resp = _session(entry).get(url, headers=_headers(entry, accept, referer, market), timeout=timeout,
                                   allow_redirects=True)
    except Exception as e:
        raise AllegroUpstreamError(f"request failed: {type(e).__name__}: {e}")
    text = resp.text or ""
    status = resp.status_code
    kind = parsers.page_kind(text, status) if not expect_json or status != 200 else "page"
    if kind in ("datadome", "captcha") or status in (403, 429):
        _invalidate(market, entry)
        raise AllegroBlocked(f"HTTP {status} ({kind}) for {url}")
    if status == 404 or kind == "not_found" or "/uzytkownik/notfound" in str(resp.url):
        raise AllegroNotFound(f"{what} not found" if what else f"{url} not found")
    if status == 400:
        raise AllegroBadRequest(text[:200])
    if status == 406:
        raise AllegroUpstreamError(f"HTTP 406 for {url}: the edge Accept version moved ({text[:120]})")
    if status != 200:
        raise AllegroUpstreamError(f"HTTP {status} for {url}")
    if not text:
        raise AllegroUpstreamError(f"empty body for {url}")
    if expect_json:
        try:
            return json.loads(text)
        except ValueError:
            raise AllegroUpstreamError(f"non-JSON body for {url}: {text[:120]!r}")
    return text, str(resp.url)


def _retrying(fn):
    """config.MAX_RETRIES attempts; a retryable failure drops the thread's
    session (a block already dropped the identity, so the retry mints a new
    one on a fresh exit). NotFound / BadRequest surface at once."""
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except AllegroBoxDown:
            raise
        except AllegroUpstreamError as e:
            last = e
            store = getattr(_local, "sessions", None) or {}
            for key in list(store):
                sess, _ = store.pop(key)
                try:
                    sess.close()
                except Exception:
                    pass
            if attempt < config.MAX_RETRIES:
                time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def fetch_page(url, market=DEFAULT_MARKET, referer=None, what=None):
    """GET one HTML page through the market's identity -> (html, final_url).
    `what` names the record for the 404 message ("offer 123")."""
    referer = referer or host(market) + "/"
    return _retrying(lambda: _once(market, url, ACCEPT_HTML, referer, PAGE_TIMEOUT, what=what))


def fetch_json(url, accept, market=DEFAULT_MARKET, referer=None):
    """GET one edge.allegro.<tld> JSON call (versioned Accept header)."""
    referer = referer or host(market) + "/"
    return _retrying(lambda: _once(market, url, accept, referer, JSON_TIMEOUT, expect_json=True))


# ---- URL builders -----------------------------------------------------------------

def listing_params(page=1, sort=None, min_price=None, max_price=None, condition=None,
                   buy_now=None, smart=None, super_seller=None, query=None):
    """The listing query string Allegro understands (filter keys from the
    category page's filters box, 2026-10-23)."""
    params = {}
    if query:
        params["string"] = query
    if page and page > 1:
        params["p"] = page
    if sort and SORT_ORDERS.get(sort, "m") != "m":
        params["order"] = SORT_ORDERS[sort]
    if min_price is not None:
        params["price_from"] = _fmt_price(min_price)
    if max_price is not None:
        params["price_to"] = _fmt_price(max_price)
    if condition:
        params["stan"] = CONDITIONS.get(condition, condition)
    if buy_now:
        params["offerTypeBuyNow"] = 1
    if smart:
        params["allegro-smart-standard"] = 1
    if super_seller:
        params["super-sprzedawca"] = 1
    return params


def _fmt_price(value):
    return int(value) if float(value).is_integer() else value


def _with_params(base, params):
    return f"{base}?{urlencode(params)}" if params else base


def _requested_page_served(final_url, page):
    """Allegro answers a listing page past the end with a redirect to the
    first page (seller storefront p=40 -> /uzytkownik/<login>, pod replay
    2026-10-24): a request for page > 1 whose final URL lost the `p`
    param was not served, and the caller returns an empty page."""
    if not page or page <= 1:
        return True
    return f"p={page}" in (final_url or "")


def _listing(url, market, page, what=None):
    """(html, served) for one listing URL — served=False when Allegro
    redirected a past-the-end page back to the first one."""
    html, final_url = fetch_page(url, market, what=what)
    return html, _requested_page_served(final_url, page)


def fetch_search(query, market=DEFAULT_MARKET, **filters):
    return _listing(_with_params(search_link(market), listing_params(query=query, **filters)), market, filters.get("page"))


def fetch_category_listing(category, market=DEFAULT_MARKET, query=None, **filters):
    return _listing(_with_params(category_link(category, market), listing_params(query=query, **filters)), market,
                    filters.get("page"), what=f"category {category}")


def fetch_category_page(category, market=DEFAULT_MARKET):
    """(html, final_url) of a category page; a department alias
    ("elektronika") redirects to its /dzial/ marketing page."""
    return fetch_page(category_link(category, market), market, what=f"category {category}")


def fetch_sitemap(alias, market=DEFAULT_MARKET):
    """/mapa-strony/<department alias>: the department's category map."""
    return fetch_page(f"{host(market)}/mapa-strony/{alias}", market, what=f"category {alias}")[0]


def fetch_offer(offer_id, market=DEFAULT_MARKET):
    return fetch_page(offer_link(offer_id, market), market, what=f"offer {offer_id}")[0]


def fetch_product(product_id, market=DEFAULT_MARKET):
    """An unknown product uuid is not a 404: Allegro redirects it to some
    unrelated /oferta/ page (pod probe 2026-10-24), so the final URL must
    still carry the uuid."""
    html, final_url = fetch_page(product_link(product_id, market), market, what=f"product {product_id}")
    if product_id.lower() not in (final_url or "").lower():
        raise AllegroNotFound(f"product {product_id} not found")
    return html


def fetch_product_offers(product_id, market=DEFAULT_MARKET, **filters):
    return _listing(_with_params(product_offers_link(product_id, market), listing_params(**filters)), market,
                    filters.get("page"), what=f"product {product_id}")


def fetch_seller_listing(login, market=DEFAULT_MARKET, query=None, **filters):
    return _listing(_with_params(seller_link(login, market), listing_params(query=query, **filters)), market,
                    filters.get("page"), what=f"seller {login!r}")


def fetch_seller_ratings_page(login, market=DEFAULT_MARKET):
    return fetch_page(seller_ratings_link(login, market), market, what=f"seller {login!r}")[0]


def fetch_suggestions(query, market=DEFAULT_MARKET):
    url = f"{edge_host(market)}/search-suggester/suggestions?{urlencode({'query': query})}"
    return fetch_json(url, ACCEPT_SUGGESTIONS, market)


def fetch_product_reviews(product_id, market=DEFAULT_MARKET, page=1, rating=None):
    params = {"productId": product_id, "page": page}
    if rating:
        params["rating"] = rating
    url = f"{edge_host(market)}/product-reviews?{urlencode(params)}"
    return fetch_json(url, ACCEPT_REVIEWS, market, referer=product_link(product_id, market))


def fetch_seller_ratings(seller_id, login, market=DEFAULT_MARKET, page=1, size=parsers.RATINGS_PAGE_SIZE,
                         recommended=None):
    # the ratings-api is a Spring pageable: its `page` is 0-based (the
    # fixture's second page carries pageNumber 1 / offset 20) and the parser
    # adds 1 back, so the caller's 1-based page is shifted down here
    params = {"page": max(int(page or 1), 1) - 1, "size": size}
    if recommended is not None:
        params["recommend"] = "true" if recommended else "false"
    url = f"{edge_host(market)}/ratings-api/sellers/{seller_id}/ratings?{urlencode(params)}"
    return fetch_json(url, ACCEPT_RATINGS, market, referer=seller_ratings_link(login, market))
