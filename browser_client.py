"""Mints the DataDome cookie identity that allegro/fetch.py replays over
plain HTTP, with a real Google Chrome (patchright) on this machine.

Every Allegro host sits behind DataDome. One Chrome loads a listing page
through your proxy, waits for DataDome's device check to clear, then loads a
SECOND listing page — only the cookie from that second page works when it is
replayed over plain HTTP. The Chrome closes right after; the cookie and user
agent are kept in memory and reused until Allegro blocks them, then a fresh
identity is minted. One identity per marketplace (allegro.pl / .cz / .sk).

Same call shape as the hosted service's client (identity, invalidate,
cookie_header and the three exceptions), so allegro/ runs unchanged.
"""
import threading
import time

TTL_SECONDS = 24 * 3600        # how long an identity is reused when nothing blocks it
CLEAR_TIMEOUT = 60             # seconds Chrome waits for DataDome on each page
SETTLE_SECONDS = 6             # after the second page, for DataDome's beacon round-trip
REMINT_PER_MINUTE = 5          # stop a block from relaunching Chrome in a loop

SEEDS = {
    "": ("https://allegro.pl/listing?string=kurtka", "Europe/Warsaw"),
    "pl": ("https://allegro.pl/listing?string=kurtka", "Europe/Warsaw"),
    "cz": ("https://allegro.cz/vyhledavani?string=bunda", "Europe/Prague"),
    "sk": ("https://allegro.sk/vyhladavanie?string=bunda", "Europe/Bratislava"),
}
DD_MARKERS = ("var dd=", "captcha-delivery", "enable js and disable")
DD_BLOCK_MARKERS = ("'t':'bv'", '"t":"bv"', "you have been blocked", "access is temporarily restricted")
CAPTCHA_MARKERS = ("allegrocaptcha.com",)


class BoxUnavailable(Exception):
    """Chrome could not start on this machine (not installed, no display)."""


class BoxRefused(Exception):
    """DataDome did not let Chrome through on this connection."""


class RemintBudgetExceeded(Exception):
    """Too many identities minted in the last minute."""


_cache = {}
_locks = {}
_locks_guard = threading.Lock()
_mints = []


def _frames(driver):
    try:
        return driver.content_frames() or []
    except Exception:
        return []


def _wait_clear(driver, label):
    deadline = time.monotonic() + CLEAR_TIMEOUT
    while True:
        frames = _frames(driver)
        joined = " ".join(frames).lower()
        if any(m in joined for m in DD_BLOCK_MARKERS):
            raise BoxRefused(f"allegro: DataDome blocked Chrome on the {label} page; use another proxy")
        if any(m in joined for m in CAPTCHA_MARKERS):
            raise BoxRefused(f"allegro: Allegro's captcha on the {label} page; use another proxy")
        html = (frames[0] if frames else "") or ""
        if len(html) > 20000 and not any(m in html[:8000].lower() for m in DD_MARKERS):
            return
        if time.monotonic() >= deadline:
            raise BoxRefused(f"allegro: DataDome did not clear on the {label} page in {CLEAR_TIMEOUT}s")
        time.sleep(2)


def mint(site, proxy=None, variant=""):
    """Open Chrome, pass DataDome on two listing pages, return the identity."""
    seed, timezone = SEEDS.get(variant or "", SEEDS[""])
    origin = "/".join(seed.split("/")[:3])
    try:
        from patchright_driver import PatchrightDriver
        driver = PatchrightDriver(proxy, headless=False, browserforge=True,
                                  timezone=timezone, geoip_timezone=False)
    except Exception as e:
        raise BoxUnavailable(f"could not start Chrome: {type(e).__name__}: {e}")
    try:
        driver.nav(seed, referer="https://www.google.com/", mode="blocked", challenge_markers=DD_MARKERS)
        _wait_clear(driver, "first")
        driver.nav(seed + "&p=2", referer=seed, mode="blocked", challenge_markers=DD_MARKERS)
        _wait_clear(driver, "second")
        time.sleep(SETTLE_SECONDS)
        cookies = driver.call(lambda page: page.context.cookies(origin))
        if not any(c["name"] == "datadome" for c in cookies):
            raise BoxRefused("allegro: no datadome cookie after the second page")
        return {
            "cookies": [{k: c[k] for k in ("name", "value", "domain", "path") if k in c} for c in cookies],
            "user_agent": driver.evaluate("navigator.userAgent"),
            "tokens": {},
            "exit_ip": None,
            "expires_at": time.time() + TTL_SECONDS,
        }
    except BoxRefused:
        raise
    except Exception as e:
        raise BoxRefused(f"allegro: Chrome failed while passing DataDome: {type(e).__name__}: {e}")
    finally:
        driver.close()


def _charge_budget():
    now = time.monotonic()
    _mints[:] = [t for t in _mints if t > now - 60]
    if len(_mints) >= REMINT_PER_MINUTE:
        raise RemintBudgetExceeded(f"{REMINT_PER_MINUTE} identities minted in the last minute")
    _mints.append(now)


def identity(site, proxy=None, variant="", force=False):
    """The cached identity for (site, proxy, variant); one mint at a time."""
    key = (site, proxy, variant)
    ident = _cache.get(key)
    if not force and ident and ident["expires_at"] > time.time():
        return ident
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        ident = _cache.get(key)
        if not force and ident and ident["expires_at"] > time.time():
            return ident
        _charge_budget()
        ident = mint(site, proxy, variant)
        _cache[key] = ident
        return ident


def invalidate(site, proxy=None, variant=""):
    _cache.pop((site, proxy, variant), None)


def cookie_header(ident):
    return "; ".join(f"{c['name']}={c['value']}" for c in ident.get("cookies", []))
