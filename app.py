import os
import re
import asyncio
import logging
from typing import List, Tuple
from pyrogram.enums import ChatAction

from pyrogram import Client, filters
from pyrogram.types import Message
from dotenv import load_dotenv

# Local
from bypass.engine import smart_bypass, normalize_url

load_dotenv()

API_ID = int(os.getenv("API_ID", "24196359"))
API_HASH = os.getenv("API_HASH", "20a1b32381ed174799e8af8def3e176b")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8225310670:AAFLJ4DvtQ9ENOS8Z1Fqy2u24ZbRGdp8bbQ")
# Optional keepalive HTTP server (for platforms that require an open port)
KEEPALIVE = os.getenv("KEEPALIVE", "false").lower() == "true"
PORT = int(os.getenv("PORT", "8080"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("bypass-bot")

if not (API_ID and API_HASH and BOT_TOKEN):
    raise SystemExit(
        "Missing API_ID/API_HASH/BOT_TOKEN. "
        "Create .env from .env.example and fill credentials."
    )

app = Client(
    "BypassBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=8,
    in_memory=True
)

URL_RE = re.compile(
    r"(https?://[^\s<>\"'\)]+)",
    re.IGNORECASE
)

TARGET_PREFERRED = (
    "t.me", "telegram.me", "telegram.dog",
    "drive.google.com", "mega.nz", "mediafire.com",
    "pixeldrain.com", "github.com"
)

HELP_TEXT = (
    "**🧭 How to use**\n"
    "• Send me **any short link** and I’ll try to bypass it.\n"
    "• For **multiple links**, send them on separate lines or in one message.\n\n"
    "**Examples**\n"
    "`https://bit.ly/...`\n"
    "`https://gtlinks.me/...`\n\n"
    "**Commands**\n"
    "/ping – check bot health\n"
    "/help – show this help"
)

def split_urls(text: str) -> List[str]:
    return [m.group(1) for m in URL_RE.finditer(text)]

def pretty_pairs(pairs: List[Tuple[str, str]]) -> str:
    lines = []
    for src, dst in pairs:
        lines.append(f"🔗 **Original**: {src}")
        lines.append(f"✅ **Bypassed**: {dst}\n")
    return "\n".join(lines) if lines else "No URLs detected."

@app.on_message(filters.command("start"))
async def start_handler(_: Client, m: Message):
    await m.reply_text("👋 **Hi!** Send me a short link and I’ll bypass it.\n\n" + HELP_TEXT, disable_web_page_preview=True)

@app.on_message(filters.command("help"))
async def help_handler(_: Client, m: Message):
    await m.reply_text(HELP_TEXT, disable_web_page_preview=True)

@app.on_message(filters.command("ping"))
async def ping_handler(_: Client, m: Message):
    await m.reply_text("🏓 Pong!")

@app.on_message(filters.text & ~filters.command(["start", "help", "ping"]))
async def bypass_handler(_: Client, m: Message):
    text = (m.text or "").strip()
    urls = split_urls(text)
    if not urls:
        return await m.reply_text("⚠️ Please send a valid URL (starts with http:// or https://).")

    # Normalize + dedupe while preserving order
    seen = set()
    normed = []
    for u in urls:
        nu = normalize_url(u)
        if nu not in seen:
            seen.add(nu)
            normed.append(nu)

    await m.reply_chat_action("typing")
    results: List[Tuple[str, str]] = []

    # Process in parallel but gentle on flood/waf
    sem = asyncio.Semaphore(5)
    async def task(u: str):
        async with sem:
            try:
                bypassed = await smart_bypass(u, prefer_domains=TARGET_PREFERRED, timeout=25)
                results.append((u, bypassed))
            except Exception as e:
                log.exception("Bypass failed for %s", u)
                results.append((u, f"❌ Error: {e}"))

    await asyncio.gather(*(task(u) for u in normed))

    # Keep original order in output
    ordered = [(u, next(dst for src, dst in results if src == u)) for u in normed]
    reply = pretty_pairs(ordered)

    await m.reply_text(reply, disable_web_page_preview=False)

# Optional keepalive HTTP server (for platforms that require a port)
async def _run_keepalive():
    from aiohttp import web
    async def ping(_):
        return web.Response(text="ok")
    app_web = web.Application()
    app_web.add_routes([web.get("/", ping), web.get("/ping", ping), web.head("/", ping)])
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info("Keepalive server on :%d", PORT)

if __name__ == "__main__":
    if KEEPALIVE:
        loop = asyncio.get_event_loop()
        loop.create_task(_run_keepalive())
        log.info("KEEPALIVE enabled, starting bot + web server")
        app.run()
    else:
        log.info("Starting bot without keepalive HTTP server")
        app.run()
