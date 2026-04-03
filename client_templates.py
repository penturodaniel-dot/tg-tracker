"""
client_templates.py — HTML шаблоны клиентских лендингов

Содержит:
  _render_client_landing()   — диспетчер шаблонов (заменяет версию из landing_templates.py)
  _tpl_relaxation()          — основной шаблон "Relaxation & Balance"
"""

import json as _json


# ── helpers ──────────────────────────────────────────────────────────────────

def _t(texts: dict, key: str, default: str = "") -> str:
    val = texts.get(key, "")
    return val if val else default


def _pixel_js(pixel_id: str) -> str:
    if not pixel_id:
        return ""
    return f"""<!-- Facebook Pixel -->
<script>
!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window,document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init','{pixel_id}');
fbq('track','PageView');
document.addEventListener('click',function(e){{
  var btn=e.target.closest('.call-button');
  if(btn){{fbq('track','Contact');}}
}});
</script>
<noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id={pixel_id}&ev=PageView&noscript=1"/></noscript>"""


def _tiktok_pixel_js(pixel_id: str) -> str:
    if not pixel_id:
        return ""
    return f"""<!-- TikTok Pixel -->
<script>
!function(w,d,t){{w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie","holdConsent","revokeConsent","grantConsent"],ttq.setAndDefer=function(t,e){{t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){{for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e}},ttq.load=function(e,n){{var r="https://analytics.tiktok.com/i18n/pixel/events.js",o=n&&n.partner;ttq._i=ttq._i||{{}},ttq._i[e]=[],ttq._i[e]._u=r,ttq._t=ttq._t||{{}},ttq._t[e]=+new Date,ttq._o=ttq._o||{{}},ttq._o[e]=n||{{}};n=document.createElement("script");n.type="text/javascript",n.async=!0,n.src=r+"?sdkid="+e+"&lib="+t;e=document.getElementsByTagName("script")[0];e.parentNode.insertBefore(n,e)}};ttq.load('{pixel_id}');ttq.page();}}(window,document,'ttq');
</script>"""


# ── dispatcher ───────────────────────────────────────────────────────────────

def _render_client_landing(landing: dict, contacts: list, pixel_id: str = "", tt_pixel: str = "", db=None) -> str:
    """Диспетчер клиентских шаблонов. Сейчас: только relaxation."""
    try:
        lcontent = _json.loads(landing.get("content", "{}"))
        template = lcontent.get("template", "relaxation")
        texts    = lcontent.get("texts", {})
    except Exception:
        template = "relaxation"
        texts    = {}

    tt_pixel_id = tt_pixel or (db.get_setting("tiktok_pixel_id", "") if db else "") or (db.get_setting("tt_pixel_id", "") if db else "")
    px = _pixel_js(pixel_id) + _tiktok_pixel_js(tt_pixel_id)

    # Телефоны — хранятся как JSON-список в texts["phones"]
    try:
        phones = _json.loads(texts.get("phones", "[]")) if isinstance(texts.get("phones"), str) else (texts.get("phones") or [])
    except Exception:
        phones = []

    # Медиа (фото и видео) из texts
    try:
        photos = _json.loads(texts.get("photos", "[]")) if isinstance(texts.get("photos"), str) else (texts.get("photos") or [])
    except Exception:
        photos = []
    try:
        videos = _json.loads(texts.get("videos", "[]")) if isinstance(texts.get("videos"), str) else (texts.get("videos") or [])
    except Exception:
        videos = []

    # Единственный шаблон сейчас
    return _tpl_relaxation(texts, contacts, px, phones, photos, videos)


# ── template: Relaxation & Balance ───────────────────────────────────────────

def _tpl_relaxation(texts: dict, contacts: list, pixel_js: str, phones: list, photos: list, videos: list) -> str:

    # ── texts (всё редактируемое) ─────────────────────────────────────────────
    top_bar     = _t(texts, "top_bar",     "⚠️ No Fake Service 💯")
    hero_title  = _t(texts, "hero_title",  "Relaxation and Balance 🌿✨")
    hero_sub    = _t(texts, "hero_sub",    "I invite you to enjoy a soothing body massage in a comfortable, private setting.")
    btn_contact = _t(texts, "btn_contact", "Contact me")

    sec_included = _t(texts, "sec_included", "Included in the session:")
    utp_1 = _t(texts, "utp_1", "💆‍♂️ Full body massage")
    utp_2 = _t(texts, "utp_2", "🤍 Full body contact massage")
    utp_3 = _t(texts, "utp_3", "🔥 Relaxation completion")

    desc_box = _t(texts, "desc_box",
        "✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed.")

    sec_rates = _t(texts, "sec_rates", "💰 Rates:")
    rate_1_dur  = _t(texts, "rate_1_dur",  "60 min"); rate_1_price = _t(texts, "rate_1_price", "$230")
    rate_2_dur  = _t(texts, "rate_2_dur",  "30 min"); rate_2_price = _t(texts, "rate_2_price", "$200")
    rate_3_dur  = _t(texts, "rate_3_dur",  "15 min"); rate_3_price = _t(texts, "rate_3_price", "$140")

    sec_info = _t(texts, "sec_info", "📋 Important Information:")
    info_1 = _t(texts, "info_1", "📌 Extra services can only be discussed in person during the session.")
    info_2 = _t(texts, "info_2", "💵 Payment is accepted in cash only. Please prepare the exact amount.")
    info_3 = _t(texts, "info_3", "⚠️ Same-day appointments only. Advance bookings are not available.")

    book_msg    = _t(texts, "book_msg",    "💌 Message me to book your session!")
    sec_contact = _t(texts, "sec_contact", "Contact me:")
    btn_tg_label= _t(texts, "btn_tg",     "Contact on Telegram")
    btn_call    = _t(texts, "btn_call",    "📞 Call me or text me")
    media_title = _t(texts, "media_title", "📸 Photos and Videos")

    # ── Telegram-кнопки ──────────────────────────────────────────────────────
    TG_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>'
    WA_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5Z"/></svg>'

    tg_btns_html = ""
    for c in contacts:
        if c.get("type") == "telegram":
            tg_btns_html += f'<a class="rl-btn rl-btn-tg call-button" href="{c["url"]}" target="_blank" rel="noopener">{TG_SVG}<span>{c["label"]}</span></a>'
        elif c.get("type") == "whatsapp":
            tg_btns_html += f'<a class="rl-btn rl-btn-wa call-button" href="{c["url"]}" target="_blank" rel="noopener">{WA_SVG}<span>{c["label"]}</span></a>'
    if not tg_btns_html:
        tg_btns_html = '<p style="color:rgba(255,255,255,.4);font-size:.85rem;text-align:center">Контакты не настроены</p>'

    # ── Телефоны ─────────────────────────────────────────────────────────────
    phones_html = ""
    if phones:
        phones_html = "".join(
            f'<div class="rl-phone-item">'
            f'<span class="rl-phone-city">{p.get("city","")}</span>'
            f'<a href="tel:{p.get("phone","").replace(" ","")}" class="rl-phone-num">{p.get("phone","")}</a>'
            f'</div>'
            for p in phones if p.get("phone")
        )

    # ── Медиа галерея ────────────────────────────────────────────────────────
    # Фото-миниатюры для попапа
    photos_thumbs = "".join(
        f'<div class="rl-gallery-item" onclick="openMedia(\'photo\',{i})">'
        f'<img src="{url}" loading="lazy" alt="photo"/></div>'
        for i, url in enumerate(photos)
    ) if photos else '<p class="rl-gallery-empty">Фото не добавлены</p>'

    # Видео-миниатюры
    videos_thumbs = "".join(
        f'<div class="rl-gallery-item rl-gallery-video" onclick="openMedia(\'video\',{i})">'
        f'<video src="{url}" muted preload="none"></video>'
        f'<div class="rl-play-icon">▶</div></div>'
        for i, url in enumerate(videos)
    ) if videos else '<p class="rl-gallery-empty">Видео не добавлены</p>'

    # JSON для JS
    import json as _j
    photos_json = _j.dumps(photos)
    videos_json = _j.dumps(videos)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{hero_title}</title>
{pixel_js}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ── RESET & BASE ─────────────────────────────────────────── */
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth}}
body{{
  font-family:'Inter',system-ui,sans-serif;
  background:#07090e;
  color:#e4ecf5;
  min-height:100vh;
  font-size:15px;
  -webkit-font-smoothing:antialiased;
  line-height:1.6;
}}
a{{text-decoration:none;color:inherit}}

/* ── WRAP ────────────────────────────────────────────────── */
.wrap{{max-width:560px;margin:0 auto;padding:0 20px}}

/* ── TOP BAR ─────────────────────────────────────────────── */
.rl-topbar{{
  background:linear-gradient(90deg,#0d1117,#1a0a2e,#0d1117);
  border-bottom:1px solid rgba(255,255,255,.07);
  padding:10px 20px;
  text-align:center;
  font-size:.78rem;
  font-weight:700;
  color:#f8d56b;
  letter-spacing:.06em;
  text-transform:uppercase;
}}

/* ── HERO ────────────────────────────────────────────────── */
.rl-hero{{
  position:relative;
  min-height:55vh;
  display:flex;
  align-items:center;
  justify-content:center;
  text-align:center;
  overflow:hidden;
}}
.rl-hero::before{{
  content:"";
  position:absolute;inset:0;
  background:url('https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop') center/cover no-repeat;
  filter:brightness(.28);
}}
.rl-hero::after{{
  content:"";
  position:absolute;inset:0;
  background:linear-gradient(to bottom,rgba(7,9,14,.1) 0%,rgba(7,9,14,1) 100%);
}}
.rl-hero-inner{{
  position:relative;z-index:1;
  padding:60px 20px 48px;
}}
.rl-hero h1{{
  font-size:clamp(1.9rem,5vw,2.8rem);
  font-weight:800;
  line-height:1.15;
  margin-bottom:14px;
  background:linear-gradient(135deg,#fff 40%,rgba(255,255,255,.7));
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}}
.rl-hero p{{
  color:rgba(255,255,255,.65);
  max-width:440px;
  margin:0 auto 28px;
  font-size:.95rem;
  font-weight:400;
}}

/* ── SCROLL-TO BTN ───────────────────────────────────────── */
.rl-cta-btn{{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:13px 30px;
  border-radius:50px;
  background:linear-gradient(135deg,#6b21a8,#4f46e5);
  color:#fff;
  font-weight:700;
  font-size:.95rem;
  cursor:pointer;
  border:none;
  transition:opacity .15s,transform .15s;
  box-shadow:0 4px 20px rgba(107,33,168,.4);
}}
.rl-cta-btn:hover{{opacity:.9;transform:translateY(-1px)}}
.rl-cta-btn svg{{flex-shrink:0}}

/* ── SECTIONS ────────────────────────────────────────────── */
.rl-sec{{padding:36px 0 12px}}
.rl-sec-title{{
  font-size:1rem;
  font-weight:700;
  color:#c4b5fd;
  margin-bottom:14px;
  text-transform:uppercase;
  letter-spacing:.05em;
}}

/* ── UTP LIST ────────────────────────────────────────────── */
.rl-utp{{display:flex;flex-direction:column;gap:8px;margin-bottom:24px}}
.rl-utp-item{{
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  border-radius:14px;
  padding:14px 18px;
  font-size:.92rem;
  font-weight:500;
  display:flex;
  align-items:center;
  gap:10px;
}}

/* ── DESC BOX ────────────────────────────────────────────── */
.rl-desc{{
  background:rgba(79,70,229,.08);
  border:1px solid rgba(79,70,229,.25);
  border-radius:14px;
  padding:16px 20px;
  font-size:.88rem;
  line-height:1.75;
  color:rgba(255,255,255,.8);
  margin-bottom:28px;
}}

/* ── MEDIA BLOCK ─────────────────────────────────────────── */
.rl-media{{
  display:flex;
  gap:12px;
  margin-bottom:28px;
}}
.rl-media-btn{{
  flex:1;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:8px;
  padding:13px;
  border-radius:14px;
  font-weight:700;
  font-size:.88rem;
  cursor:pointer;
  border:none;
  transition:all .15s;
}}
.rl-media-btn.photos{{
  background:rgba(168,85,247,.12);
  border:1px solid rgba(168,85,247,.3);
  color:#d8b4fe;
}}
.rl-media-btn.photos:hover{{background:rgba(168,85,247,.2)}}
.rl-media-btn.videos{{
  background:rgba(99,102,241,.12);
  border:1px solid rgba(99,102,241,.3);
  color:#a5b4fc;
}}
.rl-media-btn.videos:hover{{background:rgba(99,102,241,.2)}}

/* ── RATES ───────────────────────────────────────────────── */
.rl-rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:24px}}
.rl-rate{{
  display:flex;
  justify-content:space-between;
  align-items:center;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  border-radius:14px;
  padding:15px 22px;
  font-weight:600;
  font-size:.95rem;
}}
.rl-rate-price{{
  font-size:1.1rem;
  font-weight:800;
  background:linear-gradient(135deg,#a5f3fc,#67e8f9);
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}}

/* ── INFO BOX ────────────────────────────────────────────── */
.rl-info{{
  background:rgba(248,212,0,.05);
  border:1px solid rgba(248,212,0,.18);
  border-radius:14px;
  padding:18px 20px;
  margin-bottom:28px;
  display:flex;
  flex-direction:column;
  gap:10px;
}}
.rl-info-item{{
  font-size:.87rem;
  line-height:1.7;
  color:rgba(255,255,255,.78);
}}

/* ── BOOK MESSAGE ────────────────────────────────────────── */
.rl-book{{
  text-align:center;
  font-size:.95rem;
  color:rgba(255,255,255,.5);
  padding:20px 0 28px;
  border-top:1px solid rgba(255,255,255,.06);
}}

/* ── CONTACT SECTION ─────────────────────────────────────── */
.rl-contact{{
  text-align:center;
  padding:8px 0 60px;
  scroll-margin-top:20px;
}}
.rl-contact-title{{
  font-size:1.3rem;
  font-weight:800;
  margin-bottom:24px;
  background:linear-gradient(135deg,#fff,rgba(255,255,255,.7));
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}}

/* ── CONTACT BUTTONS ─────────────────────────────────────── */
.rl-btns{{display:flex;flex-direction:column;gap:10px;margin-bottom:16px}}
.rl-btn{{
  display:flex;
  align-items:center;
  justify-content:center;
  gap:10px;
  width:100%;
  padding:15px;
  border-radius:14px;
  font-weight:700;
  font-size:.95rem;
  text-decoration:none;
  transition:opacity .15s,transform .15s;
  border:none;
  cursor:pointer;
}}
.rl-btn:hover{{opacity:.88;transform:translateY(-1px)}}
.rl-btn-tg{{background:#26A5E4;color:#fff}}
.rl-btn-wa{{background:#25D366;color:#fff}}

/* ── CALL ME BUTTON ──────────────────────────────────────── */
.rl-call-toggle{{
  width:100%;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:10px;
  padding:14px;
  border-radius:14px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);
  color:#e4ecf5;
  font-weight:700;
  font-size:.95rem;
  cursor:pointer;
  transition:background .15s;
  margin-top:4px;
}}
.rl-call-toggle:hover{{background:rgba(255,255,255,.12)}}
.rl-call-toggle.open{{
  background:rgba(107,33,168,.15);
  border-color:rgba(107,33,168,.35);
  color:#d8b4fe;
}}

/* ── PHONES LIST ─────────────────────────────────────────── */
.rl-phones{{
  display:none;
  flex-direction:column;
  gap:0;
  margin-top:10px;
  background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.08);
  border-radius:14px;
  overflow:hidden;
}}
.rl-phones.open{{display:flex}}
.rl-phone-item{{
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:12px 18px;
  border-bottom:1px solid rgba(255,255,255,.06);
  gap:12px;
}}
.rl-phone-item:last-child{{border-bottom:none}}
.rl-phone-city{{
  font-size:.82rem;
  color:rgba(255,255,255,.5);
  font-weight:500;
  min-width:80px;
}}
.rl-phone-num{{
  font-size:.9rem;
  font-weight:700;
  color:#a5f3fc;
  letter-spacing:.03em;
}}
.rl-phone-num:hover{{color:#67e8f9}}

/* ── MEDIA POPUP ─────────────────────────────────────────── */
.rl-popup{{
  display:none;
  position:fixed;inset:0;
  background:rgba(0,0,0,.92);
  z-index:9000;
  flex-direction:column;
  align-items:center;
  justify-content:flex-start;
  padding:0;
  overscroll-behavior:contain;
}}
.rl-popup.open{{display:flex}}
.rl-popup-header{{
  width:100%;
  max-width:600px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  padding:16px 20px 12px;
  flex-shrink:0;
}}
.rl-popup-title{{font-weight:700;font-size:1rem;color:#fff}}
.rl-popup-close{{
  background:rgba(255,255,255,.1);
  border:none;
  color:#fff;
  width:36px;height:36px;
  border-radius:50%;
  font-size:1.1rem;
  cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  transition:background .15s;
}}
.rl-popup-close:hover{{background:rgba(255,255,255,.2)}}
.rl-popup-gallery{{
  width:100%;
  max-width:600px;
  flex:1;
  overflow-y:auto;
  padding:0 16px 24px;
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  align-content:start;
}}
.rl-gallery-item{{
  aspect-ratio:3/4;
  border-radius:12px;
  overflow:hidden;
  background:rgba(255,255,255,.05);
  cursor:pointer;
  position:relative;
  border:2px solid transparent;
  transition:border-color .15s;
}}
.rl-gallery-item:hover{{border-color:rgba(168,85,247,.5)}}
.rl-gallery-item img,
.rl-gallery-item video{{
  width:100%;height:100%;object-fit:cover;display:block;
}}
.rl-gallery-video{{position:relative}}
.rl-play-icon{{
  position:absolute;inset:0;
  display:flex;align-items:center;justify-content:center;
  font-size:2.5rem;
  color:rgba(255,255,255,.85);
  text-shadow:0 2px 12px rgba(0,0,0,.8);
  pointer-events:none;
}}
.rl-gallery-empty{{
  grid-column:1/-1;
  text-align:center;
  color:rgba(255,255,255,.35);
  padding:32px;
  font-size:.85rem;
}}

/* ── LIGHTBOX ────────────────────────────────────────────── */
.rl-lightbox{{
  display:none;
  position:fixed;inset:0;
  background:rgba(0,0,0,.97);
  z-index:9999;
  align-items:center;
  justify-content:center;
  flex-direction:column;
  gap:16px;
}}
.rl-lightbox.open{{display:flex}}
.rl-lightbox img,
.rl-lightbox video{{
  max-width:min(500px,90vw);
  max-height:min(500px,80vh);
  object-fit:contain;
  border-radius:12px;
  box-shadow:0 16px 64px rgba(0,0,0,.8);
}}
.rl-lightbox-close{{
  position:absolute;top:20px;right:20px;
  background:rgba(255,255,255,.12);
  border:none;color:#fff;
  width:42px;height:42px;border-radius:50%;
  font-size:1.3rem;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
}}
.rl-lightbox-nav{{
  display:flex;gap:16px;
}}
.rl-lightbox-nav button{{
  background:rgba(255,255,255,.1);
  border:1px solid rgba(255,255,255,.15);
  color:#fff;padding:8px 22px;
  border-radius:8px;font-size:.9rem;cursor:pointer;
  transition:background .15s;
}}
.rl-lightbox-nav button:hover{{background:rgba(255,255,255,.2)}}

/* ── SCROLL-TO-TOP ───────────────────────────────────────── */
.rl-scroll-top{{
  position:fixed;
  bottom:24px;right:20px;
  width:44px;height:44px;
  border-radius:50%;
  background:linear-gradient(135deg,#6b21a8,#4f46e5);
  color:#fff;
  border:none;
  font-size:1.2rem;
  cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 16px rgba(107,33,168,.5);
  opacity:0;
  pointer-events:none;
  transition:opacity .3s,transform .3s;
  z-index:8000;
  transform:translateY(12px);
}}
.rl-scroll-top.visible{{
  opacity:1;pointer-events:auto;transform:translateY(0);
}}
.rl-scroll-top:hover{{transform:scale(1.08)}}

/* ── DIVIDER ─────────────────────────────────────────────── */
.rl-divider{{
  border:none;
  border-top:1px solid rgba(255,255,255,.06);
  margin:8px 0 24px;
}}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="rl-topbar">{top_bar}</div>

<!-- HERO -->
<div class="rl-hero">
  <div class="rl-hero-inner">
    <h1>{hero_title}</h1>
    <p>{hero_sub}</p>
    <button class="rl-cta-btn" onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}})">
      <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path d="M2 10a8 8 0 1 1 16 0A8 8 0 0 1 2 10Zm8-3a1 1 0 0 0-1 1v2H7a1 1 0 1 0 0 2h2v2a1 1 0 1 0 2 0v-2h2a1 1 0 1 0 0-2h-2V8a1 1 0 0 0-1-1Z" clip-rule="evenodd" fill-rule="evenodd"/></svg>
      {btn_contact}
    </button>
  </div>
</div>

<div class="wrap">

  <!-- INCLUDED IN SESSION -->
  <div class="rl-sec">
    <div class="rl-sec-title">{sec_included}</div>
    <div class="rl-utp">
      <div class="rl-utp-item">{utp_1}</div>
      <div class="rl-utp-item">{utp_2}</div>
      <div class="rl-utp-item">{utp_3}</div>
    </div>
  </div>

  <!-- DESCRIPTION -->
  <div class="rl-desc">{desc_box}</div>

  <!-- PHOTOS & VIDEOS -->
  <div class="rl-sec" style="padding-bottom:0">
    <div class="rl-sec-title">{media_title}</div>
  </div>
  <div class="rl-media">
    <button class="rl-media-btn photos" onclick="openPopup('photos')">
      <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M4 5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H4Zm0 2h16v6.586l-2.293-2.293a1 1 0 0 0-1.414 0L13 14.586l-2.293-2.293a1 1 0 0 0-1.414 0L4 17.586V7Z"/></svg>
      Photos
    </button>
    <button class="rl-media-btn videos" onclick="openPopup('videos')">
      <svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M4 6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2.5l4 2V8l-4 2V8a2 2 0 0 0-2-2H4Z"/></svg>
      Videos
    </button>
  </div>

  <!-- CTA #2 -->
  <button class="rl-cta-btn" style="width:100%;justify-content:center;margin-bottom:28px"
    onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}})">
    {btn_contact}
  </button>

  <hr class="rl-divider">

  <!-- RATES -->
  <div class="rl-sec">
    <div class="rl-sec-title">{sec_rates}</div>
    <div class="rl-rates">
      <div class="rl-rate"><span>{rate_1_dur}</span><span class="rl-rate-price">{rate_1_price}</span></div>
      <div class="rl-rate"><span>{rate_2_dur}</span><span class="rl-rate-price">{rate_2_price}</span></div>
      <div class="rl-rate"><span>{rate_3_dur}</span><span class="rl-rate-price">{rate_3_price}</span></div>
    </div>
  </div>

  <!-- CTA #3 -->
  <button class="rl-cta-btn" style="width:100%;justify-content:center;margin-bottom:28px"
    onclick="document.getElementById('contact-anchor').scrollIntoView({{behavior:'smooth'}})">
    {btn_contact}
  </button>

  <hr class="rl-divider">

  <!-- IMPORTANT INFO -->
  <div class="rl-sec">
    <div class="rl-sec-title">{sec_info}</div>
    <div class="rl-info">
      <div class="rl-info-item">{info_1}</div>
      <div class="rl-info-item">{info_2}</div>
      <div class="rl-info-item">{info_3}</div>
    </div>
  </div>

  <!-- BOOK MESSAGE -->
  <div class="rl-book">{book_msg}</div>

  <!-- CONTACT SECTION -->
  <div class="rl-contact" id="contact-anchor">
    <div class="rl-contact-title">{sec_contact}</div>

    <!-- Telegram / WhatsApp кнопки -->
    <div class="rl-btns">
      {tg_btns_html}
    </div>

    <!-- Call me toggle -->
    <button class="rl-call-toggle" id="call-toggle-btn" onclick="togglePhones()">
      📞 {btn_call}
      <svg id="call-arrow" viewBox="0 0 20 20" fill="currentColor" width="16" height="16" style="transition:transform .25s"><path fill-rule="evenodd" d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd"/></svg>
    </button>

    <!-- Phones list -->
    <div class="rl-phones" id="phones-list">
      {phones_html if phones_html else '<div class="rl-phone-item"><span class="rl-phone-city" style="color:rgba(255,255,255,.35);width:100%;text-align:center">Телефоны не добавлены</span></div>'}
    </div>
  </div>

</div><!-- /wrap -->

<!-- MEDIA POPUP: Photos -->
<div class="rl-popup" id="popup-photos">
  <div class="rl-popup-header">
    <span class="rl-popup-title">📸 Photos</span>
    <button class="rl-popup-close" onclick="closePopup('photos')">✕</button>
  </div>
  <div class="rl-popup-gallery" id="gallery-photos">
    {photos_thumbs}
  </div>
</div>

<!-- MEDIA POPUP: Videos -->
<div class="rl-popup" id="popup-videos">
  <div class="rl-popup-header">
    <span class="rl-popup-title">🎬 Videos</span>
    <button class="rl-popup-close" onclick="closePopup('videos')">✕</button>
  </div>
  <div class="rl-popup-gallery" id="gallery-videos">
    {videos_thumbs}
  </div>
</div>

<!-- LIGHTBOX -->
<div class="rl-lightbox" id="lightbox">
  <button class="rl-lightbox-close" onclick="closeLightbox()">✕</button>
  <div id="lightbox-content"></div>
  <div class="rl-lightbox-nav">
    <button onclick="lightboxNav(-1)">← Prev</button>
    <button onclick="lightboxNav(1)">Next →</button>
  </div>
</div>

<!-- SCROLL TO TOP -->
<button class="rl-scroll-top" id="scroll-top-btn" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Back to top">↑</button>

<script>
// ── данные галерей ──────────────────────────────────────────
var _photos = {photos_json};
var _videos = {videos_json};
var _lbMode = 'photo';
var _lbIdx  = 0;

// ── popup ───────────────────────────────────────────────────
function openPopup(type) {{
  document.getElementById('popup-' + type).classList.add('open');
  document.body.style.overflow = 'hidden';
}}
function closePopup(type) {{
  document.getElementById('popup-' + type).classList.remove('open');
  document.body.style.overflow = '';
}}
// закрыть popup по клику на фон
['popup-photos','popup-videos'].forEach(function(id){{
  var el = document.getElementById(id);
  if(el) el.addEventListener('click', function(e){{
    if(e.target === el) closePopup(id.replace('popup-',''));
  }});
}});

// ── lightbox ────────────────────────────────────────────────
function openMedia(type, idx) {{
  _lbMode = type; _lbIdx = idx;
  renderLightbox();
  document.getElementById('lightbox').classList.add('open');
}}
function closeLightbox() {{
  document.getElementById('lightbox').classList.remove('open');
  document.getElementById('lightbox-content').innerHTML = '';
}}
function renderLightbox() {{
  var arr = _lbMode === 'photo' ? _photos : _videos;
  var url = arr[_lbIdx];
  var html = '';
  if(_lbMode === 'video') {{
    html = '<video src="'+url+'" controls autoplay style="max-width:min(500px,90vw);max-height:min(500px,80vh);border-radius:12px"></video>';
  }} else {{
    html = '<img src="'+url+'" alt="photo"/>';
  }}
  document.getElementById('lightbox-content').innerHTML = html;
}}
function lightboxNav(dir) {{
  var arr = _lbMode === 'photo' ? _photos : _videos;
  _lbIdx = (_lbIdx + dir + arr.length) % arr.length;
  renderLightbox();
}}
document.getElementById('lightbox').addEventListener('click', function(e){{
  if(e.target === this) closeLightbox();
}});

// ── phones toggle ───────────────────────────────────────────
function togglePhones() {{
  var list = document.getElementById('phones-list');
  var btn  = document.getElementById('call-toggle-btn');
  var arr  = document.getElementById('call-arrow');
  var open = list.classList.toggle('open');
  btn.classList.toggle('open', open);
  if(arr) arr.style.transform = open ? 'rotate(180deg)' : 'rotate(0deg)';
}}

// ── scroll to top ───────────────────────────────────────────
(function(){{
  var btn = document.getElementById('scroll-top-btn');
  var threshold = document.documentElement.scrollHeight * 0.25;
  window.addEventListener('scroll', function(){{
    btn.classList.toggle('visible', window.scrollY > threshold);
  }}, {{passive:true}});
}})();

// ── fbp cookie ──────────────────────────────────────────────
(function(){{
  if(!document.cookie.includes('_fbp')){{
    var fbp='fb.1.'+Date.now()+'.'+Math.random().toString(36).substr(2,9);
    document.cookie='_fbp='+fbp+';max-age=7776000;path=/;SameSite=Lax';
  }}
}})();
</script>
</body>
</html>"""
