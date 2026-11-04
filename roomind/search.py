"""Web tools: search snippets plus weather. Free tiers, honest empties."""
import re
from html import unescape
from html.parser import HTMLParser

import httpx


def web_search(query: str, api_key: str = "",
               base: str = "https://api.tavily.com",
               count: int = 5, timeout: float = 20.0) -> list:
    """Snippet rows [{title, url, snippet}]. [] when keyless or on failure."""
    if not (api_key and query.strip()):
        return []
    try:
        r = httpx.post(f"{base.rstrip('/')}/search",
                       json={"api_key": api_key, "query": query.strip(),
                             "max_results": count, "search_depth": "basic"},
                       timeout=timeout)
        r.raise_for_status()
        rows = []
        for w in r.json().get("results", [])[:count]:
            rows.append({"title": w.get("title", ""),
                         "url": w.get("url", ""),
                         "snippet": w.get("content", "")})
        return rows
    except Exception:
        return []


_CODES = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy",
          3: "overcast", 45: "foggy", 48: "icy fog", 51: "light drizzle",
          53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
          65: "heavy rain", 71: "light snow", 73: "snow", 75: "heavy snow",
          80: "light showers", 81: "showers", 82: "heavy showers",
          95: "thunderstorm", 96: "storm with hail", 99: "storm with hail"}


def describe(code) -> str:
    try:
        return _CODES.get(int(code), "unsettled")
    except (TypeError, ValueError):
        return "unsettled"


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("head", "script", "style", "nav", "header", "footer"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("head", "script", "style", "nav", "header", "footer") \
                and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            text = data.strip()
            if text:
                self.parts.append(text)


_OPEN_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
}


def open_page(url: str, timeout: float = 20.0) -> dict:
    """Full page {title, text} stripped of markup. {} on failure."""
    if not url.strip().lower().startswith(("http://", "https://")):
        return {}
    try:
        r = httpx.get(url.strip(), timeout=timeout, follow_redirects=True,
                      headers=_OPEN_HEADERS)
        r.raise_for_status()
        parser = _Text()
        parser.feed(r.text[:200000])
        text = unescape(" ".join(parser.parts))
        text = " ".join(text.split())[:6000]
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text[:20000],
                      re.S | re.I)
        if m:
            title = unescape(" ".join(m.group(1).split()))[:200]
        if not text:
            return {}
        return {"title": title, "text": text}
    except Exception:
        return {}


def weather(place: str, timeout: float = 20.0) -> dict:
    """Current {place, temp_c, code} via Open-Meteo. {} on failure."""
    if not place.strip():
        return {}
    try:
        g = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                      params={"name": place.strip(), "count": 1},
                      timeout=timeout).json()
        hits = g.get("results") or []
        if not hits:
            return {}
        lat, lon = hits[0]["latitude"], hits[0]["longitude"]
        name = hits[0].get("name", place)
        cur = httpx.get("https://api.open-meteo.com/v1/forecast",
                        params={"latitude": lat, "longitude": lon,
                                "current": "temperature_2m,weather_code"},
                        timeout=timeout).json().get("current", {})
        if cur.get("temperature_2m") is None:
            return {}
        return {"place": name, "temp_c": cur["temperature_2m"],
                "code": cur.get("weather_code")}
    except Exception:
        return {}
