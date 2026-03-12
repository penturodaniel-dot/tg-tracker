"""
bot_manager.py v5
Бот 1 — Трекер: вступления в каналы → Meta CAPI Subscribe
Бот 2 — Сотрудники: переписка → Meta CAPI Lead
Уведомления менеджеру при новом сообщении
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, Command

log = logging.getLogger(__name__)

_tracker_bot: Bot | None = None
_tracker_dp:  Dispatcher | None = None
_tracker_task: asyncio.Task | None = None

_staff_bot: Bot | None = None
_staff_dp:  Dispatcher | None = None
_staff_task: asyncio.Task | None = None

_db = None
_meta = None


def init(db, meta_module):
    global _db, _meta
    _db = db
    _meta = meta_module


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

        # Ищем click_id по invite_link если есть
        click_id = None
        if campaign:
            click_id = campaign.get("click_id")

        join_id = _db.log_join(
            user_id=user.id,
            channel_id=cid,
            invite_link=raw_link,
            campaign_name=campaign_name,
            click_id=click_id
        )

        # Получаем UTM данные если есть click_id
        click_data = _db.get_click(click_id) if click_id else {}
        if click_data:
            _db.save_utm(click_data, join_id=join_id)

        pixel_id   = _db.get_setting("pixel_id")
        meta_token = _db.get_setting("meta_token")
        await _meta.send_subscribe_event(
            pixel_id, meta_token, str(user.id), campaign_name,
            fbclid=click_data.get("fbclid") if click_data else None,
            fbp=click_data.get("fbp") if click_data else None,
            utm_source=click_data.get("utm_source") if click_data else None,
            utm_campaign=click_data.get("utm_campaign") if click_data else None,
        )
        log.info(f"[BOT1] JOIN user={user.id} channel={cid} campaign={campaign_name}")
        asyncio.create_task(_run_flow(user.id, cid, _tracker_bot))

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
            _tracker_dp.start_polling(
                _tracker_bot,
                allowed_updates=["chat_member"],
                drop_pending_updates=True,
                handle_signals=False,
            )
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
    if _tracker_dp:
        try: await _tracker_dp.stop_polling()
        except: pass
    if _tracker_bot:
        try: await _tracker_bot.session.close()
        except: pass
    _tracker_bot = _tracker_dp = _tracker_task = None


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
        staff = _db.get_or_create_staff(str(user.id), name, user.username, conv["id"])

        # Получаем фото профиля
        try:
            photos = await message.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count > 0:
                file = await message.bot.get_file(photos.photos[0][-1].file_id)
                photo_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
                _db.update_conv_profile(conv["id"], photo_url=photo_url)
        except Exception as e:
            log.warning(f"[BOT2] photo fetch error: {e}")

        # Проверяем UTM из start параметра
        start_param = message.text.split()[-1] if len(message.text.split()) > 1 else None
        if start_param and start_param.startswith("ref_"):
            click_id = start_param[4:]
            click_data = _db.get_click(click_id)
            if click_data:
                _db.save_utm(click_data, conversation_id=conv["id"])
                log.info(f"[BOT2] UTM linked conv={conv['id']} click={click_id}")

        # Отправляем Lead в Meta CAPI если ещё не отправляли
        if not staff.get("fb_event_sent"):
            utm = _db.get_utm_by_conv(conv["id"])
            pixel_id   = _db.get_setting("pixel_id_staff") or _db.get_setting("pixel_id")
            meta_token = _db.get_setting("meta_token_staff") or _db.get_setting("meta_token")
            sent = await _meta.send_lead_event(
                pixel_id, meta_token, str(user.id),
                campaign=utm.get("utm_campaign", "staff_bot") if utm else "staff_bot",
                fbclid=utm.get("fbclid") if utm else None,
                fbp=utm.get("fbp") if utm else None,
            )
            if sent:
                _db.set_staff_fb_event(staff["id"], "Lead")
                _db.set_conv_fb_event(conv["id"], "Lead")

        # Уведомление менеджеру
        asyncio.create_task(_notify_manager(name, conv["id"], "start"))

        welcome = _db.get_setting("staff_welcome", "Привет! Напиши своё имя и должность 👋")
        await message.answer(welcome)
        log.info(f"[BOT2] START user={user.id} name={name}")

    @dp.message()
    async def on_message(message: types.Message):
        if message.chat.type != "private": return
        user = message.from_user
        name = f"{user.first_name or ''} {user.last_name or ''}".strip() or "Сотрудник"
        text = message.text or message.caption or ""

        media_url  = None
        media_type = None

        # Скачиваем медиа через Telegram file API
        file_obj = None
        if message.photo:
            file_obj = message.photo[-1]  # наибольшее разрешение
            media_type = "image/jpeg"
            if not text: text = "[фото]"
        elif message.document:
            file_obj = message.document
            media_type = message.document.mime_type or "application/octet-stream"
            if not text: text = f"[файл: {message.document.file_name or 'документ'}]"
        elif message.video:
            file_obj = message.video
            media_type = "video/mp4"
            if not text: text = "[видео]"
        elif message.voice:
            file_obj = message.voice
            media_type = "audio/ogg"
            if not text: text = "[голосовое]"

        if file_obj:
            try:
                tg_file = await _staff_bot.get_file(file_obj.file_id)
                # Прямая ссылка на файл через Telegram CDN
                bot_token = _db.get_setting("bot2_token") or ""
                if bot_token:
                    media_url = f"https://api.telegram.org/file/bot{bot_token}/{tg_file.file_path}"
            except Exception as e:
                log.warning(f"[BOT2] Media download error: {e}")

        if not text: text = "[сообщение]"

        conv = _db.get_or_create_conversation(str(user.id), name, user.username)
        _db.get_or_create_staff(str(user.id), name, user.username, conv["id"])
        _db.save_message(conv["id"], str(user.id), "visitor", text, message.message_id,
                         media_url=media_url, media_type=media_type)
        _db.update_conversation_last_message(str(user.id), text, increment_unread=True)

        # Уведомление менеджеру
        asyncio.create_task(_notify_manager(name, conv["id"], text))
        log.info(f"[BOT2] MSG user={user.id}: {text[:50]}")

    return dp


async def _notify_manager(sender_name: str, conv_id: int, text: str):
    """Отправляет уведомление менеджеру в Telegram"""
    notify_chat = _db.get_setting("notify_chat_id")
    if not notify_chat: return
    bot = get_tracker_bot() or get_staff_bot()
    if not bot: return
    preview = text[:80] + "..." if len(text) > 80 else text
    msg = f"💬 *Новое сообщение*\n👤 {sender_name}\n\n_{preview}_"
    try:
        await bot.send_message(
            int(notify_chat), msg,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="Открыть чат →",
                    url=f"{_db.get_setting('app_url', '')}/chat?key={_db.get_setting('dashboard_password', '')}&conv_id={conv_id}"
                )
            ]])
        )
    except Exception as e:
        log.warning(f"Notify error: {e}")


async def start_staff_bot(token: str):
    global _staff_bot, _staff_dp, _staff_task
    await stop_staff_bot()
    if not token: return
    try:
        _staff_bot = Bot(token=token)
        _staff_dp  = _build_staff_dp()
        _staff_task = asyncio.create_task(
            _staff_dp.start_polling(
                _staff_bot,
                allowed_updates=["message"],
                drop_pending_updates=True,
                handle_signals=False,
            )
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
    if _staff_dp:
        try: await _staff_dp.stop_polling()
        except: pass
    if _staff_bot:
        try: await _staff_bot.session.close()
        except: pass
    _staff_bot = _staff_dp = _staff_task = None


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
        return {"active": True, "username": info.username,
                "name": info.full_name, "link": f"https://t.me/{info.username}"}
    except:
        return {"active": False, "username": None, "name": None}
