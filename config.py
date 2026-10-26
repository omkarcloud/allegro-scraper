"""Configuration for the Allegro Scraper. Everything can be set with an
environment variable.

    PORT           port the API listens on (default 8000)
    ALLEGRO_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                   (REQUIRED). Allegro sits behind DataDome, which blocks most
                   home and server connections outright. Use a residential
                   proxy in Poland (or in the Czech Republic / Slovakia for
                   country=cz / sk) — datacenter proxies get Allegro's captcha.
                   A real Google Chrome on this machine passes DataDome once
                   per marketplace through this proxy, then every request runs
                   over plain HTTP with the cookie it earned. DataDome refuses
                   some residential IPs outright: if every request answers 403,
                   switch the proxy to another IP and restart.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

ALLEGRO_PROXY = os.environ.get("ALLEGRO_PROXY") or None


def allegro_proxy(market="pl"):
    """The proxy the DataDome cookie is minted and replayed on (None = not set)."""
    return os.environ.get("ALLEGRO_PROXY") or None
