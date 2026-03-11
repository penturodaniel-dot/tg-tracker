import hashlib
import time
import logging
import httpx

log = logging.getLogger(__name__)


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


async def send_event(
    pixel_id: str,
    access_token: str,
    event_name: str,          # Subscribe, Lead, InitiateCheckout, etc.
    user_id: str,
    campaign: str = "unknown",
    fbclid: str = None,
    fbp: str = None,
    utm_source: str = None,
    utm_campaign: str = None,
    client_ip: str = None,
    user_agent: str = None,
) -> bool:
    if not pixel_id or not access_token:
        log.warning("Meta CAPI: pixel_id or token not set")
        return False

    url = f"https://graph.facebook.com/v19.0/{pixel_id}/events"

    user_data = {"external_id": _hash(user_id)}
    if fbp:    user_data["fbp"]        = fbp
    if fbclid: user_data["fbc"]        = f"fb.1.{int(time.time()*1000)}.{fbclid}"
    if client_ip:   user_data["client_ip_address"] = client_ip
    if user_agent:  user_data["client_user_agent"]  = user_agent

    custom_data = {"campaign": campaign}
    if utm_source:   custom_data["utm_source"]   = utm_source
    if utm_campaign: custom_data["utm_campaign"] = utm_campaign

    payload = {
        "data": [{
            "event_name": event_name,
            "event_time": int(time.time()),
            "action_source": "other",
            "user_data": user_data,
            "custom_data": custom_data,
        }],
        "access_token": access_token,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if resp.status_code == 200 and data.get("events_received", 0) > 0:
                log.info(f"Meta CAPI OK: {event_name} user={user_id} campaign={campaign}")
                return True
            log.error(f"Meta CAPI error {resp.status_code}: {data}")
            return False
    except Exception as e:
        log.error(f"Meta CAPI exception: {e}")
        return False


# Удобные обёртки
async def send_subscribe_event(pixel_id, access_token, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, "Subscribe", user_id, campaign, **kwargs)

async def send_lead_event(pixel_id, access_token, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, "Lead", user_id, campaign, **kwargs)

async def send_custom_event(pixel_id, access_token, event_name, user_id, campaign="unknown", **kwargs):
    return await send_event(pixel_id, access_token, event_name, user_id, campaign, **kwargs)
