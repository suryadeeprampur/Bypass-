import asyncio
import html
import re
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse, urljoin
from aiohttp import ClientSession, ClientTimeout, TCPConnector
import cloudscraper
from bs4 import BeautifulSoup
import functools


# User-Agent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Shortener hints
SHORTENER_HINTS = {
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "tiny.one",
    "cutt.ly", "rebrand.ly", "ouo.io", "shorte.st", "adf.ly",
    "linkvertise.com", "lnk.to", "gtlinks.me", "droplink.co",
    "tnlink.in", "tnshort.net", "rocklinks.net", "ez4short.com",
    "ouo.press", "boost.ink",
}

# Preferred targets
DEFAULT_PREFERRED = ("t.me", "telegram.me", "telegram.dog")

# Regex patterns
META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\'][^>]*?url=([^"\'>\s]+)', re.IGNORECASE
)
JS_REDIRECT_RE = re.compile(
    r'(?:window\.location(?:\.href)?|location\.href)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

# --- Utilities ---

def normalize_url(url: str) -> str:
    """Ensure URL starts with http/https and remove trailing spaces."""
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    return url

def _is_shortener(netloc: str) -> bool:
    host = netloc.lower()
    return any(host == d or host.endswith("." + d) for d in SHORTENER_HINTS)

def _preferred_first(candidates: Iterable[str], prefer: Sequence[str]) -> Optional[str]:
    """Return the preferred URL from a list."""
    def score(u: str) -> int:
        host = urlparse(u).netloc.lower()
        for i, dom in enumerate(prefer, start=1):
            if host == dom or host.endswith("." + dom):
                return 1000 - i
        return 0

    best = None
    best_s = -1
    for u in candidates:
        s = score(u)
        if s > best_s:
            best_s = s
            best = u
    return best or next(iter(candidates), None)

async def _fetch(session: ClientSession, url: str):
    """GET URL and return final URL and HTML text if content-type is HTML."""
    resp = await session.get(url, allow_redirects=True)
    text = ""
    ctype = resp.headers.get("content-type", "")
    if "text/html" in ctype.lower():
        text = await resp.text(errors="ignore")
    return str(resp.url), text

def _extract_from_html(html_text: str, base_url: str, prefer_domains: Sequence[str]) -> Optional[str]:
    """Extract redirect URL from meta refresh, JS, or anchors."""
    # Meta refresh
    m = META_REFRESH_RE.search(html_text)
    if m:
        return urljoin(base_url, html.unescape(m.group(1)))

    # JS redirect
    js = JS_REDIRECT_RE.findall(html_text)
    if js:
        hrefs = [urljoin(base_url, html.unescape(u)) for u in js]
        chosen = _preferred_first(hrefs, prefer_domains)
        if chosen:
            return chosen

    # Anchors
    hrefs = [urljoin(base_url, html.unescape(h)) for h in HREF_RE.findall(html_text)]
    if not hrefs:
        return None
    return _preferred_first(hrefs, prefer_domains)

# --- Shortener bypasses ---

async def gplinks_bypass(url: str) -> str:
    """Async bypass for gplinks.in"""
    client = cloudscraper.create_scraper()
    loop = asyncio.get_running_loop()

    # GET initial page
    res = await loop.run_in_executor(None, functools.partial(client.get, url, timeout=15))

    if "gplinks.in" not in res.url:
        return res.url

    soup = BeautifulSoup(res.text, "html.parser")
    form = soup.find("form")
    if not form:
        return "Bypass failed: form not found."

    action_url = form.get("action")
    inputs = form.find_all("input")
    data = {inp.get("name"): inp.get("value", "") for inp in inputs if inp.get("name")}

    await asyncio.sleep(5)  # countdown

    headers = {"Referer": url}
    res2 = await loop.run_in_executor(
        None, functools.partial(client.post, action_url, data=data, headers=headers, timeout=15, allow_redirects=False)
    )

    if "Location" in res2.headers:
        return res2.headers["Location"]
    return "Bypass failed: no redirect found."

# --- Main smart bypass ---

async def smart_bypass(url: str, prefer_domains=DEFAULT_PREFERRED, timeout: int = 25) -> str:
    """
    Smart bypass:
      1) Handle known shorteners (gplinks)
      2) Follow redirects and parse HTML for meta/JS/anchors
      3) Return final URL
    """
    norm = normalize_url(url)
    parsed = urlparse(norm)

    # Handle known shorteners
    if "gplinks.in" in parsed.netloc:
        return await gplinks_bypass(norm)

    connector = TCPConnector(ssl=False, limit=20)
    t = ClientTimeout(total=timeout)
    async with ClientSession(timeout=t, connector=connector, headers={"User-Agent": UA}) as session:
        final_url, html_text = await _fetch(session, norm)

        # If no longer a shortener, return
        if not _is_shortener(urlparse(final_url).netloc):
            return final_url

        # Try extracting from HTML
        if html_text:
            extracted = _extract_from_html(html_text, final_url, prefer_domains)
            if extracted:
                return extracted

        # Try one more GET
        final_url_2, html_text_2 = await _fetch(session, final_url)
        if not _is_shortener(urlparse(final_url_2).netloc):
            return final_url_2
        if html_text_2:
            extracted2 = _extract_from_html(html_text_2, final_url_2, prefer_domains)
            if extracted2:
                return extracted2

        # Last resort
        return final_url

# --- Testing ---

if __name__ == "__main__":
    test_url = input("https://gplinks.co/P3rGI").strip()
    final_link = asyncio.run(smart_bypass(test_url))
    print("Bypassed URL:", final_link)
