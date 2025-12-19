import os
import re
import aiohttp
from urllib.parse import urlparse

import settings


_INVALID_WIN_CHARS = re.compile(r"[<>:\\/?*\"|]+")


def _safe_filename(name: str, fallback: str = "yandex_file") -> str:
    name = (name or "").strip()
    if not name:
        return fallback
    name = _INVALID_WIN_CHARS.sub("_", name)
    name = name.strip(" .")
    return name or fallback


def _filename_from_cd(content_disposition: str | None) -> str | None:
    if not content_disposition:
        return None
    # Very small and permissive parser: look for filename="..." or filename=...
    m = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"filename=\"([^\"]+)\"", content_disposition, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"filename=([^;]+)", content_disposition, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"')
    return None


class YandexDiskPublicStrategy:
    """Download files from public Yandex Disk share links (disk.yandex.ru / yadi.sk).

    Uses public Disk API endpoints, no OAuth required for public resources.
    """

    API_BASE = "https://cloud-api.yandex.net/v1/disk/public"

    def __init__(self, url: str):
        self.url = url

    async def download(self, save_path: str):
        os.makedirs(save_path, exist_ok=True)

        connector = aiohttp.TCPConnector(ssl=False)
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)",
        }

        async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
            # 1) Read metadata (name/size/type) if possible
            name = None
            size = None
            resource_type = None
            try:
                params = {"public_key": self.url, "fields": "name,size,type,mime_type"}
                async with session.get(f"{self.API_BASE}/resources", params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        name = data.get("name")
                        size = data.get("size")
                        resource_type = data.get("type")
            except Exception:
                pass

            if resource_type == "dir":
                return None, save_path, "Yandex Disk folder links are not supported", None

            # 2) Get one-time download URL
            try:
                async with session.get(f"{self.API_BASE}/resources/download", params={"public_key": self.url}) as resp:
                    if resp.status != 200:
                        try:
                            data = await resp.json()
                            msg = data.get("message") or data.get("description")
                        except Exception:
                            msg = None
                        return None, save_path, msg or f"Yandex Disk API error: {resp.status}", None
                    data = await resp.json()
                    href = data.get("href")
                    if not href:
                        return None, save_path, "Yandex Disk: no download link", None
            except Exception as e:
                return None, save_path, f"Yandex Disk API request failed: {e}", None

            # 3) Download
            try:
                async with session.get(href, allow_redirects=True) as resp:
                    if resp.status != 200:
                        return None, save_path, f"Yandex Disk download failed: {resp.status}", None

                    cl = resp.headers.get("Content-Length")
                    if cl:
                        try:
                            if int(cl) > int(getattr(settings, "MAX_FILE_SIZE", 50 * 1024 * 1024)):
                                return None, save_path, "File is too big", None
                        except Exception:
                            pass

                    cd = resp.headers.get("Content-Disposition")
                    cd_name = _filename_from_cd(cd)

                    filename = _safe_filename(cd_name or name or "yandex_file")

                    # If filename has no extension but original URL has something, keep it.
                    if "." not in filename:
                        try:
                            path = urlparse(self.url).path
                            tail = os.path.basename(path)
                            if "." in tail:
                                filename = _safe_filename(filename + os.path.splitext(tail)[1])
                        except Exception:
                            pass

                    out_path = os.path.join(save_path, filename)

                    total = 0
                    max_size = int(getattr(settings, "MAX_FILE_SIZE", 50 * 1024 * 1024))
                    with open(out_path, "wb") as f:
                        async for chunk in resp.content.iter_chunked(1024 * 256):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > max_size:
                                try:
                                    f.close()
                                except Exception:
                                    pass
                                try:
                                    os.remove(out_path)
                                except Exception:
                                    pass
                                return None, save_path, "File is too big", None
                            f.write(chunk)

                    meta = {
                        "title": filename,
                        "uploader": "Yandex Disk",
                        "extractor": "yandex_disk_public",
                    }
                    return [out_path], save_path, None, meta

            except Exception as e:
                return None, save_path, f"Yandex Disk download error: {e}", None
