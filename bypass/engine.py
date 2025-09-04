import asyncio
import html
import re
from typing import Optional, Sequence, Iterable
from urllib.parse import urlparse, urljoin
from aiohttp import ClientSession, ClientTimeout, TCPConnector
import cloudscraper
from bs4 import BeautifulSoup
import functools
import requests, json

# ---------------- Config ---------------- #
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

SHORTENERS = {
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "tiny.one",
    "cutt.ly", "rebrand.ly", "ouo.io", "shorte.st", "adf.ly",
    "linkvertise.com", "lnk.to", "gtlinks.me", "droplink.co",
    "tnlink.in", "tnshort.net", "rocklinks.net", "ez4short.com",
    "ouo.press", "boost.ink", "gplinks.in", "lksfy.com"
}

PREFERRED_DOMAINS = ("t.me", "telegram.me", "telegram.dog")

PUBLIC_APIS = [
    "https://api.bypass.vip/?url=",
    "https://bypass.bot.nu/bypass?url=",
    "https://linkvertisebypass.org/api/?url="
]

META_REFRESH_RE = re.compile(
    r'<meta\s+http-equiv=["\']refresh["\'][^>]*?url=([^"\'>\s]+)', re.IGNORECASE
)
JS_REDIRECT_RE = re.compile(
    r'(?:window\.location(?:\.href)?|location\.href)\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE
)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)


# ---------------- Utilities ---------------- #
def normalize_url(url: str) -> str:
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "http://" + url
    return url


def is_shortener(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in SHORTENERS)


def preferred_link(candidates: Iterable[str], prefer: Sequence[str]) -> Optional[str]:
    """Return the best URL based on preferred domains."""
    def score(u: str) -> int:
        host = urlparse(u).netloc.lower()
        for i, dom in enumerate(prefer, start=1):
            if host == dom or host.endswith("." + dom):
                return 1000 - i
        return 0

    best = None
    best_score = -1
    for u in candidates:
        s = score(u)
        if s > best_score:
            best_score = s
            best = u
    return best or next(iter(candidates), None)


async def fetch(session: ClientSession, url: str):
    """Fetch URL and return (final_url, html_text if any)."""
    resp = await session.get(url, allow_redirects=True)
    html_text = ""
    if "text/html" in resp.headers.get("content-type", "").lower():
        html_text = await resp.text(errors="ignore")
    return str(resp.url), html_text


def extract_redirect(html_text: str, base_url: str, prefer: Sequence[str]) -> Optional[str]:
    """Extract redirect from meta, JS, or anchor tags."""
    m = META_REFRESH_RE.search(html_text)
    if m:
        return urljoin(base_url, html.unescape(m.group(1)))

    js_links = JS_REDIRECT_RE.findall(html_text)
    if js_links:
        hrefs = [urljoin(base_url, html.unescape(u)) for u in js_links]
        return preferred_link(hrefs, prefer)

    hrefs = [urljoin(base_url, html.unescape(h)) for h in HREF_RE.findall(html_text)]
    if hrefs:
        return preferred_link(hrefs, prefer)
    return None


# ---------------- Cloudflare Handling ---------------- #
def cloudscraper_bypass(url: str) -> tuple[str, str]:
    """Bypass Cloudflare challenge using cloudscraper."""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    response = scraper.get(url)
    return response.url, response.text


def needs_cloudflare_bypass(html_text: str) -> bool:
    return "cf-challenge" in html_text or "Checking your browser" in html_text


# ---------------- Special Bypasses ---------------- #
async def gplinks_bypass(url: str) -> str:
    """Handle gplinks.in shortener."""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    loop = asyncio.get_running_loop()

    headers = {"User-Agent": USER_AGENT, "Referer": url}
    res = await loop.run_in_executor(None, functools.partial(scraper.get, url, headers=headers, timeout=15))

    if "gplinks.in" not in res.url:
        return res.url

    soup = BeautifulSoup(res.text, "html.parser")
    form = soup.find("form")
    if not form:
        return res.url

    action_url = form.get("action")
    data = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}

    await asyncio.sleep(7)  # Wait for countdown

    res2 = await loop.run_in_executor(
        None,
        functools.partial(scraper.post, action_url, data=data, headers=headers, timeout=15, allow_redirects=False)
    )

    return res2.headers.get("Location", res.url)


async def ouo_io_bypass(url: str) -> str:
    """Handle ouo.io shortener using cloudscraper."""
    return cloudscraper_bypass(url)[0]


async def try_public_apis(url: str) -> Optional[str]:
    for base in PUBLIC_APIS:
        try:
            async with ClientSession() as session:
                async with session.get(f"{base}{url}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("success") and data.get("destination"):
                            return data["destination"]
        except:
            continue
    return None


# ---------------- Main Logic ---------------- #
async def smart_bypass(url: str, prefer=PREFERRED_DOMAINS, timeout: int = 25, use_api=True) -> str:
    norm = normalize_url(url)
    parsed = urlparse(norm)
    host = parsed.netloc.lower()

    # Special handlers
    if "gplinks.in" in host:
        return await gplinks_bypass(norm)
    elif "ouo.io" in host or "ouo.press" in host:
        return await ouo_io_bypass(norm)

    # Try aiohttp first
    connector = TCPConnector(ssl=False, limit=20)
    async with ClientSession(timeout=ClientTimeout(total=timeout), connector=connector, headers={"User-Agent": USER_AGENT}) as session:
        final_url, html_text = await fetch(session, norm)

        # Cloudflare bypass
        if needs_cloudflare_bypass(html_text):
            final_url, html_text = cloudscraper_bypass(norm)

        if not is_shortener(urlparse(final_url).netloc):
            return final_url

        if html_text:
            extracted = extract_redirect(html_text, final_url, prefer)
            if extracted:
                return extracted

        # Second fetch attempt
        final_url_2, html_text_2 = await fetch(session, final_url)
        if needs_cloudflare_bypass(html_text_2):
            final_url_2, html_text_2 = cloudscraper_bypass(final_url)

        if not is_shortener(urlparse(final_url_2).netloc):
            return final_url_2
        if html_text_2:
            extracted2 = extract_redirect(html_text_2, final_url_2, prefer)
            if extracted2:
                return extracted2

    # API fallback
    if use_api:
        api_result = await try_public_apis(norm)
        if api_result:
            return api_result

    return final_url


# ---------------- Sync Helper ---------------- #
def bypass(url: str) -> str:
    """Run bypass synchronously."""
    return asyncio.run(smart_bypass(url))


# ---------------- Extra API (FreeSeptember) ---------------- #
def uni(url):
    res = requests.post("https://freeseptemberapi.vercel.app/bypass", json={"url": url})
    try:
        _j = res.json()
        return _j.get("url", res.text)
    except:
        return res.text


# ---------------- Example Run ---------------- #
if __name__ == "__main__":
    test_links = [
        "https://lksfy.com/0l1Zgq",
        "https://gplinks.co/P3rGI",
        "https://ouo.io/abc123",
        "https://bit.ly/3xyz123",
        "https://droplink.co/example"
    ]

    async def main():
        for link in test_links:
            print(f"🔗 Original: {link}")
            result = await smart_bypass(link)
            print(f"✅ Bypassed: {result}\n")

    asyncio.run(main())
    print("FreeSeptember API:", uni("https://earn4link.in"))
