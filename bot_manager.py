"""
bot_manager.py — управление aiogram ботами TG Tracker v6
Поддержка: текст, фото, видео, голос (скачивание → Cloudinary → DB)
"""
import asyncio
import logging
import os
import httpx

log = logging.getLogger(__name__)

# ─── Debug log (circular buffer последних 100 событий) ───────────────────────
import collections as _col, datetime as _dt

_debug_log = _col.deque(maxlen=100)

def _dbg(level: str, msg: str):
    """Добавляет запись в debug-буфер и стандартный лог."""
    entry = {"ts": _dt.datetime.utcnow().strftime("%H:%M:%S"), "level": level, "msg": msg}
    _debug_log.append(entry)
    if level == "ERROR":
        log.error(msg)
    elif level == "WARN":
        log.warning(msg)
    else:
        log.info(msg)

def get_debug_log():
    """Возвращает копию debug-буфера (для /api/debug)."""
    return list(_debug_log)

# ─── Глобальные переменные ────────────────────────────────────────────────────
_db         = None
_meta_capi  = None
_tracker_dp = None
_tracker_bot = None
_staff_dp   = None
_staff_bot  = None
_tracker_task = None
_staff_task   = None


import hashlib as _hl, time as _time

class _CU:
    def __init__(self):
        self.cloud = os.getenv("CLOUDINARY_CLOUD_NAME","")
        self.key   = os.getenv("CLOUDINARY_API_KEY","")
        self.sec   = os.getenv("CLOUDINARY_API_SECRET","")
    def _sign(self, params):
        s = "&".join(f"{k}={v}" for k,v in sorted(params.items()))
        return _hl.sha1((s + self.sec).encode()).hexdigest()
    async def upload_bytes(self, data: bytes, resource_type="image", folder="tg_chat"):
        if not all([self.cloud, self.key, self.sec]): return None
        try:
            ts = int(_time.time())
            params = {"folder": folder, "timestamp": ts}
            sig = self._sign(params)
            url = f"https://api.cloudinary.com/v1_1/{self.cloud}/{resource_type}/upload"
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(url, data={"api_key":self.key,"timestamp":ts,"folder":folder,"signature":sig},
                                 files={"file":("media", data)})
            return r.json().get("secure_url") if r.status_code==200 else None
        except Exception as e:
            log.warning(f"Cloudinary upload error: {e}"); return None
    async def upload_from_url(self, src_url: str, resource_type="image", folder="tg_chat"):
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.get(src_url)
            return await self.upload_bytes(r.content, resource_type, folder) if r.status_code==200 else None
        except Exception as e:
            log.warning(f"upload_from_url error: {e}"); return None

_cu = _CU()

def init(db, meta_capi):
    global _db, _meta_capi
    _db = db
    _meta_capi = meta_capi
    _dbg("INFO", f"[INIT] bot_manager.init() called, db={'OK' if db else 'NONE'}")


def get_tracker_bot():
    return _tracker_bot


def get_staff_bot():
    return _staff_bot


# ─── Загрузка файла из TG + Cloudinary ───────────────────────────────────────

async def _tg_download_to_cloudinary(bot, file_id: str, resource_type: str) -> str | None:
    """Скачивает файл из Telegram и загружает в Cloudinary."""
    try:
        if not (_cu and _cu.cloud):
            log.warning("Cloudinary not configured — check env vars")
            return None
        file = await bot.get_file(file_id)
        # aiogram v3: скачиваем байты через bot.download()
        import io
        buf = io.BytesIO()
        await bot.download(file, destination=buf)
        buf.seek(0)
        data = buf.read()
        if not data:
            log.warning("Empty file downloaded from TG")
            return None
        return await _cu.upload_bytes(data, resource_type=resource_type, folder="tg_chat")
    except Exception as e:
        log.warning(f"_tg_download_to_cloudinary error: {e}")
        return None


# ─── Регистрация хэндлеров ────────────────────────────────────────────────────

def _register_tracker_handlers(dp, bot):
    """Бот-трекер: обрабатывает сообщения от посетителей (tracker bot)."""
    from aiogram import types
    from aiogram.filters import CommandStart

    @dp.message(CommandStart())
    async def cmd_start(msg: types.Message):
        """Отвечает на /start, создаёт конверсацию."""
        try:
            tg_id = str(msg.from_user.id)
            name  = (msg.from_user.full_name or tg_id)[:100]
            uname = msg.from_user.username
            conv  = _db.get_or_create_conversation(tg_id, name, uname)
            pixel = _db.get_setting("pixel_id")
            token = _db.get_setting("meta_token")
            if pixel and token:
                await _meta_capi.send_lead_event(pixel, token, user_id=tg_id)
            await msg.answer("Привет! Оставьте ваш вопрос — мы ответим в ближайшее время 👋")
        except Exception as e:
            log.error(f"tracker /start error: {e}")

    @dp.message()
    async def on_message(msg: types.Message):
        try:
            tg_id = str(msg.from_user.id)
            name  = (msg.from_user.full_name or tg_id)[:100]
            uname = msg.from_user.username
            _dbg("INFO", f"[TRACKER] msg from {tg_id} (@{uname}): text={repr((msg.text or '')[:60])}")

            if _db is None:
                _dbg("ERROR", f"[TRACKER] _db is None! init() was not called")
                return

            conv  = _db.get_or_create_conversation(tg_id, name, uname)
            _dbg("INFO", f"[TRACKER] conv_id={conv.get('id')} for tg_id={tg_id}")

            text       = msg.text or msg.caption or ""
            media_url  = None
            media_type = None

            # Фото
            if msg.photo:
                best = msg.photo[-1]
                media_url = await _tg_download_to_cloudinary(bot, best.file_id, "image")
                media_type = "photo"
                text = text or "📷 Фото"
                _dbg("INFO", f"[TRACKER] photo → cloudinary={media_url}")
            # Видео
            elif msg.video:
                media_url = await _tg_download_to_cloudinary(bot, msg.video.file_id, "video")
                media_type = "video"
                text = text or "🎬 Видео"
            # Голосовое
            elif msg.voice:
                media_url = await _tg_download_to_cloudinary(bot, msg.voice.file_id, "video")
                media_type = "voice"
                text = text or "🎤 Голосовое"
            # Документ
            elif msg.document:
                ext = (msg.document.file_name or "").split(".")[-1].lower()
                rt  = "image" if ext in ("jpg","jpeg","png","gif","webp") else \
                      "video" if ext in ("mp4","mov","avi","mkv") else "raw"
                media_url = await _tg_download_to_cloudinary(bot, msg.document.file_id, rt)
                media_type = "document"
                text = text or f"📎 {msg.document.file_name or 'Файл'}"
            # Стикер
            elif msg.sticker:
                text = f"🎭 Стикер: {msg.sticker.emoji or ''}"

            _db.save_message(conv["id"], tg_id, "visitor", text,
                             media_url=media_url, media_type=media_type)
            _db.update_conversation_last_message(tg_id, text, increment_unread=True)
            _dbg("INFO", f"[TRACKER] saved msg to conv_id={conv.get('id')}, text={repr(text[:40])}")
        except Exception as e:
            _dbg("ERROR", f"[TRACKER] on_message EXCEPTION: {e}")


def _register_staff_handlers(dp, bot):
    """Бот для сотрудников: обрабатывает ответы сотрудников."""
    from aiogram import types
    from aiogram.filters import CommandStart

    @dp.message(CommandStart())
    async def cmd_start(msg: types.Message):
        try:
            tg_id = str(msg.from_user.id)
            name  = (msg.from_user.full_name or tg_id)[:100]
            uname = msg.from_user.username
            _db.get_or_create_staff(tg_id, name, uname, conv_id=0)
            pixel = _db.get_setting("pixel_id")
            token = _db.get_setting("meta_token")
            if pixel and token:
                await _meta_capi.send_lead_event(pixel, token, user_id=tg_id, campaign="staff")
            await msg.answer("Привет! Ваша анкета создана. Мы свяжемся с вами 👔")
        except Exception as e:
            log.error(f"staff /start error: {e}")

    @dp.message()
    async def on_message(msg: types.Message):
        try:
            tg_id = str(msg.from_user.id)
            name  = (msg.from_user.full_name or tg_id)[:100]
            uname = msg.from_user.username
            conv  = _db.get_or_create_staff_conv(tg_id, name, uname)
            if not conv:
                return

            text       = msg.text or msg.caption or ""
            media_url  = None
            media_type = None

            if msg.photo:
                best = msg.photo[-1]
                media_url = await _tg_download_to_cloudinary(bot, best.file_id, "image")
                media_type = "photo"
                text = text or "📷 Фото"
            elif msg.video:
                media_url = await _tg_download_to_cloudinary(bot, msg.video.file_id, "video")
                media_type = "video"
                text = text or "🎬 Видео"
            elif msg.voice:
                media_url = await _tg_download_to_cloudinary(bot, msg.voice.file_id, "video")
                media_type = "voice"
                text = text or "🎤 Голосовое"
            elif msg.document:
                ext = (msg.document.file_name or "").split(".")[-1].lower()
                rt  = "image" if ext in ("jpg","jpeg","png","gif","webp") else \
                      "video" if ext in ("mp4","mov","avi","mkv") else "raw"
                media_url = await _tg_download_to_cloudinary(bot, msg.document.file_id, rt)
                media_type = "document"
                text = text or f"📎 {msg.document.file_name or 'Файл'}"

            _db.save_message(conv["id"], tg_id, "visitor", text,
                             media_url=media_url, media_type=media_type)
            _db.update_conversation_last_message(tg_id, text, increment_unread=True)

            # Уведомление менеджера
            notify_chat = _db.get_setting("notify_chat_id")
            if notify_chat and _tracker_bot:
                try:
                    await _tracker_bot.send_message(
                        int(notify_chat),
                        f"👔 *Staff бот — новое сообщение*\n👤 {name}\n\n_{text[:80]}_",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception as e:
            log.error(f"staff on_message error: {e}")


# ─── Запуск / остановка ───────────────────────────────────────────────────────

async def _run_bot(dp, bot):
    try:
        log.info(f"Bot polling started for {bot}")
        await dp.start_polling(bot, handle_signals=False)
        log.info("Bot polling stopped normally")
    except asyncio.CancelledError:
        log.info("Bot polling cancelled")
    except Exception as e:
        log.error(f"Bot polling CRASHED: {e}", exc_info=True)


async def start_tracker_bot(token: str | None):
    global _tracker_bot, _tracker_dp, _tracker_task
    if not token:
        log.warning("Tracker bot: token not set — skipping")
        return
    try:
        from aiogram import Bot, Dispatcher
        await stop_tracker_bot()
        _tracker_bot = Bot(token=token)
        # Снимаем webhook если был установлен — иначе polling не работает
        wh = await _tracker_bot.get_webhook_info()
        if wh.url:
            _dbg("WARN", f"[TRACKER] removing webhook {wh.url}")
            await _tracker_bot.delete_webhook(drop_pending_updates=True)
        _tracker_dp  = Dispatcher()
        _register_tracker_handlers(_tracker_dp, _tracker_bot)
        info = await _tracker_bot.get_me()
        _dbg("INFO", f"[TRACKER] bot @{info.username} (id={info.id}) starting polling...")
        if not _db.get_setting("bot1_name"):
            _db.set_setting("bot1_name", f"@{info.username}")
        _tracker_task = asyncio.create_task(_run_bot(_tracker_dp, _tracker_bot))
        _dbg("INFO", f"[TRACKER] polling task created ✅")
    except Exception as e:
        _dbg("ERROR", f"[TRACKER] start_tracker_bot FAILED: {e}")
        _tracker_bot = None


async def stop_tracker_bot():
    global _tracker_bot, _tracker_dp, _tracker_task
    if _tracker_task:
        _tracker_task.cancel()
        try: await _tracker_task
        except Exception: pass
        _tracker_task = None
    if _tracker_dp:
        await _tracker_dp.storage.close()
        _tracker_dp = None
    if _tracker_bot:
        await _tracker_bot.session.close()
        _tracker_bot = None


async def start_staff_bot(token: str | None):
    global _staff_bot, _staff_dp, _staff_task
    if not token:
        log.warning("Staff bot: token not set — skipping")
        return
    try:
        from aiogram import Bot, Dispatcher
        await stop_staff_bot()
        _staff_bot = Bot(token=token)
        wh = await _staff_bot.get_webhook_info()
        if wh.url:
            log.info(f"Staff bot: removing webhook {wh.url}")
            await _staff_bot.delete_webhook(drop_pending_updates=True)
        _staff_dp  = Dispatcher()
        _register_staff_handlers(_staff_dp, _staff_bot)
        info = await _staff_bot.get_me()
        log.info(f"Staff bot @{info.username} (id={info.id}) starting polling...")
        if not _db.get_setting("bot2_name"):
            _db.set_setting("bot2_name", f"@{info.username}")
        _staff_task = asyncio.create_task(_run_bot(_staff_dp, _staff_bot))
        log.info(f"Staff bot @{info.username} polling task created ✅")
    except Exception as e:
        log.error(f"start_staff_bot FAILED: {e}", exc_info=True)
        _staff_bot = None


async def stop_staff_bot():
    global _staff_bot, _staff_dp, _staff_task
    if _staff_task:
        _staff_task.cancel()
        try: await _staff_task
        except Exception: pass
        _staff_task = None
    if _staff_dp:
        await _staff_dp.storage.close()
        _staff_dp = None
    if _staff_bot:
        await _staff_bot.session.close()
        _staff_bot = None


# ─── Отправка сообщений из дашборда ──────────────────────────────────────────

async def send_staff_message(tg_chat_id: str, text: str) -> bool:
    """Отправляет текстовое сообщение сотруднику через staff-бот."""
    if not _staff_bot:
        return False
    try:
        await _staff_bot.send_message(int(tg_chat_id), text)
        return True
    except Exception as e:
        log.error(f"send_staff_message error: {e}")
        return False


async def send_staff_photo(tg_chat_id: str, photo_url: str, caption: str = "") -> bool:
    """Отправляет фото сотруднику через staff-бот (по URL из Cloudinary)."""
    if not _staff_bot:
        return False
    try:
        await _staff_bot.send_photo(int(tg_chat_id), photo=photo_url, caption=caption)
        return True
    except Exception as e:
        log.error(f"send_staff_photo error: {e}")
        return False


async def send_tracker_message(tg_chat_id: str, text: str) -> bool:
    """Отправляет текстовое сообщение через tracker-бот."""
    if not _tracker_bot:
        return False
    try:
        await _tracker_bot.send_message(int(tg_chat_id), text)
        return True
    except Exception as e:
        log.error(f"send_tracker_message error: {e}")
        return False


async def get_bot_info(bot) -> dict | None:
    if not bot:
        return None
    try:
        me = await bot.get_me()
        return {"id": me.id, "username": me.username, "first_name": me.first_name}
    except Exception:
        return None
