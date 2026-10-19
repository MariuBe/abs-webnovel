"""Mock Byparr server for local smoke testing.

Implements just enough of the FlareSolverr-compatible contract
(``POST /v1``) to exercise abs-webnovel's Byparr integration: it returns a
fixed, Cloudflare-"solved" NovelUpdates search page as rendered HTML.
"""

from __future__ import annotations

from aiohttp import web

NU_HTML = """
<html><body>
<div class="series-item">
  <a href="https://www.novelupdates.com/series/solo-leveling/" class="series-title">Solo Leveling</a>
</div>
<div class="series-item">
  <a href="https://www.novelupdates.com/series/the-beginning-after-the-end/" class="series-title">The Beginning After the End</a>
</div>
</body></html>
"""


async def v1(request: web.Request) -> web.Response:
    body = await request.json()
    url = body.get("url", "")
    if "novelupdates.com" in url:
        return web.json_response(
            {
                "status": "ok",
                "message": "Success",
                "solution": {
                    "url": url,
                    "status": 200,
                    "cookies": [],
                    "userAgent": "mock-byparr-ua",
                    "response": NU_HTML,
                    "contentType": "text/html",
                },
            }
        )
    return web.json_response(
        {"status": "error", "message": "unsupported url", "solution": {"status": 500}}
    )


async def health(request: web.Request) -> web.Response:
    return web.json_response({"msg": "mock byparr", "version": "0.0.0"})


def main() -> None:
    app = web.Application()
    app.router.add_post("/v1", v1)
    app.router.add_get("/health", health)
    web.run_app(app, host="127.0.0.1", port=8191)


if __name__ == "__main__":
    main()
