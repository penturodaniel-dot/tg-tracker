"""
tiktok_capi.py — TikTok Events API (аналог meta_capi.py)
──────────────────────────────────────────────────────────
Документация: https://business-api.tiktok.com/portal/docs?id=1741601162187777

Для matching событий нужно:
1. ttclid   — параметр из URL (как fbclid у Facebook)
2. ttp      — cookie _ttp с лендинга (TikTok Pixel устанавливает сам)
3. external_id — sha256(user_id)

Endpoint: POST https://business-api.tiktok.com/open_api/v1.3/pixel/track/
"""

import hashlib
import time
import logging
import httpx

log = logging.getLogger(__name__)

_API_URL = "https://business-api.tiktok.com/open_api/v1.3/pixel/track/"


def _hash(value: str) -> str:
    """SHA256 хэш для PII данных"""
    if not value:
        return None
    return hashlib.sha256(str(value).strip().lower().encode()).hexdigest()


async def send_event(
    pixel_id: str,
    access_token: str,
    event_name: str,          # "SubmitForm" = Lead аналог
    user_id: str = "",
    ip: str = None,
    user_agent: str = None,
    ttclid: str = None,       # TikTok click ID (как fbclid)
    ttp: str = None,          # TikTok cookie _ttp (как fbp)
    utm_source: str = None,
    utm_campaign: str = None,
    test_event_code: str = None,
    event_source_url: str = None,
) -> bool:
    if not pixel_id or not access_token:
        log.warning("TikTok CAPI: pixel_id or access_token not set")
        return False

    # Контекст пользователя
    user_context = {}
    if user_id:
        user_context["external_id"] = _hash(str(user_id))
    if ip:
        user_context["ip"] = ip
    if user_agent:
        user_context["user_agent"] = user_agent
    if ttclid:
        user_context["ttclid"] = ttclid
    if ttp:
        user_context["ttp"] = ttp

    # Свойства события
    properties = {}
    if utm_campaign:
        properties["query"] = utm_campaign
    if event_source_url:
        properties["page_url"] = event_source_url

    payload = {
        "pixel_code":   pixel_id,
        "event":        event_name,
        "event_time":   int(time.time()),
        "context": {
            "user": user_context,
            "page": {
                "url": event_source_url or "",
                "referrer": f"utm_source={utm_source}" if utm_source else "",
            },
            "ad": {
                "callback": ttclid or "",
            },
        },
        "properties": properties,
    }

    if test_event_code:
        payload["test_event_code"] = test_event_code

    headers = {
        "Access-Token": access_token,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(_API_URL, json=payload, headers=headers)
            data = resp.json()
            code = data.get("code", -1)
            if resp.status_code == 200 and code == 0:
                log.info(
                    f"TikTok CAPI ✅ {event_name} user={user_id} "
                    f"ttp={'✓' if ttp else '—'} ttclid={'✓' if ttclid else '—'}"
                )
                return True
            log.error(f"TikTok CAPI error {resp.status_code} code={code}: {data.get('message','')}")
            return False
    except Exception as e:
        log.error(f"TikTok CAPI exception: {e}")
        return False


async def send_lead_event(
    pixel_id: str,
    access_token: str,
    user_id: str = "",
    **kwargs,
) -> bool:
    """Lead событие — аналог meta_capi.send_lead_event()"""
    return await send_event(
        pixel_id, access_token,
        event_name="SubmitForm",
        user_id=user_id,
        **kwargs,
    )


async def send_subscribe_event(
    pixel_id: str,
    access_token: str,
    user_id: str = "",
    **kwargs,
) -> bool:
    """Subscribe событие — с лендинга при клике на кнопку"""
    return await send_event(
        pixel_id, access_token,
        event_name="Subscribe",
        user_id=user_id,
        **kwargs,
    )
