"""
bot_manager.py — управляет двумя независимыми ботами.
Бот 1 (Трекер): отслеживает вступления в каналы → Meta CAPI
Бот 2 (Сотрудники): переписка менеджеров с сотрудниками
Оба бота можно сменить через UI без перезапуска Railway.
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, Command

log = logging.getLogger(__name__)

# Глобальные экземпляры — заменяются при смене токена
_tracker_bot: Bot | None = None
_tracker_dp:  Dispatcher | None = None
_tracker_task: asyncio.Task | None = None

_staff_bot: Bot | None = None
_staff_dp:  Dispatcher | None = None
_staff_task: asyncio.Task | None = None

# Ссылки на db и capi — инжектируются из main.py
_db = None
_send_capi = None


def init(db, send_capi_fn):
    global _db, _send_capi
    _db = db
    _send_capi = send_capi_fn


# ══════════════════════════════════════════════════════════════════════════════
# БОТ 1 — ТРЕКЕР
# ══════════════════════════════════════════════════════════════════════════════

def _build_tracker_dp() -> Dispatcher:
    dp = Dispatcher()

    @dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
    async def on_join(event: types.ChatMemberUpdated):
        channel_ids = _db.get_channel_ids()
        cid = str(event.chat.id)
        if cid not in channel_ids:
            return
        user = event.new_chat_member.user
        raw_link = event.invite_link.invite_link if event.invite_link else None
        campaign = _db.get_campaign_by_link(raw_link)
        campaign_name = campaign["name"] if campaign else "organic"
        _db.log_join(user_id=user.id, channel_id=cid, invite_link=raw_link, campaign_name=campaign_name)
        log.info(f"[BOT1] JOIN user={user.id} channel={cid} campaign={campaign_name}")
        pixel_id   = _db.get_setting("pixel_id")
        meta_token = _db.get_setting("meta_token")
        await _send_capi(pixel_id, meta_token, str(user.id), campaign_name)

        # Message Flow для трекер-бота
        asyncio.create_task(_run_flow(event.new_chat_member.user.id, cid, _tracker_bot))

    return dp


async def _run_flow(user_id: int, channel_id: str, bot: Bot | None):
    if not bot: return
    flows = _db.get_flows(channel_id, bot_type="tracker")
    for flow in flows:
        if not flow["active"]: continue
        if _db.was_flow_sent(user_id, channel_id, flow["step"]): continue
        if flow["delay_min"] > 0:
            await asyncio.sleep(flow["delay_min"] * 60)
        try:
            await bot.send_message(user_id, flow["message"])
            _db.log_flow_sent(user_id, channel_id, flow["step"])
        except Exception as e:
            log.warning(f"Flow error user={user_id}: {e}")


async def start_tracker_bot(token: str):
    global _tracker_bot, _tracker_dp, _tracker_task
    await stop_tracker_bot()
    if not token: return
    try:
        _tracker_bot = Bot(token=token)
        _tracker_dp  = _build_tracker_dp()
        _tracker_task = asyncio.create_task(
            _tracker_dp.start_polling(_tracker_bot, allowed_updates=["chat_member"])
        )
        info = await _tracker_bot.get_me()
        log.info(f"[BOT1] Started: @{info.username}")
    except Exception as e:
        log.error(f"[BOT1] Start error: {e}")
        _tracker_bot = None


async def stop_tracker_bot():
    global _tracker_bot, _tracker_dp, _tracker_task
    if _tracker_task and not _tracker_task.done():
        _tracker_task.cancel()
        try: await _tracker_task
        except: pass
    if _tracker_bot:
        try: await _tracker_bot.session.close()
        except: pass
    _tracker_bot = _tracker_dp = _tracker_task = None
    log.info("[BOT1] Stopped")


def get_tracker_bot() -> Bot | None:
    return _tracker_bot


# ══════════════════════════════════════════════════════════════════════════════
# БОТ 2 — СОТРУДНИКИ
# ══════════════════════════════════════════════════════════════════════════════

def _build_staff_dp() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def on_start(message: types.Message):
        user = message.from_user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Сотрудник"
        conv = _db.get_or_create_conversation(str(user.id), name, user.username)
        _db.get_or_create_staff(str(user.id), name, user.username, conv["id"])
        welcome = _db.get_setting("staff_welcome", "Привет! Напиши своё имя и должность, мы свяжемся с тобой 👋")
        await message.answer(welcome)
        log.info(f"[BOT2] START user={user.id} name={name}")

    @dp.message()
    async def on_message(message: types.Message):
        if message.chat.type != "private": return
        user = message.from_user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Сотрудник"
        text = message.text or message.caption or "[медиафайл]"
        conv = _db.get_or_create_conversation(str(user.id), name, user.username)
        _db.get_or_create_staff(str(user.id), name, user.username, conv["id"])
        _db.save_message(conv["id"], str(user.id), "visitor", text, message.message_id)
        _db.update_conversation_last_message(str(user.id), text, increment_unread=True)
        log.info(f"[BOT2] MSG user={user.id}: {text[:50]}")

    return dp


async def start_staff_bot(token: str):
    global _staff_bot, _staff_dp, _staff_task
    await stop_staff_bot()
    if not token: return
    try:
        _staff_bot = Bot(token=token)
        _staff_dp  = _build_staff_dp()
        _staff_task = asyncio.create_task(
            _staff_dp.start_polling(_staff_bot, allowed_updates=["message"])
        )
        info = await _staff_bot.get_me()
        log.info(f"[BOT2] Started: @{info.username}")
    except Exception as e:
        log.error(f"[BOT2] Start error: {e}")
        _staff_bot = None


async def stop_staff_bot():
    global _staff_bot, _staff_dp, _staff_task
    if _staff_task and not _staff_task.done():
        _staff_task.cancel()
        try: await _staff_task
        except: pass
    if _staff_bot:
        try: await _staff_bot.session.close()
        except: pass
    _staff_bot = _staff_dp = _staff_task = None
    log.info("[BOT2] Stopped")


def get_staff_bot() -> Bot | None:
    return _staff_bot


async def send_staff_message(tg_chat_id: str, text: str) -> bool:
    bot = get_staff_bot()
    if not bot:
        log.error("[BOT2] Bot not running")
        return False
    try:
        await bot.send_message(int(tg_chat_id), text)
        return True
    except Exception as e:
        log.error(f"[BOT2] Send error: {e}")
        return False


async def get_bot_info(bot: Bot | None) -> dict:
    if not bot:
        return {"active": False, "username": None, "name": None}
    try:
        info = await bot.get_me()
        return {"active": True, "username": info.username, "name": info.full_name, "link": f"https://t.me/{info.username}"}
    except:
        return {"active": False, "username": None, "name": None}
