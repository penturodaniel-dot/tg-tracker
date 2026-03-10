import hashlib
import time
import logging
import httpx

log = logging.getLogger(__name__)


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


async def send_lead_event(
    pixel_id: str,
    access_token: str,
    user_id: str,
    campaign: str = "unknown",
) -> bool:
    """
    Отправляет событие Subscribe в Meta Conversions API.
    Документация: https://developers.facebook.com/docs/marketing-api/conversions-api
    """
    url = f"https://graph.facebook.com/v19.0/{pixel_id}/events"

    payload = {
        "data": [
            {
                "event_name": "Subscribe",
                "event_time": int(time.time()),
                "action_source": "other",           # не веб — поэтому "other"
                "user_data": {
                    "external_id": _hash(user_id),  # хешированный Telegram user_id
                },
                "custom_data": {
                    "campaign": campaign,
                    "content_name": "Telegram Channel Join",
                },
            }
        ],
        "access_token": access_token,
        # test_event_code: раскомментируй для тестирования в Events Manager
        # "test_event_code": "TEST12345",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            if resp.status_code == 200 and data.get("events_received", 0) > 0:
                log.info(f"Meta CAPI OK: {data}")
                return True
            else:
                log.error(f"Meta CAPI error {resp.status_code}: {data}")
                return False
    except Exception as e:
        log.error(f"Meta CAPI exception: {e}")
        return False
