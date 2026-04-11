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
    fbc: str = None,
    utm_source: str = None,
    utm_campaign: str = None,
    client_ip: str = None,
    user_agent: str = None,
    test_event_code: str = None,
    event_source_url: str = None,
    event_time: int = None,
    first_name: str = None,
    last_name: str = None,
    phone: str = None,
    event_id: str = None,
) -> bool:
    if not pixel_id or not access_token:
        log.debug("Meta CAPI: pixel_id or token not set (skipped)")
        return False

    user_data = {}
    if user_id:
        user_data["external_id"] = [_hash(str(user_id))]
    if fbp:
        user_data["fbp"] = fbp
    # Используем готовый fbc (сгенерированный в момент клика) или генерируем из fbclid
    _fbc = fbc or _make_fbc(fbclid)
    if _fbc:
        user_data["fbc"] = _fbc
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent
    if first_name:
        user_data["fn"] = [_hash(first_name)]
    if last_name:
        user_data["ln"] = [_hash(last_name)]
    if phone:
        # Нормализуем: только цифры, без +
        _ph = "".join(c for c in str(phone) if c.isdigit())
        if _ph:
            user_data["ph"] = [_hash(_ph)]

    custom_data = {}
    if utm_source:   custom_data["utm_source"]   = utm_source
    if utm_campaign: custom_data["utm_campaign"] = utm_campaign
    if campaign:     custom_data["campaign"]     = campaign

    # action_source зависит от типа события:
    # - website: события инициированные на сайте (Lead, Contact, PageView)
    # - system_generated: события из бота/сервера (Subscribe из Telegram)
    _website_events = {"Lead", "Contact", "PageView", "ViewContent", "Search",
                       "CompleteRegistration", "Purchase"}
    if event_name == "Lead":
        # Lead всегда website — человек кликнул рекламу и написал нам, это website-конверсия
        _action_source = "website"
        _source_url = {"event_source_url": event_source_url or "https://t.me/"}
    elif event_name in _website_events:
        _action_source = "website"
        _source_url = {"event_source_url": event_source_url or "https://t.me/"}
    else:
        # Subscribe и др. из бота:
        # - в тестовом режиме используем "website" чтобы событие было видно в Test Events
        # - в продакшне используем "system_generated" (правильный тип для бот-событий)
        if test_event_code:
            _action_source = "website"
            _source_url = {"event_source_url": event_source_url or "https://t.me/"}
        else:
            _action_source = "system_generated"
            _source_url = {"event_source_url": event_source_url} if event_source_url else {}

    _event_entry = {
        "event_name": event_name,
        "event_time": event_time if event_time else int(time.time()),
        "action_source": _action_source,
        "user_data": user_data,
        "custom_data": custom_data,
        **_source_url,
    }
    if event_id:
        _event_entry["event_id"] = event_id

    payload = {
        "data": [_event_entry],
        "access_token": access_token,
    }
    if test_event_code:
        payload["test_event_code"] = test_event_code

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"https://graph.facebook.com/v19.0/{pixel_id}/events", json=payload)
            data = resp.json()
            if resp.status_code == 200 and data.get("events_received", 0) > 0:
                _msgs = data.get('messages') or []
                _test_tag = f" 🧪 TEST={_msgs}" if _msgs else ""
                log.info(f"Meta CAPI ✅ {event_name} user={user_id} fbp={'✓' if fbp else '—'} fbc={'✓' if fbc else '—'} test_code={'✓' if test_event_code else '—'} events_received={data.get('events_received')}{_test_tag}")
                return True
            log.error(f"Meta CAPI ❌ {resp.status_code}: events_received={data.get('events_received',0)} error={data.get('error')} messages={data.get('messages')} full={data}")
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
