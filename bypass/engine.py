import asyncio
import re
import html
from typing import Iterable, Optional, Sequence
from urllib.parse import urlparse, urljoin
from aiohttp import ClientSession, ClientTimeout, TCPConnector
import time
import cloudscraper
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

SHORTENER_HINTS = {
    # common shorteners & interstitial domains
    "bit.ly", "t.co", "tinyurl.com", "goo.gl",
    "tiny.one", "cutt.ly", "rebrand.ly", "ouo.io",
    "shorte.st", "adf.ly", "linkvertise.com", "lnk.to",
    "gtlinks.me", "droplink.co", "tnlink.in", "tnshort.net",
    "rocklinks.net", "ez4short.com", "ouo.press", "boost.ink",
}

# Prefer targets you'd like to extract from page HTML when JS is required
DEFAULT_PREFERRED = ("t.me", "telegram.me", "telegram.dog")

META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\'][^>]*?url=([^"\'>\s]+)',
    re.IGNORECASE
)

JS_REDIRECT_RE = re.compile(
    r'(?:window\.location(?:\.href)?|location\.href)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE
)

HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)

def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    return url

def _is_shortener(netloc: str) -> bool:
    host = netloc.lower()
    return any(host == d or host.endswith("." + d) for d in SHORTENER_HINTS)

def _preferred_first(candidates: Iterable[str], prefer: Sequence[str]) -> Optional[str]:
    def score(u: str) -> int:
        host = urlparse(u).netloc.lower()
        for i, dom in enumerate(prefer, start=1):
            if host == dom or host.endswith("." + dom):
                # higher weight for earlier in list
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
    # GET with redirect following; some providers require GET over HEAD
    resp = await session.get(url, allow_redirects=True)
    text = ""
    ctype = resp.headers.get("content-type", "")
    if "text/html" in ctype.lower():
        text = await resp.text(errors="ignore")
    return str(resp.url), text

def _extract_from_html(html_text: str, base_url: str, prefer_domains: Sequence[str]) -> Optional[str]:
    # 1) <meta http-equiv="refresh" content="0;url=...">
    m = META_REFRESH_RE.search(html_text)
    if m:
        return urljoin(base_url, html.unescape(m.group(1)))

    # 2) JS assignments to location
    js = JS_REDIRECT_RE.findall(html_text)
    if js:
        # normalize to absolute
        hrefs = [urljoin(base_url, html.unescape(u)) for u in js]
        chosen = _preferred_first(hrefs, prefer_domains)
        if chosen:
            return chosen

    # 3) Scan anchors; pick preferred targets first (t.me etc.)
    hrefs = [urljoin(base_url, html.unescape(h)) for h in HREF_RE.findall(html_text)]
    if not hrefs:
        return None
    chosen = _preferred_first(hrefs, prefer_domains)
    return chosen

async def smart_bypass(
    url: str,
    prefer_domains: Sequence[str] = DEFAULT_PREFERRED,
    timeout: int = 20
) -> str:
    """
    Strategy:
      1) Follow server redirects.
      2) If still on shortener, parse HTML for meta refresh / JS redirects.
      3) If still stuck, scan all links and return the most 'preferred' target (t.me etc.).
      4) Fallback: return final_url.
    """
    norm = normalize_url(url)
    parsed = urlparse(norm)

    connector = TCPConnector(ssl=False, limit=20)
    t = ClientTimeout(total=timeout)
    async with ClientSession(timeout=t, connector=connector, headers={"User-Agent": UA}) as session:
        final_url, html_text = await _fetch(session, norm)

        # If we left a shortener domain, we’re done
        if not _is_shortener(urlparse(final_url).netloc):
            return final_url

        # Try extracting target from HTML we already have
        if html_text:
            extracted = _extract_from_html(html_text, final_url, prefer_domains)
            if extracted:
                return extracted

        # Some providers only give content after a second request (cookie set)
        # Try one more GET on the final URL we reached
        final_url_2, html_text_2 = await _fetch(session, final_url)
        if not _is_shortener(urlparse(final_url_2).netloc):
            return final_url_2
        if html_text_2:
            extracted2 = _extract_from_html(html_text_2, final_url_2, prefer_domains)
            if extracted2:
                return extracted2

        # Last resort: return whatever final URL we reached
        return final_url
import re

def normalize_url(url: str) -> str:
    """Clean the URL (remove tracking or extra stuff)."""
    return url.strip().split("?")[0]

async def smart_bypass(url: str, prefer_domains=None, timeout: int = 25) -> str:
    """
    Fake bypass function – just returns the input for now.
    Later you can add real bypass logic here.
    """
    # Example: if it's a gtlinks link, just return a fake Telegram link
    if "gtlinks.me" in url:
        return "https://t.me/fake_bypass_result"
    return url

import requests, ssl
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

# ✅ TLSAdapter to handle weak SSL sites
class TLSAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)

# ✅ session with TLSAdapter
session = requests.Session()
session.mount("https://", TLSAdapter())

# ✅ use safe_get instead of requests.get
def safe_get(url):
    return session.get(url, timeout=20)


# --- Your bypass functions below ---
def getlinks(url):
    res = safe_get(url)   # use safe_get here
    # parse response normally...
    return res.text



def gplinks_bypass(url: str) -> str:
    """
    Bypass gplinks.in shortener and return the final destination link.
    """
    client = cloudscraper.create_scraper()  # handles Cloudflare
    res = client.get(url, timeout=15)

    if "gplinks.in" not in res.url:
        # Already redirected
        return res.url

    soup = BeautifulSoup(res.text, "html.parser")
    try:
        form = soup.find("form")
        if not form:
            return "Bypass failed: form not found."

        action_url = form.get("action")
        inputs = form.find_all("input")

        data = {inp.get("name"): inp.get("value", "") for inp in inputs if inp.get("name")}

        # Wait for the countdown (usually 10s)
        time.sleep(10)

        headers = {"Referer": url}
        res2 = client.post(action_url, data=data, headers=headers, timeout=15, allow_redirects=False)

        if "Location" in res2.headers:
            return res2.headers["Location"]
        else:
            return "Bypass failed: no redirect found."

    except Exception as e:
        return f"Bypass error: {str(e)}"

def smart_bypass(url: str) -> str:
    """
    Detect which shortener is used and call its bypass function.
    """
    if "gplinks.in" in url:
        return gplinks_bypass(url)
    # You can add more shorteners here:
    # elif "gtlinks.me" in url:
    #     return gtlinks_bypass(url)
    # elif "droplink.co" in url:
    #     return droplink_bypass(url)
    else:
        return url  # return original if unsupported

if __name__ == "__main__":
    test_url = input("Enter gplinks.in URL: ").strip()
    final_link = smart_bypass(test_url)
    print("Bypassed URL:", final_link)
