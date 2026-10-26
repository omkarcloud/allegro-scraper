"""Start the Allegro Scraper API.

    ALLEGRO_PROXY=http://user:pass@host:port python run.py   # http://localhost:8000
    PORT=9000 python run.py                                   # another port

Then:  curl "http://localhost:8000/offers/details?offer=18907429591"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    print(f"Allegro Scraper listening on http://localhost:{config.PORT}/")
    if not config.ALLEGRO_PROXY:
        print("WARNING: ALLEGRO_PROXY is not set — Allegro's DataDome blocks direct requests, "
              "so every endpoint will fail until you set it.")
    print(f"Try:  curl \"http://localhost:{config.PORT}/offers/details?offer=18907429591\"")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="allegro-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
