"""
Cloudinary upload helper — используется в bot_manager и main.py
"""
import os
import hashlib
import hmac
import time
import logging
import httpx

log = logging.getLogger(__name__)

CLOUD_NAME  = os.getenv("CLOUDINARY_CLOUD_NAME", "")
API_KEY     = os.getenv("CLOUDINARY_API_KEY", "")
API_SECRET  = os.getenv("CLOUDINARY_API_SECRET", "")


def _sign(params: dict) -> str:
    """Создаёт подпись для Cloudinary API."""
    to_sign = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
    return hashlib.sha1((to_sign + API_SECRET).encode()).hexdigest()


async def upload_bytes(data: bytes, resource_type: str = "image",
                       folder: str = "tg_chat") -> str | None:
    """
    Загружает байты в Cloudinary.
    resource_type: 'image', 'video', 'raw'
    Возвращает secure_url или None при ошибке.
    """
    if not all([CLOUD_NAME, API_KEY, API_SECRET]):
        log.warning("Cloudinary credentials not set")
        return None
    try:
        ts = int(time.time())
        params = {"folder": folder, "timestamp": ts}
        sig = _sign(params)
        url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/{resource_type}/upload"
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, data={
                "api_key": API_KEY,
                "timestamp": ts,
                "folder": folder,
                "signature": sig,
            }, files={"file": ("media", data)})
        if r.status_code == 200:
            return r.json().get("secure_url")
        log.warning(f"Cloudinary upload error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        log.error(f"Cloudinary upload exception: {e}")
    return None


async def upload_from_url(src_url: str, resource_type: str = "image",
                          folder: str = "tg_chat") -> str | None:
    """Скачивает файл по URL и загружает в Cloudinary."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(src_url)
        if r.status_code == 200:
            return await upload_bytes(r.content, resource_type, folder)
    except Exception as e:
        log.error(f"upload_from_url error: {e}")
    return None
