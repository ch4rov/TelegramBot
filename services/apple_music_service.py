import re
import html
import aiohttp


async def get_apple_music_metadata(url: str) -> dict | None:
    """Best-effort metadata extraction for music.apple.com links.

    Returns dict like: {"artist": str|None, "track": str|None, "title": str|None}
    """
    if not url or "music.apple.com" not in (url or "").lower():
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
    }

    try:
        async with aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(ssl=False)) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()
    except Exception:
        return None

    def _meta(prop: str) -> str | None:
        m = re.search(rf'<meta\s+property="{re.escape(prop)}"\s+content="(.*?)"\s*/?>', text, flags=re.IGNORECASE)
        if m:
            return html.unescape(m.group(1)).strip()
        return None

    og_title = _meta("og:title")
    og_desc = _meta("og:description")

    # Heuristics:
    # og:title often contains track/album + " - Apple Music".
    # og:description often contains artist or subtitle.
    title = og_title
    if title:
        title = re.sub(r"\s*[-|—]\s*Apple\s+Music\s*$", "", title, flags=re.IGNORECASE).strip()

    artist = None
    track = None

    if og_desc:
        # Description sometimes starts with artist.
        artist = og_desc.split("·")[0].strip() if "·" in og_desc else og_desc.strip()

    if title:
        # If title is like "Song - Single" or "Song" keep as track.
        track = re.sub(r"\s*-\s*(Single|EP|Album)\s*$", "", title, flags=re.IGNORECASE).strip()

    # If track looks like "Artist - Song" split.
    if track and " - " in track and not artist:
        parts = track.split(" - ", 1)
        if len(parts) == 2:
            artist = parts[0].strip()
            track = parts[1].strip()

    return {
        "artist": artist,
        "track": track,
        "title": track or title,
    }
