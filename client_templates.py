"""
client_templates.py — HTML шаблоны клиентских лендингов

Шаблоны (одна блочная структура, 4 дизайна):
  _tpl_dark_luxury()     — тёмный, золото + глубокий градиент (default)
  _tpl_rose_elegant()    — розово-бежевый, светлый, женственный
  _tpl_neon_modern()     — тёмный неон, TikTok-стиль
  _tpl_midnight_blue()   — глубокий синий, премиум

Диспетчер:
  _render_client_landing() — выбирает нужный шаблон
"""

import json as _json


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

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


def _parse_list(texts: dict, key: str) -> list:
    raw = texts.get(key, "[]")
    try:
        result = _json.loads(raw) if isinstance(raw, str) else (raw or [])
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _build_contact_section(contacts: list) -> str:
    """
    Одна кнопка "Contact me" → попап городов → каналы города + телефон.
    contacts: [{type, label, url, city, phone}]
    Все данные (город, телефон) берутся из campaign_channels.
    """
    import json as _j

    TG_SVG = '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>'

    # Уникальные города (в порядке добавления)
    cities, seen = [], set()
    for c in contacts:
        city = (c.get("city") or "").strip()
        if city and city not in seen:
            cities.append(city)
            seen.add(city)

    # Данные для JS
    contacts_js = _j.dumps([
        {
            "type":        c.get("type", "telegram"),
            "label":       c.get("label", ""),
            "url":         c.get("url", ""),
            "city":        (c.get("city") or "").strip(),
            "phone":       (c.get("phone") or "").strip(),
            "address":     (c.get("address") or "").strip(),
            "tg_label":    (c.get("tg_label") or "").strip(),
            "phone_label": (c.get("phone_label") or "").strip(),
        }
        for c in contacts
    ])
    cities_js = _j.dumps(cities)

    if not contacts:
        return '<p style="color:rgba(255,255,255,.3);font-size:.85rem;text-align:center;padding:8px 0">Контакты не настроены</p>'

    return f"""
<!-- ОДНА КНОПКА -->
<button class="cl-btn cl-btn-contact-trigger" onclick="clOpenMain()">
  {TG_SVG} <span>Contact me</span>
</button>

<!-- ПОПАП ГОРОДОВ -->
<div class="cl-cpop" id="cl-city-popup">
  <div class="cl-cpop-overlay" onclick="clClose()"></div>
  <div class="cl-cpop-box">
    <div class="cl-cpop-hdr">
      <span>📍 Choose your city</span>
      <button class="cl-cpop-x" onclick="clClose()">✕</button>
    </div>
    <div id="cl-city-list"></div>
  </div>
</div>

<!-- ПОПАП КАНАЛОВ ГОРОДА -->
<div class="cl-cpop" id="cl-contact-popup">
  <div class="cl-cpop-overlay" onclick="clClose()"></div>
  <div class="cl-cpop-box">
    <div class="cl-cpop-hdr">
      <button class="cl-cpop-x cl-back-btn" id="cl-back-btn" onclick="clBack()">←</button>
      <span id="cl-contact-title">Contact</span>
      <button class="cl-cpop-x" onclick="clClose()">✕</button>
    </div>
    <div id="cl-contact-list"></div>
  </div>
</div>

<style>
.cl-btn-contact-trigger{{width:100%;border:none;cursor:pointer;font-family:inherit;font-weight:700;font-size:.94rem;transition:opacity .15s,transform .15s;letter-spacing:.02em}}.cl-btn-contact-trigger:hover{{opacity:.88;transform:translateY(-1px)}}
.cl-cpop{{display:none;position:fixed;inset:0;z-index:9500;align-items:flex-end;justify-content:center}}
.cl-cpop.open{{display:flex}}
.cl-cpop-overlay{{position:absolute;inset:0;background:rgba(0,0,0,.55);backdrop-filter:blur(4px)}}
.cl-cpop-box{{position:relative;z-index:1;width:100%;max-width:560px;background:#13131f;border-radius:20px 20px 0 0;padding:0 16px 32px;box-shadow:0 -8px 40px rgba(0,0,0,.5);animation:clSlide .25s ease;max-height:80vh;overflow-y:auto}}
@keyframes clSlide{{from{{transform:translateY(60px);opacity:0}}to{{transform:translateY(0);opacity:1}}}}
.cl-cpop-box::before{{content:'';display:block;width:40px;height:4px;background:rgba(255,255,255,.18);border-radius:2px;margin:12px auto 0}}
.cl-cpop-hdr{{display:flex;align-items:center;justify-content:space-between;padding:14px 4px 10px;color:rgba(255,255,255,.7);font-size:.85rem;font-weight:600}}
.cl-cpop-x{{background:rgba(255,255,255,.1);border:none;color:#fff;width:30px;height:30px;border-radius:50%;font-size:1rem;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:background .15s}}
.cl-cpop-x:hover{{background:rgba(255,255,255,.2)}}
.cl-back-btn{{display:none}}
.cl-city-btn{{width:100%;display:flex;align-items:center;padding:13px 16px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);color:#fff;font-size:.92rem;font-weight:600;cursor:pointer;margin-bottom:8px;transition:background .15s;text-align:left;font-family:inherit}}
.cl-city-btn:hover{{background:rgba(255,255,255,.1)}}
.cl-city-all{{background:rgba(255,255,255,.02);color:rgba(255,255,255,.45);font-weight:400;border-style:dashed}}
.cl-city-all:hover{{background:rgba(255,255,255,.06)}}
.cl-contact-item{{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;padding:14px;border-radius:12px;font-weight:700;font-size:.93rem;text-decoration:none;margin-bottom:10px;background:#26A5E4;color:#fff;border:none;cursor:pointer;font-family:inherit;transition:opacity .15s}}
.cl-contact-item:hover{{opacity:.88}}
.cl-contact-item.wa{{background:#25D366}}
.cl-phone-item{{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);margin-bottom:8px}}
.cl-phone-city{{font-size:.82rem;color:rgba(255,255,255,.5);font-weight:500}}
.cl-phone-num{{font-size:.9rem;font-weight:700;color:#a5f3fc;text-decoration:none;letter-spacing:.02em}}
.cl-phone-num:hover{{color:#67e8f9}}
</style>

<script>
(function(){{
  var _contacts = {contacts_js};
  var _cities   = {cities_js};
  var _hasCities = _cities.length > 0;
  var TG = '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M9.036 15.28 8.87 18.64c.34 0 .49-.15.67-.33l1.6-1.54 3.31 2.43c.61.34 1.05.16 1.22-.56l2.2-10.3c.2-.9-.32-1.25-.92-1.03L3.9 10.01c-.88.34-.86.83-.15 1.05l3.29 1.02 7.64-4.82c.36-.23.69-.1.42.14z"/></svg>';
  var WA = '<svg viewBox="0 0 24 24" fill="currentColor" width="18" height="18"><path d="M20 3.5A10 10 0 0 0 4.2 17.3L3 21l3.8-1.2A10 10 0 1 0 20 3.5Z"/></svg>';

  function _lock()  {{ document.body.style.overflow = 'hidden'; }}
  function _unlock(){{ document.body.style.overflow = ''; }}

  window.clClose = function() {{
    document.getElementById('cl-city-popup').classList.remove('open');
    document.getElementById('cl-contact-popup').classList.remove('open');
    _unlock();
  }};

  window.clBack = function() {{
    document.getElementById('cl-contact-popup').classList.remove('open');
    document.getElementById('cl-city-popup').classList.add('open');
  }};

  window.clOpenMain = function() {{
    if (_hasCities) {{
      _showCities();
    }} else {{
      _showContacts(_contacts, null);
    }}
  }};

  function _showCities() {{
    var list = document.getElementById('cl-city-list');
    list.innerHTML = '';
    _cities.forEach(function(city) {{
      var btn = document.createElement('button');
      btn.className = 'cl-city-btn';
      btn.innerHTML = '📍 ' + city;
      btn.onclick = function() {{
        document.getElementById('cl-city-popup').classList.remove('open');
        var filtered = _contacts.filter(function(c) {{ return !c.city || c.city === city; }});
        _showContacts(filtered, city);
      }};
      list.appendChild(btn);
    }});

    document.getElementById('cl-city-popup').classList.add('open');
    _lock();
  }}

  function _showContacts(list, cityLabel) {{
    var el = document.getElementById('cl-contact-list');
    var title = document.getElementById('cl-contact-title');
    var backBtn = document.getElementById('cl-back-btn');
    el.innerHTML = '';
    if (cityLabel) {{
      title.textContent = '📍 ' + cityLabel;
      backBtn.style.display = 'flex';
    }} else {{
      title.textContent = 'Contact';
      backBtn.style.display = 'none';
    }}
    if (!list.length) {{
      el.innerHTML = '<p style="color:rgba(255,255,255,.4);text-align:center;padding:16px;font-size:.85rem">Нет контактов для этого города</p>';
    }} else {{
      // Берём общие данные из первого контакта (address, tg_label, phone_label, phone)
      var phone = '', address = '', tgLabel = '', phoneLabel = '';
      for (var i = 0; i < list.length; i++) {{
        if (!phone && list[i].phone)       phone = list[i].phone;
        if (!address && list[i].address)   address = list[i].address;
        if (!tgLabel && list[i].tg_label)  tgLabel = list[i].tg_label;
        if (!phoneLabel && list[i].phone_label) phoneLabel = list[i].phone_label;
      }}
      // Адреса над кнопками (каждая строка — отдельный адрес)
      if (address) {{
        var lines = address.split('\n').map(function(s){{return s.trim();}}).filter(Boolean);
        lines.forEach(function(line) {{
          var addrEl = document.createElement('div');
          addrEl.style.cssText = 'display:flex;align-items:flex-start;gap:8px;padding:9px 14px;'
            + 'background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);'
            + 'border-radius:10px;margin-bottom:8px;font-size:.83rem;color:rgba(255,255,255,.65);line-height:1.5';
          addrEl.innerHTML = '<span style="flex-shrink:0;font-size:.95rem">📍</span><span>' + line + '</span>';
          el.appendChild(addrEl);
        }});
      }}
      // Заголовок перед TG кнопками
      if (tgLabel) {{
        var tgH = document.createElement('div');
        tgH.style.cssText = 'font-size:.76rem;font-weight:600;color:rgba(255,255,255,.45);'
          + 'text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;margin-top:4px';
        tgH.textContent = tgLabel;
        el.appendChild(tgH);
      }}
      // Кнопки каналов
      list.forEach(function(c) {{
        var svg = c.type === 'whatsapp' ? WA : TG;
        var cls = c.type === 'whatsapp' ? 'cl-contact-item wa call-button' : 'cl-contact-item call-button';
        var a = document.createElement('a');
        a.className = cls;
        a.href = c.url;
        a.target = '_blank';
        a.rel = 'noopener';
        a.innerHTML = svg + '<span>' + c.label + '</span>';
        a.addEventListener('click', function() {{
          window.clClose();
          if (typeof fbq !== 'undefined') fbq('track', 'Contact');
          if (typeof ttq !== 'undefined') ttq.track('Contact');
        }});
        el.appendChild(a);
      }});
      // Заголовок перед телефоном
      if (phone) {{
        if (phoneLabel) {{
          var phH = document.createElement('div');
          phH.style.cssText = 'font-size:.76rem;font-weight:600;color:rgba(255,255,255,.45);'
            + 'text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;margin-top:10px';
          phH.textContent = phoneLabel;
          el.appendChild(phH);
        }}
        var ph = document.createElement('div');
        ph.className = 'cl-phone-item';
        ph.innerHTML = '<span class="cl-phone-city">📞 ' + (cityLabel || 'Phone') + '</span>'
          + '<a href="tel:' + phone.replace(/ /g,'') + '" class="cl-phone-num">' + phone + '</a>';
        el.appendChild(ph);
      }}
    }}
    document.getElementById('cl-contact-popup').classList.add('open');
    _lock();
  }}
}})();
</script>"""


def _shared_popup_and_js(accent: str = "#6b21a8") -> str:
    """Общий JS — только scroll-to-top."""
    return f"""
<button class="cl-stb" id="stb" onclick="window.scrollTo({{top:0,behavior:'smooth'}})">↑</button>
<style>
.cl-stb{{position:fixed;bottom:24px;right:20px;width:44px;height:44px;border-radius:50%;background:{accent};color:#fff;border:none;font-size:1.3rem;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 20px rgba(0,0,0,.4);opacity:0;pointer-events:none;transition:opacity .3s,transform .3s;z-index:8000;transform:translateY(12px)}}
.cl-stb.visible{{opacity:1;pointer-events:auto;transform:translateY(0)}}
</style>
<script>
(function(){{
  var btn=document.getElementById('stb');
  function upd(){{var th=document.documentElement.scrollHeight*0.25;btn.classList.toggle('visible',window.scrollY>th)}}
  window.addEventListener('scroll',upd,{{passive:true}});upd();
}})();
(function(){{if(!document.cookie.includes('_fbp')){{var f='fb.1.'+Date.now()+'.'+Math.random().toString(36).substr(2,9);document.cookie='_fbp='+f+';max-age=7776000;path=/;SameSite=Lax'}}}})();
</script>"""


def _get_texts(texts: dict) -> dict:
    return {
        "top_bar":      _t(texts, "top_bar",      "⚠️ No Fake Service 💯"),
        "hero_title":   _t(texts, "hero_title",   "Relaxation and Balance 🌿✨"),
        "hero_sub":     _t(texts, "hero_sub",     "I invite you to enjoy a soothing body massage in a comfortable, private setting."),
        "btn_contact":  _t(texts, "btn_contact",  "Contact me"),
        "sec_included": _t(texts, "sec_included", "Included in the session:"),
        "utp_1":        _t(texts, "utp_1",        "💆‍♂️ Full body massage"),
        "utp_2":        _t(texts, "utp_2",        "🤍 Full body contact massage"),
        "utp_3":        _t(texts, "utp_3",        "🔥 Relaxation completion"),
        "desc_box":     _t(texts, "desc_box",     "✨ I'll greet you in elegant attire and provide a relaxing massage in comfortable, minimal clothing. Touching me is not allowed."),
        "media_title":  _t(texts, "media_title",  "📸 Photos and Videos"),
        "sec_rates":    _t(texts, "sec_rates",    "💰 Rates:"),
        "rate_1_dur":   _t(texts, "rate_1_dur",   "60 min"),
        "rate_1_price": _t(texts, "rate_1_price", "$230"),
        "rate_2_dur":   _t(texts, "rate_2_dur",   "30 min"),
        "rate_2_price": _t(texts, "rate_2_price", "$200"),
        "rate_3_dur":   _t(texts, "rate_3_dur",   "15 min"),
        "rate_3_price": _t(texts, "rate_3_price", "$140"),
        "sec_info":     _t(texts, "sec_info",     "📋 Important Information:"),
        "info_1":       _t(texts, "info_1",       "📌 Extra services can only be discussed in person during the session."),
        "info_2":       _t(texts, "info_2",       "💵 Payment is accepted in cash only. Please prepare the exact amount."),
        "info_3":       _t(texts, "info_3",       "⚠️ Same-day appointments only. Advance bookings are not available."),
        "book_msg":     _t(texts, "book_msg",     "💌 Message me to book your session!"),
        "sec_contact":  _t(texts, "sec_contact",  "Contact me:"),
        "btn_call":     _t(texts, "btn_call",     "Call me or text me"),
        "hero_bg":      _t(texts, "hero_bg",      ""),
        "photo_url":    _t(texts, "photo_url",    ""),
        "video_url":    _t(texts, "video_url",    ""),
        "btn_photo":    _t(texts, "btn_photo",    "📷 Photos"),
        "btn_video":    _t(texts, "btn_video",    "🎬 Videos"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# DISPATCHER
# ══════════════════════════════════════════════════════════════════════════════

def _render_client_landing(landing: dict, contacts: list, pixel_id: str = "", tt_pixel: str = "",
                           db=None, campaign_phones: list = None) -> str:
    """
    campaign_phones — список {city, phone} из кампании (приоритет над phones в шаблоне).
    Если передан — используем его. Если нет — берём из texts шаблона (для прямого /l/{slug}).
    """
    try:
        lcontent = _json.loads(landing.get("content", "{}"))
        template = lcontent.get("template", "dark_luxury")
        texts    = lcontent.get("texts", {})
    except Exception:
        template = "dark_luxury"
        texts    = {}

    tt_pixel_id = tt_pixel or (db.get_setting("tiktok_pixel_id", "") if db else "") or (db.get_setting("tt_pixel_id", "") if db else "")
    px = _pixel_js(pixel_id) + _tiktok_pixel_js(tt_pixel_id)


    if template == "rose_elegant":
        return _tpl_rose_elegant(texts, contacts, px)
    elif template == "neon_modern":
        return _tpl_neon_modern(texts, contacts, px)
    elif template == "midnight_blue":
        return _tpl_midnight_blue(texts, contacts, px)
    else:
        return _tpl_dark_luxury(texts, contacts, px)


def _media_buttons(T: dict, css_class_ph: str = "", css_class_vi: str = "") -> str:
    """Кнопки Фото и Видео — прямые ссылки, без галереи."""
    ph_url = T.get("photo_url", "")
    vi_url = T.get("video_url", "")
    ph_label = T.get("btn_photo", "📷 Photos")
    vi_label = T.get("btn_video", "🎬 Videos")
    ph_btn = (f'<a class="media-btn {css_class_ph}" href="{ph_url}" target="_blank" rel="noopener">{ph_label}</a>'
              if ph_url else f'<button class="media-btn {css_class_ph}" disabled style="opacity:.4;cursor:default">{ph_label}</button>')
    vi_btn = (f'<a class="media-btn {css_class_vi}" href="{vi_url}" target="_blank" rel="noopener">{vi_label}</a>'
              if vi_url else f'<button class="media-btn {css_class_vi}" disabled style="opacity:.4;cursor:default">{vi_label}</button>')
    return ph_btn + vi_btn


# ══════════════════════════════════════════════════════════════════════════════
# TPL 1 — DARK LUXURY  (тёмный, золото, Playfair Display)
# ══════════════════════════════════════════════════════════════════════════════

def _tpl_dark_luxury(texts, contacts, pixel_js):
    T  = _get_texts(texts)
    bt = _build_contact_section(contacts)
    sh = _shared_popup_and_js(accent="#b8862d")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{T["hero_title"]}</title>{pixel_js}
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600;700;800&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}
body{{font-family:'Inter',sans-serif;background:#080608;color:#e8ddd0;min-height:100vh;-webkit-font-smoothing:antialiased}}a{{text-decoration:none;color:inherit}}
.w{{max-width:560px;margin:0 auto;padding:0 20px}}
.topbar{{background:linear-gradient(90deg,#1a0e00,#2d1f05,#1a0e00);border-bottom:1px solid rgba(184,134,45,.25);padding:11px 20px;text-align:center;font-size:.73rem;font-weight:700;color:#d4a843;letter-spacing:.12em;text-transform:uppercase}}
.hero{{position:relative;min-height:58vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
.hero::before{{content:"";position:absolute;inset:0;background:url('{{T["hero_bg"] or "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop"}}') center/cover;filter:brightness(.22)}}
.hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(8,6,8,.2),rgba(8,6,8,1) 96%)}}
.hero-in{{position:relative;z-index:1;padding:64px 20px 52px}}
h1{{font-family:'Playfair Display',serif;font-size:clamp(2rem,5.5vw,3rem);font-weight:800;line-height:1.1;margin-bottom:16px;background:linear-gradient(135deg,#f0d080,#d4a843,#f0d080);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.hero p{{color:rgba(232,221,208,.6);max-width:420px;margin:0 auto 32px;font-size:.93rem;font-weight:300;line-height:1.8}}
.cta{{display:inline-flex;align-items:center;gap:8px;padding:14px 32px;border-radius:3px;background:linear-gradient(135deg,#b8862d,#d4a843);color:#0a0700;font-weight:700;font-size:.93rem;cursor:pointer;border:none;transition:opacity .15s;font-family:'Inter',sans-serif;letter-spacing:.04em}}
.cl-btn-contact-trigger{{background:linear-gradient(135deg,#b8862d,#d4a843)!important;color:#0a0700!important;border-radius:3px;padding:15px 32px;font-family:'Inter',sans-serif;letter-spacing:.04em}}
.cta:hover{{opacity:.9}}
.cta-o{{display:flex;align-items:center;justify-content:center;width:100%;padding:14px;border-radius:3px;background:transparent;border:1px solid rgba(184,134,45,.4);color:#d4a843;font-weight:600;font-size:.93rem;cursor:pointer;transition:background .15s;font-family:'Inter',sans-serif}}
.cta-o:hover{{background:rgba(184,134,45,.08)}}
.sec{{padding:36px 0 8px}}.sec-t{{font-family:'Playfair Display',serif;font-size:1rem;font-weight:700;color:#d4a843;margin-bottom:16px;text-transform:uppercase;letter-spacing:.08em}}
.utp{{display:flex;flex-direction:column;gap:1px;margin-bottom:28px;border:1px solid rgba(184,134,45,.16);border-radius:5px;overflow:hidden}}
.utp-i{{background:rgba(255,255,255,.03);padding:15px 20px;font-size:.91rem;border-bottom:1px solid rgba(184,134,45,.1)}}.utp-i:last-child{{border-bottom:none}}
.desc{{background:rgba(184,134,45,.06);border-left:3px solid #d4a843;padding:18px 22px;font-size:.88rem;line-height:1.8;color:rgba(232,221,208,.76);margin-bottom:28px;font-style:italic}}
.media{{display:flex;gap:12px;margin-bottom:28px}}
.media-btn{{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:3px;font-weight:600;font-size:.87rem;cursor:pointer;border:1px solid rgba(184,134,45,.28);background:rgba(184,134,45,.07);color:#d4a843;transition:background .15s;font-family:'Inter',sans-serif}}
.media-btn:hover{{background:rgba(184,134,45,.14)}}
.rates{{display:flex;flex-direction:column;gap:1px;border:1px solid rgba(184,134,45,.16);border-radius:5px;overflow:hidden;margin-bottom:24px}}
.rate{{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.03);padding:15px 22px;font-size:.93rem;border-bottom:1px solid rgba(184,134,45,.08)}}.rate:last-child{{border-bottom:none}}
.rate-p{{font-family:'Playfair Display',serif;font-size:1.15rem;font-weight:700;color:#d4a843}}
.info{{border:1px solid rgba(184,134,45,.14);border-radius:5px;padding:20px 22px;margin-bottom:28px;display:flex;flex-direction:column;gap:12px}}
.info-i{{font-size:.87rem;line-height:1.75;color:rgba(232,221,208,.68)}}
.divider{{border:none;border-top:1px solid rgba(184,134,45,.1);margin:10px 0 28px}}
.book{{text-align:center;font-size:.9rem;color:rgba(232,221,208,.38);padding:16px 0 28px;border-top:1px solid rgba(184,134,45,.09)}}
.contact{{text-align:center;padding:8px 0 68px;scroll-margin-top:20px}}
.contact-t{{font-family:'Playfair Display',serif;font-size:1.4rem;font-weight:700;margin-bottom:28px;color:#e8ddd0}}
.btns{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.cl-btn{{border-radius:3px;font-family:'Inter',sans-serif}}
.call-tog{{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:14px;border-radius:3px;background:transparent;border:1px solid rgba(232,221,208,.16);color:#e8ddd0;font-weight:600;font-size:.93rem;cursor:pointer;transition:background .15s;font-family:'Inter',sans-serif;margin-top:4px}}
.call-tog:hover{{background:rgba(255,255,255,.04)}}.call-tog.open{{border-color:rgba(184,134,45,.4);color:#d4a843}}
</style></head><body>
<div class="topbar">{T["top_bar"]}</div>
<div class="hero"><div class="hero-in">
  <h1>{T["hero_title"]}</h1><p>{T["hero_sub"]}</p>
  <button class="cta" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]} →</button>
</div></div>
<div class="w">
  <div class="sec"><div class="sec-t">{T["sec_included"]}</div>
  <div class="utp"><div class="utp-i">{T["utp_1"]}</div><div class="utp-i">{T["utp_2"]}</div><div class="utp-i">{T["utp_3"]}</div></div></div>
  <div class="desc">{T["desc_box"]}</div>
  <div class="sec" style="padding-bottom:0"><div class="sec-t">{T["media_title"]}</div></div>
  <div class="media">{_media_buttons(T)}</div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_rates"]}</div>
  <div class="rates"><div class="rate"><span>{T["rate_1_dur"]}</span><span class="rate-p">{T["rate_1_price"]}</span></div><div class="rate"><span>{T["rate_2_dur"]}</span><span class="rate-p">{T["rate_2_price"]}</span></div><div class="rate"><span>{T["rate_3_dur"]}</span><span class="rate-p">{T["rate_3_price"]}</span></div></div></div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_info"]}</div>
  <div class="info"><div class="info-i">{T["info_1"]}</div><div class="info-i">{T["info_2"]}</div><div class="info-i">{T["info_3"]}</div></div></div>
  <div class="book">{T["book_msg"]}</div>
  <div class="contact" id="ca">
    <div class="contact-t">{T["sec_contact"]}</div>
    <div class="btns">{bt}</div>
  </div>
</div>{sh}</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# TPL 2 — ROSE ELEGANT  (светлый, розово-бежевый, Cormorant Garamond)
# ══════════════════════════════════════════════════════════════════════════════

def _tpl_rose_elegant(texts, contacts, pixel_js):
    T  = _get_texts(texts)
    bt = _build_contact_section(contacts)
    sh = _shared_popup_and_js(accent="#c2185b")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{T["hero_title"]}</title>{pixel_js}
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}
body{{font-family:'Inter',sans-serif;background:#fdf8f5;color:#2d1f1a;min-height:100vh;-webkit-font-smoothing:antialiased}}a{{text-decoration:none;color:inherit}}
.w{{max-width:560px;margin:0 auto;padding:0 20px}}
.topbar{{background:#2d1f1a;padding:11px 20px;text-align:center;font-size:.72rem;font-weight:600;color:#f5e6d3;letter-spacing:.1em;text-transform:uppercase}}
.hero{{position:relative;min-height:56vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
.hero::before{{content:"";position:absolute;inset:0;background:url('{{T["hero_bg"] or "https://images.unsplash.com/photo-1552693673-1bf958298935?q=80&w=1920&auto=format&fit=crop"}}') center/cover;filter:brightness(.52) saturate(.85)}}
.hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(253,248,245,.05),rgba(253,248,245,1) 96%)}}
.hero-in{{position:relative;z-index:1;padding:72px 20px 56px}}
h1{{font-family:'Cormorant Garamond',serif;font-size:clamp(2.2rem,6vw,3.4rem);font-weight:700;line-height:1.1;margin-bottom:16px;color:#2d1f1a}}
.hero p{{color:#7a5a50;max-width:380px;margin:0 auto 32px;font-size:.92rem;font-weight:300;line-height:1.85}}
.cta{{display:inline-flex;align-items:center;gap:8px;padding:14px 36px;border-radius:2px;background:#2d1f1a;color:#f5e6d3;font-weight:600;font-size:.9rem;cursor:pointer;border:none;transition:background .15s;letter-spacing:.06em;font-family:'Inter',sans-serif}}
.cl-btn-contact-trigger{{background:#2d1f1a!important;color:#f5e6d3!important;border-radius:2px;padding:15px;font-family:'Inter',sans-serif;letter-spacing:.05em}}
.cta:hover{{background:#3d2f2a}}
.cta-o{{display:flex;align-items:center;justify-content:center;width:100%;padding:14px;border-radius:2px;background:transparent;border:1px solid #c8a99a;color:#2d1f1a;font-weight:600;font-size:.9rem;cursor:pointer;transition:background .15s;font-family:'Inter',sans-serif}}
.cta-o:hover{{background:rgba(45,31,26,.05)}}
.sec{{padding:36px 0 8px}}.sec-t{{font-family:'Cormorant Garamond',serif;font-size:1.15rem;font-weight:600;color:#2d1f1a;margin-bottom:16px}}
.utp{{display:flex;flex-direction:column;gap:8px;margin-bottom:28px}}
.utp-i{{background:#fff;border:1px solid #ecddd6;border-radius:3px;padding:14px 20px;font-size:.91rem;color:#4a3028;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.desc{{background:#fff8f5;border-left:3px solid #c2185b;padding:18px 22px;font-size:.88rem;line-height:1.85;color:#5a3f37;margin-bottom:28px;font-style:italic}}
.media{{display:flex;gap:12px;margin-bottom:28px}}
.media-btn{{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:2px;font-weight:600;font-size:.87rem;cursor:pointer;border:1px solid #ecddd6;background:#fff;color:#2d1f1a;transition:background .15s;font-family:'Inter',sans-serif;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.media-btn:hover{{background:#fdf0eb}}
.rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:24px}}
.rate{{display:flex;justify-content:space-between;align-items:center;background:#fff;border:1px solid #ecddd6;border-radius:3px;padding:15px 22px;font-size:.93rem;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.rate-p{{font-family:'Cormorant Garamond',serif;font-size:1.2rem;font-weight:700;color:#c2185b}}
.info{{background:#fff;border:1px solid #ecddd6;border-radius:3px;padding:20px 22px;margin-bottom:28px;display:flex;flex-direction:column;gap:12px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.info-i{{font-size:.87rem;line-height:1.75;color:#5a3f37}}
.divider{{border:none;border-top:1px solid #ecddd6;margin:10px 0 28px}}
.book{{text-align:center;font-size:.9rem;color:#9a7a70;padding:16px 0 28px;border-top:1px solid #ecddd6;font-style:italic}}
.contact{{text-align:center;padding:8px 0 68px;scroll-margin-top:20px}}
.contact-t{{font-family:'Cormorant Garamond',serif;font-size:1.6rem;font-weight:700;margin-bottom:28px;color:#2d1f1a}}
.btns{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.cl-btn{{border-radius:3px;font-family:'Inter',sans-serif}}
.cl-phones-list{{background:#fff!important;border-color:#ecddd6!important}}
.cl-phone-city{{color:#9a7a70!important}}
.call-tog{{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:14px;border-radius:2px;background:#fff;border:1px solid #ecddd6;color:#2d1f1a;font-weight:600;font-size:.9rem;cursor:pointer;transition:background .15s;font-family:'Inter',sans-serif;margin-top:4px;box-shadow:0 1px 3px rgba(0,0,0,.04)}}
.call-tog:hover{{background:#fdf0eb}}.call-tog.open{{border-color:#c2185b;color:#c2185b}}
</style></head><body>
<div class="topbar">{T["top_bar"]}</div>
<div class="hero"><div class="hero-in">
  <h1>{T["hero_title"]}</h1><p>{T["hero_sub"]}</p>
  <button class="cta" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
</div></div>
<div class="w">
  <div class="sec"><div class="sec-t">{T["sec_included"]}</div>
  <div class="utp"><div class="utp-i">{T["utp_1"]}</div><div class="utp-i">{T["utp_2"]}</div><div class="utp-i">{T["utp_3"]}</div></div></div>
  <div class="desc">{T["desc_box"]}</div>
  <div class="sec" style="padding-bottom:0"><div class="sec-t">{T["media_title"]}</div></div>
  <div class="media">{_media_buttons(T)}</div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_rates"]}</div>
  <div class="rates"><div class="rate"><span>{T["rate_1_dur"]}</span><span class="rate-p">{T["rate_1_price"]}</span></div><div class="rate"><span>{T["rate_2_dur"]}</span><span class="rate-p">{T["rate_2_price"]}</span></div><div class="rate"><span>{T["rate_3_dur"]}</span><span class="rate-p">{T["rate_3_price"]}</span></div></div></div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_info"]}</div>
  <div class="info"><div class="info-i">{T["info_1"]}</div><div class="info-i">{T["info_2"]}</div><div class="info-i">{T["info_3"]}</div></div></div>
  <div class="book">{T["book_msg"]}</div>
  <div class="contact" id="ca">
    <div class="contact-t">{T["sec_contact"]}</div>
    <div class="btns">{bt}</div>
  </div>
</div>{sh}</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# TPL 3 — NEON MODERN  (тёмный, пурпурный неон, Space Grotesk)
# ══════════════════════════════════════════════════════════════════════════════

def _tpl_neon_modern(texts, contacts, pixel_js):
    T  = _get_texts(texts)
    bt = _build_contact_section(contacts)
    sh = _shared_popup_and_js(accent="#d946ef")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{T["hero_title"]}</title>{pixel_js}
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}
body{{font-family:'Space Grotesk',sans-serif;background:#080010;color:#f0e6ff;min-height:100vh;-webkit-font-smoothing:antialiased}}a{{text-decoration:none;color:inherit}}
.w{{max-width:560px;margin:0 auto;padding:0 20px}}
.topbar{{background:linear-gradient(90deg,#0d001a,#1a0030,#0d001a);border-bottom:1px solid rgba(217,70,239,.3);padding:11px 20px;text-align:center;font-size:.72rem;font-weight:700;color:#e879f9;letter-spacing:.12em;text-transform:uppercase}}
.hero{{position:relative;min-height:60vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
.hero::before{{content:"";position:absolute;inset:0;background:url('{{T["hero_bg"] or "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop"}}') center/cover;filter:brightness(.18) saturate(.5)}}
.hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(8,0,16,.1),rgba(8,0,16,1) 92%)}}
.hero-glow{{position:absolute;top:0;left:50%;transform:translateX(-50%);width:600px;height:400px;background:radial-gradient(ellipse,rgba(217,70,239,.22),transparent 70%);pointer-events:none;z-index:1}}
.hero-in{{position:relative;z-index:2;padding:72px 20px 60px}}
h1{{font-size:clamp(2rem,5.5vw,2.9rem);font-weight:800;line-height:1.1;margin-bottom:16px;background:linear-gradient(135deg,#f0e6ff,#e879f9,#c026d3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.hero p{{color:rgba(240,230,255,.52);max-width:400px;margin:0 auto 32px;font-size:.93rem;font-weight:300;line-height:1.8}}
.cta{{display:inline-flex;align-items:center;gap:8px;padding:14px 32px;border-radius:50px;background:linear-gradient(135deg,#d946ef,#9333ea);color:#fff;font-weight:700;font-size:.93rem;cursor:pointer;border:none;transition:opacity .15s,box-shadow .15s;box-shadow:0 0 24px rgba(217,70,239,.35);font-family:'Space Grotesk',sans-serif}}
.cl-btn-contact-trigger{{background:linear-gradient(135deg,#d946ef,#9333ea)!important;color:#fff!important;border-radius:50px;padding:15px;box-shadow:0 0 24px rgba(217,70,239,.35);font-family:'Space Grotesk',sans-serif}}
.cta:hover{{opacity:.9;box-shadow:0 0 36px rgba(217,70,239,.5)}}
.cta-o{{display:flex;align-items:center;justify-content:center;width:100%;padding:14px;border-radius:50px;background:transparent;border:1px solid rgba(217,70,239,.32);color:#e879f9;font-weight:600;font-size:.93rem;cursor:pointer;transition:background .15s;font-family:'Space Grotesk',sans-serif}}
.cta-o:hover{{background:rgba(217,70,239,.08)}}
.sec{{padding:36px 0 8px}}.sec-t{{font-size:.76rem;font-weight:700;color:#d946ef;margin-bottom:16px;text-transform:uppercase;letter-spacing:.14em}}
.utp{{display:flex;flex-direction:column;gap:8px;margin-bottom:28px}}
.utp-i{{background:rgba(217,70,239,.06);border:1px solid rgba(217,70,239,.18);border-radius:12px;padding:14px 20px;font-size:.91rem}}
.desc{{background:rgba(147,51,234,.06);border:1px solid rgba(147,51,234,.22);border-radius:12px;padding:18px 22px;font-size:.88rem;line-height:1.8;color:rgba(240,230,255,.72);margin-bottom:28px}}
.media{{display:flex;gap:12px;margin-bottom:28px}}
.media-btn{{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:12px;font-weight:700;font-size:.87rem;cursor:pointer;transition:background .15s;font-family:'Space Grotesk',sans-serif}}
.media-btn.ph{{background:rgba(217,70,239,.1);border:1px solid rgba(217,70,239,.28);color:#e879f9}}.media-btn.ph:hover{{background:rgba(217,70,239,.18)}}
.media-btn.vi{{background:rgba(147,51,234,.1);border:1px solid rgba(147,51,234,.28);color:#c4b5fd}}.media-btn.vi:hover{{background:rgba(147,51,234,.18)}}
.rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:24px}}
.rate{{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.03);border:1px solid rgba(217,70,239,.14);border-radius:12px;padding:15px 22px;font-size:.93rem}}
.rate-p{{font-size:1.1rem;font-weight:800;background:linear-gradient(135deg,#e879f9,#c026d3);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.info{{background:rgba(255,255,255,.02);border:1px solid rgba(217,70,239,.1);border-radius:12px;padding:20px 22px;margin-bottom:28px;display:flex;flex-direction:column;gap:12px}}
.info-i{{font-size:.87rem;line-height:1.75;color:rgba(240,230,255,.62)}}
.divider{{border:none;border-top:1px solid rgba(217,70,239,.1);margin:10px 0 28px}}
.book{{text-align:center;font-size:.9rem;color:rgba(240,230,255,.33);padding:16px 0 28px;border-top:1px solid rgba(217,70,239,.1)}}
.contact{{text-align:center;padding:8px 0 68px;scroll-margin-top:20px}}
.contact-t{{font-size:1.4rem;font-weight:800;margin-bottom:28px;background:linear-gradient(135deg,#f0e6ff,#e879f9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}}
.btns{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.cl-btn{{border-radius:12px;font-family:'Space Grotesk',sans-serif}}
.call-tog{{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:14px;border-radius:12px;background:transparent;border:1px solid rgba(240,230,255,.14);color:#f0e6ff;font-weight:600;font-size:.93rem;cursor:pointer;transition:background .15s;font-family:'Space Grotesk',sans-serif;margin-top:4px}}
.call-tog:hover{{background:rgba(255,255,255,.04)}}.call-tog.open{{border-color:rgba(217,70,239,.4);color:#e879f9}}
</style></head><body>
<div class="topbar">{T["top_bar"]}</div>
<div class="hero"><div class="hero-glow"></div><div class="hero-in">
  <h1>{T["hero_title"]}</h1><p>{T["hero_sub"]}</p>
  <button class="cta" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]} ↓</button>
</div></div>
<div class="w">
  <div class="sec"><div class="sec-t">{T["sec_included"]}</div>
  <div class="utp"><div class="utp-i">{T["utp_1"]}</div><div class="utp-i">{T["utp_2"]}</div><div class="utp-i">{T["utp_3"]}</div></div></div>
  <div class="desc">{T["desc_box"]}</div>
  <div class="sec" style="padding-bottom:0"><div class="sec-t">{T["media_title"]}</div></div>
  <div class="media">{_media_buttons(T, 'ph', 'vi')}</div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_rates"]}</div>
  <div class="rates"><div class="rate"><span>{T["rate_1_dur"]}</span><span class="rate-p">{T["rate_1_price"]}</span></div><div class="rate"><span>{T["rate_2_dur"]}</span><span class="rate-p">{T["rate_2_price"]}</span></div><div class="rate"><span>{T["rate_3_dur"]}</span><span class="rate-p">{T["rate_3_price"]}</span></div></div></div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_info"]}</div>
  <div class="info"><div class="info-i">{T["info_1"]}</div><div class="info-i">{T["info_2"]}</div><div class="info-i">{T["info_3"]}</div></div></div>
  <div class="book">{T["book_msg"]}</div>
  <div class="contact" id="ca">
    <div class="contact-t">{T["sec_contact"]}</div>
    <div class="btns">{bt}</div>
  </div>
</div>{sh}</body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
# TPL 4 — MIDNIGHT BLUE  (глубокий синий, DM Serif Display)
# ══════════════════════════════════════════════════════════════════════════════

def _tpl_midnight_blue(texts, contacts, pixel_js):
    T  = _get_texts(texts)
    bt = _build_contact_section(contacts)
    sh = _shared_popup_and_js(accent="#3b82f6")
    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{T["hero_title"]}</title>{pixel_js}
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Serif+Display:ital@0;1&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}html{{scroll-behavior:smooth}}
body{{font-family:'DM Sans',sans-serif;background:#050d1a;color:#dce8f5;min-height:100vh;-webkit-font-smoothing:antialiased}}a{{text-decoration:none;color:inherit}}
.w{{max-width:560px;margin:0 auto;padding:0 20px}}
.topbar{{background:linear-gradient(90deg,#060f1f,#0a1628,#060f1f);border-bottom:1px solid rgba(59,130,246,.2);padding:11px 20px;text-align:center;font-size:.72rem;font-weight:600;color:#93c5fd;letter-spacing:.1em;text-transform:uppercase}}
.hero{{position:relative;min-height:58vh;display:flex;align-items:center;justify-content:center;text-align:center;overflow:hidden}}
.hero::before{{content:"";position:absolute;inset:0;background:url('{{T["hero_bg"] or "https://images.unsplash.com/photo-1544161515-4ab6ce6db874?q=80&w=1920&auto=format&fit=crop"}}') center/cover;filter:brightness(.2) saturate(.7) hue-rotate(200deg)}}
.hero::after{{content:"";position:absolute;inset:0;background:linear-gradient(to bottom,rgba(5,13,26,.2),rgba(5,13,26,1) 94%)}}
.hero-in{{position:relative;z-index:1;padding:68px 20px 56px}}
h1{{font-family:'DM Serif Display',serif;font-size:clamp(2rem,5.5vw,3rem);font-weight:400;font-style:italic;line-height:1.15;margin-bottom:16px;color:#dce8f5}}
.hero p{{color:rgba(220,232,245,.48);max-width:400px;margin:0 auto 32px;font-size:.93rem;font-weight:300;line-height:1.85}}
.cta{{display:inline-flex;align-items:center;gap:8px;padding:14px 32px;border-radius:6px;background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#fff;font-weight:600;font-size:.92rem;cursor:pointer;border:none;transition:opacity .15s,box-shadow .15s;box-shadow:0 4px 20px rgba(59,130,246,.3);font-family:'DM Sans',sans-serif}}
.cl-btn-contact-trigger{{background:linear-gradient(135deg,#1d4ed8,#3b82f6)!important;color:#fff!important;border-radius:6px;padding:15px;box-shadow:0 4px 20px rgba(59,130,246,.3);font-family:'DM Sans',sans-serif}}
.cta:hover{{opacity:.92;box-shadow:0 6px 28px rgba(59,130,246,.45)}}
.cta-o{{display:flex;align-items:center;justify-content:center;width:100%;padding:14px;border-radius:6px;background:transparent;border:1px solid rgba(59,130,246,.28);color:#93c5fd;font-weight:600;font-size:.92rem;cursor:pointer;transition:background .15s;font-family:'DM Sans',sans-serif}}
.cta-o:hover{{background:rgba(59,130,246,.07)}}
.sec{{padding:36px 0 8px}}.sec-t{{font-family:'DM Serif Display',serif;font-size:1.05rem;font-style:italic;color:#93c5fd;margin-bottom:16px}}
.utp{{display:flex;flex-direction:column;gap:8px;margin-bottom:28px}}
.utp-i{{background:rgba(59,130,246,.05);border:1px solid rgba(59,130,246,.14);border-radius:8px;padding:14px 20px;font-size:.91rem;color:#b8d0ef}}
.desc{{background:rgba(59,130,246,.06);border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;padding:18px 22px;font-size:.88rem;line-height:1.8;color:rgba(220,232,245,.7);margin-bottom:28px}}
.media{{display:flex;gap:12px;margin-bottom:28px}}
.media-btn{{flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:8px;font-weight:600;font-size:.87rem;cursor:pointer;border:1px solid rgba(59,130,246,.22);background:rgba(59,130,246,.07);color:#93c5fd;transition:background .15s;font-family:'DM Sans',sans-serif}}
.media-btn:hover{{background:rgba(59,130,246,.14)}}
.rates{{display:flex;flex-direction:column;gap:8px;margin-bottom:24px}}
.rate{{display:flex;justify-content:space-between;align-items:center;background:rgba(255,255,255,.03);border:1px solid rgba(59,130,246,.11);border-radius:8px;padding:15px 22px;font-size:.93rem}}
.rate-p{{font-family:'DM Serif Display',serif;font-size:1.2rem;color:#93c5fd}}
.info{{background:rgba(59,130,246,.04);border:1px solid rgba(59,130,246,.1);border-radius:8px;padding:20px 22px;margin-bottom:28px;display:flex;flex-direction:column;gap:12px}}
.info-i{{font-size:.87rem;line-height:1.75;color:rgba(220,232,245,.6)}}
.divider{{border:none;border-top:1px solid rgba(59,130,246,.09);margin:10px 0 28px}}
.book{{text-align:center;font-size:.9rem;color:rgba(220,232,245,.33);padding:16px 0 28px;border-top:1px solid rgba(59,130,246,.09)}}
.contact{{text-align:center;padding:8px 0 68px;scroll-margin-top:20px}}
.contact-t{{font-family:'DM Serif Display',serif;font-size:1.6rem;font-style:italic;margin-bottom:28px;color:#dce8f5}}
.btns{{display:flex;flex-direction:column;gap:10px;margin-bottom:14px}}
.cl-btn{{border-radius:8px;font-family:'DM Sans',sans-serif}}
.call-tog{{width:100%;display:flex;align-items:center;justify-content:center;gap:10px;padding:14px;border-radius:8px;background:transparent;border:1px solid rgba(220,232,245,.14);color:#dce8f5;font-weight:600;font-size:.92rem;cursor:pointer;transition:background .15s;font-family:'DM Sans',sans-serif;margin-top:4px}}
.call-tog:hover{{background:rgba(255,255,255,.04)}}.call-tog.open{{border-color:rgba(59,130,246,.4);color:#93c5fd}}
</style></head><body>
<div class="topbar">{T["top_bar"]}</div>
<div class="hero"><div class="hero-in">
  <h1>{T["hero_title"]}</h1><p>{T["hero_sub"]}</p>
  <button class="cta" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
</div></div>
<div class="w">
  <div class="sec"><div class="sec-t">{T["sec_included"]}</div>
  <div class="utp"><div class="utp-i">{T["utp_1"]}</div><div class="utp-i">{T["utp_2"]}</div><div class="utp-i">{T["utp_3"]}</div></div></div>
  <div class="desc">{T["desc_box"]}</div>
  <div class="sec" style="padding-bottom:0"><div class="sec-t">{T["media_title"]}</div></div>
  <div class="media">{_media_buttons(T)}</div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_rates"]}</div>
  <div class="rates"><div class="rate"><span>{T["rate_1_dur"]}</span><span class="rate-p">{T["rate_1_price"]}</span></div><div class="rate"><span>{T["rate_2_dur"]}</span><span class="rate-p">{T["rate_2_price"]}</span></div><div class="rate"><span>{T["rate_3_dur"]}</span><span class="rate-p">{T["rate_3_price"]}</span></div></div></div>
  <button class="cta-o" style="margin-bottom:28px" onclick="document.getElementById('ca').scrollIntoView({{behavior:'smooth'}})">{T["btn_contact"]}</button>
  <hr class="divider">
  <div class="sec"><div class="sec-t">{T["sec_info"]}</div>
  <div class="info"><div class="info-i">{T["info_1"]}</div><div class="info-i">{T["info_2"]}</div><div class="info-i">{T["info_3"]}</div></div></div>
  <div class="book">{T["book_msg"]}</div>
  <div class="contact" id="ca">
    <div class="contact-t">{T["sec_contact"]}</div>
    <div class="btns">{bt}</div>
  </div>
</div>{sh}</body></html>"""
