"""
Meta Conversions API v19.0
──────────────────────────
Для matching событий в Ads Manager (не только Test Events) нужно:
1. fbp  — cookie _fbp с лендинга (Meta Pixel устанавливает его сам)
2. fbc  — fb.1.{ts}.{fbclid} — из fbclid URL параметра
3. external_id — sha256(telegram_user_id)

Без fbp и fbc события видны в Test Events но НЕ связываются с рекламными кампаниями.
"""
import hashlib
import time
import logging
import httpx

log = logging.getLogger(__name__)


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _make_fbc(fbclid: str) -> str:
    if not fbclid: return None
    return f"fb.1.{int(time.time()*1000)}.{fbclid}"


async def send_event(
    pixel_id: str,
    access_token: str,
    event_name: str,
    user_id: str,
    campaign: str = "unknown",
    fbclid: str = None,
    fbp: str = None,
    utm_source: str = None,
    utm_campaign: str = None,
    client_ip: str = None,
    user_agent: str = None,
    test_event_code: str = None,
    event_source_url: str = None,
) -> bool:
    if not pixel_id or not access_token:
        log.warning("Meta CAPI: pixel_id or token not set")
        return False

    user_data = {}
    if user_id:
        user_data["external_id"] = [_hash(str(user_id))]
    if fbp:
        user_data["fbp"] = fbp
    fbc = _make_fbc(fbclid)
    if fbc:
        user_data["fbc"] = fbc
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent

    custom_data = {}
    if utm_source:   custom_data["utm_source"]   = utm_source
    if utm_campaign: custom_data["utm_campaign"] = utm_campaign
    if campaign:     custom_data["campaign"]     = campaign

    # Lead отправляется из CRM менеджером — это system_generated
    # Subscribe/другие события с лендинга — website
    _action_source = "system_generated" if event_name == "Lead" else "website"
    _source_url = {} if event_name == "Lead" else {"event_source_url": event_source_url or "https://t.me/"}

    payload = {
        "data": [{
            "event_name": event_name,
            "event_time": int(time.time()),
            "action_source": _action_source,
            "user_data": user_data,
            "custom_data": custom_data,
            **_source_url,
        }],
        "access_token": access_token,
    }
    if test_event_code:
        payload["test_event_code"] = test_event_code

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"https://graph.facebook.com/v19.0/{pixel_id}/events", json=payload)
            data = resp.json()
            if resp.status_code == 200 and data.get("events_received", 0) > 0:
                log.info(f"Meta CAPI ✅ {event_name} user={user_id} fbp={'✓' if fbp else '—'} fbc={'✓' if fbc else '—'}")
                return True
            log.error(f"Meta CAPI error {resp.status_code}: {data}")
            return False
    except Exception as e:
        log.error(f"Meta CAPI exception: {e}")
        return False


async def send_subscribe_event(pixel_id, access_token, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, "Subscribe", user_id, campaign, **kwargs)

async def send_lead_event(pixel_id, access_token, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, "Lead", user_id, campaign, **kwargs)

async def send_custom_event(pixel_id, access_token, event_name, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, event_name, user_id, campaign, **kwargs)
