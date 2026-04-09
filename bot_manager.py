"""
bot_manager.py
Бот 1 — Трекер (Клиенты): вступления в каналы → Meta CAPI Subscribe
Бот 2 — Уведомления: авторизация в CRM + уведомления о новых сообщениях
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, Command
from aiogram.filters import CommandStart

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
# БОТ 1 — ТРЕКЕР (Клиенты)
# ══════════════════════════════════════════════════════════════════════════════

def _build_tracker_dp() -> Dispatcher:
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def on_start(message: types.Message):
        """
        /start ref_{click_id} — привязываем tg_user_id к клику и отправляем
        пользователю инвайт-ссылку канала. Это даёт точный matching при вступлении.
        """
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                return
            param = args[1].strip()
            if not param.startswith("ref_"):
                return

            click_id = param[4:]  # убираем "ref_"
            user_id  = str(message.from_user.id)

            # Сохраняем связь tg_user_id → click_id
            _db.bind_click_to_user(click_id, user_id)
            log.info(f"[BOT1] bound click_id={click_id} to user={user_id}")

            # Достаём инвайт-ссылку из клика (target_id) и отправляем пользователю
            click = _db.get_click(click_id)
            invite_link = click.get("target_id") if click else None

            if invite_link and "t.me/" in invite_link:
                # Находим название кампании для кнопки
                campaign = _db.get_campaign_by_invite_link(invite_link)
                btn_label = "Вступить в группу"
                if campaign:
                    btn_label = f"Вступить → {campaign.get('name', 'группу')}"

                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[
                    types.InlineKeyboardButton(text=btn_label, url=invite_link)
                ]])
                await message.answer(
                    "Привет! Нажми кнопку ниже чтобы вступить в группу 👇",
                    reply_markup=keyboard
                )
                log.info(f"[BOT1] sent invite_link to user={user_id} link={invite_link[:50]}")
            else:
                log.warning(f"[BOT1] no invite_link for click_id={click_id}")

        except Exception as e:
            log.warning(f"[BOT1] on_start error: {e}")

    @dp.chat_join_request()
    async def on_join_request(event: types.ChatJoinRequest):
        """
        Join Request флоу: пользователь нажал 'Запрос на вступление' в канале.
        Привязываем его tg_user_id к клику (чтобы on_join нашёл точное совпадение),
        затем одобряем запрос — пользователь попадает в канал без лишних шагов.
        """
        try:
            channel_ids = _db.get_channel_ids()
            cid = str(event.chat.id)
            if cid not in channel_ids:
                # Канал не отслеживается — просто одобряем
                await event.approve()
                return

            user_id_str = str(event.from_user.id)
            raw_link    = event.invite_link.invite_link if event.invite_link else None

            _CLICK_WINDOW = 10080  # 7 дней

            # Ищем клик по invite_link — пользователь только что перешёл по ней
            click_data = {}
            if raw_link:
                click_data = _db.get_latest_click_by_link(raw_link, minutes=_CLICK_WINDOW) or {}

            # Фолбэк: поиск по utm_campaign кампании
            if not click_data:
                campaign = _db.get_campaign_by_link(raw_link)
                if campaign and campaign.get("project_id"):
                    _proj = _db.get_project(int(campaign["project_id"]))
                    if _proj and _proj.get("utm_campaigns"):
                        for _utm in [u.strip() for u in _proj["utm_campaigns"].split(",") if u.strip()]:
                            click_data = _db.get_latest_click_by_utm(_utm, minutes=_CLICK_WINDOW) or {}
                            if click_data:
                                break

            if click_data:
                # Привязываем tg_user_id → on_join найдёт этот клик через Приоритет 0
                _db.bind_click_to_user(click_data["click_id"], user_id_str)
                log.info(f"[BOT1] join_request: bound user={user_id_str} → click={click_data['click_id']} fbclid={'✓' if click_data.get('fbclid') else '—'}")
            else:
                log.info(f"[BOT1] join_request: user={user_id_str} no click found (organic)")

            # Задержка перед одобрением — защита от бана Telegram при высоком трафике.
            # Значение берём из настроек CRM (join_request_delay_sec), по умолчанию 1 сек.
            try:
                _delay = float(_db.get_setting("join_request_delay_sec") or 1)
            except Exception:
                _delay = 1.0
            if _delay > 0:
                await asyncio.sleep(_delay)

            # Одобряем запрос — on_join сработает следующим и отправит Subscribe в FB
            await event.approve()

        except Exception as e:
            log.warning(f"[BOT1] on_join_request error: {e}")
            try:
                await event.approve()
            except Exception:
                pass

    @dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
    async def on_join(event: types.ChatMemberUpdated):
        channel_ids = _db.get_channel_ids()
        cid = str(event.chat.id)
        if cid not in channel_ids:
            return

        user         = event.new_chat_member.user
        raw_link     = event.invite_link.invite_link if event.invite_link else None
        campaign     = _db.get_campaign_by_link(raw_link)
        campaign_name = campaign["name"] if campaign else "organic"

        # ── click_data (fbclid, fbp, utm...) ─────────────────────────────────
        click_id   = None
        click_data = {}
        if campaign:
            user_id_str = str(user.id)

            # Окно поиска click_data: 7 дней (10080 мин).
            # Пользователи часто кликают на рекламу и подписываются на канал
            # спустя часы или дни — окно 120 мин теряло большинство атрибуций.
            _CLICK_WINDOW = 10080  # 7 дней в минутах

            # Приоритет 0: точный поиск по user_id (через /start ref_)
            click_data = _db.get_click_by_user(user_id_str, minutes=_CLICK_WINDOW) or {}

            # Приоритет 1: поиск по invite_link канала
            if not click_data and raw_link:
                click_data = _db.get_latest_click_by_link(raw_link, minutes=_CLICK_WINDOW) or {}

            # Приоритет 2: поиск по utm_campaign из проекта
            if not click_data:
                _utm_vals = []
                if campaign.get("project_id"):
                    _proj = _db.get_project(int(campaign["project_id"]))
                    if _proj and _proj.get("utm_campaigns"):
                        _utm_vals = [u.strip() for u in _proj["utm_campaigns"].split(",") if u.strip()]
                if not _utm_vals:
                    _utm_vals = [campaign.get("name") or campaign_name]
                for _utm in _utm_vals:
                    click_data = _db.get_latest_click_by_utm(_utm, minutes=_CLICK_WINDOW) or {}
                    if click_data:
                        break

            click_id = click_data.get("click_id") if click_data else None
            _src = "user_id" if _db.get_click_by_user(user_id_str, minutes=_CLICK_WINDOW) else ("invite_link" if raw_link and click_data else "utm")
            log.info(f"[BOT1] click lookup src={_src} found={'✓' if click_data else '❌'}")

        join_id = _db.log_join(
            user_id=user.id,
            channel_id=cid,
            invite_link=raw_link,
            campaign_name=campaign_name,
            click_id=click_id
        )
        if click_data:
            _db.save_utm(click_data, join_id=join_id)

        # ── Пиксель: проект кампании → проект лендинга → глобальный ──────────
        pixel_id   = None
        meta_token = None
        _project   = None

        if campaign:
            # Приоритет 1: проект напрямую привязанный к кампании
            if campaign.get("project_id"):
                _project = _db.get_project(int(campaign["project_id"]))
            # Приоритет 2: проект через лендинг кампании
            if not _project and campaign.get("landing_id"):
                _landing = _db.get_landing(int(campaign["landing_id"]))
                if _landing and _landing.get("project_id"):
                    _project = _db.get_project(int(_landing["project_id"]))
            # Приоритет 3: проект по utm_campaign из click_data
            if not _project and click_data and click_data.get("utm_campaign"):
                _project = _db.get_project_by_utm(click_data["utm_campaign"])
            # Приоритет 4: проект по имени кампании (когда нет click_data)
            if not _project:
                _project = _db.get_project_by_utm(campaign_name)

        if _project:
            pixel_id   = _project.get("fb_pixel_id") or ""
            meta_token = _project.get("fb_token") or ""

        if not pixel_id:
            pixel_id   = _db.get_setting("pixel_id") or ""
        if not meta_token:
            meta_token = _db.get_setting("meta_token") or ""

        # ── Matching данные ───────────────────────────────────────────────────
        _fbclid = click_data.get("fbclid") if click_data else None
        _fbp    = click_data.get("fbp")    if click_data else None
        _fbc    = click_data.get("fbc")    if click_data else None

        if _fbclid and not _fbc:
            import time as _time
            _fbc = f"fb.1.{int(_time.time()*1000)}.{_fbclid}"

        _utm_source   = click_data.get("utm_source")  if click_data else None
        _utm_campaign = click_data.get("utm_campaign") if click_data else None
        # IP и User-Agent из момента клика на лендинг (улучшают matching)
        _client_ip    = click_data.get("ip_address")  if click_data else None
        _user_agent   = click_data.get("user_agent")  if click_data else None
        # event_source_url: URL лендинга из которого пришёл пользователь
        _app_url      = _db.get_setting("app_url") or ""
        _camp_slug    = campaign.get("slug") if campaign else None
        _event_source_url = (f"{_app_url}/l/{_camp_slug}" if _camp_slug and _app_url
                             else _app_url or None)

        # test_event_code: из проекта кампании → глобальный
        test_event_code = None
        if _project:
            test_event_code = _project.get("test_event_code") or None
        if not test_event_code:
            test_event_code = _db.get_setting("test_event_code") or None

        log.info(f"[BOT1] test_event_code={test_event_code or '—'} project={_project.get('name') if _project else '—'}")

        # ── Лог с качеством matching ──────────────────────────────────────────
        _ip_ua_score  = sum([bool(_client_ip), bool(_user_agent)])
        _score = sum([bool(_fbclid), bool(_fbp), bool(_fbc)])
        _score_labels = ["❌ нет данных", "⚠️ слабый", "✅ хороший", "✅✅ отличный"]
        _matching = _score_labels[min(_score, 3)]
        _pixel_src = f"проект '{_project['name']}'" if _project else "глобальный"

        log.info(
            f"[BOT1] JOIN user={user.id} channel={cid} campaign={campaign_name} | "
            f"pixel={_pixel_src} | matching={_matching} | "
            f"fbclid={'✓' if _fbclid else '—'} fbp={'✓' if _fbp else '—'} fbc={'✓' if _fbc else '—'} "
            f"ip={'✓' if _client_ip else '—'} ua={'✓' if _user_agent else '—'}"
        )
        if not _score:
            log.warning(
                f"[BOT1] CAPI без matching данных — событие уйдёт но не свяжется с рекламой. "
                f"Причина: пользователь вошёл не через трекинговую ссылку лендинга."
            )

        # ── Отправка Subscribe ────────────────────────────────────────────────
        await _meta.send_subscribe_event(
            pixel_id, meta_token, str(user.id), campaign_name,
            fbclid=_fbclid,
            fbp=_fbp,
            fbc=_fbc,
            utm_source=_utm_source,
            utm_campaign=_utm_campaign,
            client_ip=_client_ip,
            user_agent=_user_agent,
            event_source_url=_event_source_url,
            test_event_code=test_event_code,
        )

    return dp



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
                allowed_updates=["chat_member", "chat_join_request", "message"],
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
# БОТ 2 — УВЕДОМЛЕНИЯ (авторизация + новые сообщения)
# ══════════════════════════════════════════════════════════════════════════════

def _build_staff_dp() -> Dispatcher:
    dp = Dispatcher()
    # Бот только для отправки уведомлений — входящие сообщения игнорируем
    return dp


async def _notify_manager(sender_name: str, conv_id: int, text: str, chat_path: str = "tg_account/chat"):
    """Отправляет уведомление менеджеру в Telegram"""
    notify_chat = _db.get_setting("notify_chat_id")
    if not notify_chat: return
    bot = get_staff_bot() or get_tracker_bot()
    if not bot: return
    preview = text[:80] + "..." if len(text) > 80 else text
    msg = f"💬 *Новое сообщение*\n👤 {sender_name}\n\n_{preview}_"
    app_url = _db.get_setting("app_url", "")
    try:
        await bot.send_message(
            int(notify_chat), msg,
            parse_mode="Markdown",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                types.InlineKeyboardButton(
                    text="Открыть чат →",
                    url=f"{app_url}/{chat_path}?conv_id={conv_id}"
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


async def get_bot_info(bot: Bot | None) -> dict:
    if not bot:
        return {"active": False, "username": None, "name": None}
    try:
        info = await bot.get_me()
        return {"active": True, "username": info.username,
                "name": info.full_name, "link": f"https://t.me/{info.username}"}
    except:
        return {"active": False, "username": None, "name": None}

# ══════════════════════════════════════════════════════════════════════════════
# БОТ 3 — АВТОПОСТИНГ В КАНАЛЫ
# ══════════════════════════════════════════════════════════════════════════════

_autopost_bot = None

async def start_autopost_bot(token: str):
    global _autopost_bot
    await stop_autopost_bot()
    if not token: return
    try:
        _autopost_bot = Bot(token=token)
        info = await _autopost_bot.get_me()
        log.info(f"[BOT3] Started: @{info.username}")
    except Exception as e:
        log.error(f"[BOT3] Start error: {e}")
        _autopost_bot = None


async def stop_autopost_bot():
    global _autopost_bot
    if _autopost_bot:
        try: await _autopost_bot.session.close()
        except: pass
    _autopost_bot = None


def get_autopost_bot():
    return _autopost_bot
