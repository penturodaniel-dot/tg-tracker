"""
seo_templates_jobs.py
SEO-модуль: альтернативный шаблон «jobs_landing» для HR-сайтов
(работа массажисткой в США, типа choiseforyoutoday.com).

Отличия от default:
- Шрифты Montserrat (заголовки) + Open Sans (текст), не Inter/Playfair
- Pink/magenta gradient брендинг с CSS-токенами
- Полная landing-страница с hero, about, benefits, requirements,
  how-it-works, offers, FAQ, CTA banner — структура хардкод, тексты
  i18n по site.language (ru/ua/en).
- Hero и banner картинки из site.hero_image_url / site.secondary_image_url
  (если не заданы — рендерим только градиенты)
- Telegram CTA через site.telegram_url

Только render_seo_home_jobs здесь. Статьи / блог-индекс / локации /
страницы — рендерятся default-шаблоном из seo_templates.py чтобы
не дублировать SEO-обвязку и Schema.
"""
import html as _html
import json as _json
from datetime import datetime

from seo_templates import (
    _esc, _site_url, _adjust_color, _schema_organization,
    _schema_website,
)


# ── i18n ─────────────────────────────────────────────────────────────────────

T = {
    "ru": {
        "hero.title": "РАБОТА МАССАЖИСТКОЙ",
        "hero.tag": "в США",
        "hero.subtitle": "Свяжитесь с нами и начните зарабатывать деньги прямо сейчас!",
        "hero.salary": "от $500 в день",
        "hero.spa": "Элитный СПА",
        "tg.button": "Связаться в Телеграм",
        "about.tagline": "Увлекательная карьера и большие заработки",
        "about.title": "Большие заработки для",
        "about.titleHighlight": "Массажисток",
        "about.p1": "Работа массажисткой в США — уникальный шанс построить успешную карьеру в индустрии красоты и здоровья. Практика показывает: каждая массажистка может зарабатывать от $1500 в день. Главное — желание развиваться.",
        "about.p2": "С таким доходом осуществите свои мечты: купите машину, квартиру, помогите близким, запустите собственный бизнес. Вы начнёте зарабатывать с первого дня и сразу почувствуете разницу в качестве жизни.",
        "about.banner.title": "Начни зарабатывать уже сегодня",
        "about.banner.desc": "Присоединяйся к нашей команде и получай стабильный доход с первого дня работы.",
        "benefits.title": "Почему стоит начать работать с нами",
        "benefits.1.title": "Работайте анонимно",
        "benefits.1.desc": "Ваши личные данные защищены. Мы гарантируем полную конфиденциальность всем нашим специалистам.",
        "benefits.2.title": "Работайте когда хотите",
        "benefits.2.desc": "Гибкий график позволяет совмещать работу с образованием и личной жизнью.",
        "benefits.3.title": "Безопасность",
        "benefits.3.desc": "Все клиенты проходят тщательную проверку. Ваша безопасность — наш приоритет.",
        "benefits.4.title": "Оплата каждый день",
        "benefits.4.desc": "Оплата происходит перед каждой процедурой, поэтому вы сразу получаете свой доход и полностью контролируете свой заработок.",
        "benefits.5.title": "Обучение и поддержка",
        "benefits.5.desc": "Если у вас нет опыта — это не проблема. Мы предоставляем обучение для будущих массажисток. На протяжении всей работы вам доступна поддержка. Администратор всегда на связи.",
        "benefits.6.title": "Комфортное жильё",
        "benefits.6.desc": "На время сотрудничества мы предоставляем комфортное проживание. Также предусмотрена возможность смены локации в разных городах по территории США.",
        "req.title1": "Требования к",
        "req.title2": "кандидаткам",
        "req.intro": "Вы нам подойдёте, если вы:",
        "req.1": "имеете опыт работы или готовы обучаться с нуля",
        "req.2": "ответственны и дисциплинированы",
        "req.3": "коммуникабельны и ориентированы на клиента",
        "req.4": "ухожены и придерживаетесь аккуратного внешнего вида",
        "req.5": "готовы соблюдать стандарты сервиса",
        "how.title": "Как начать",
        "how.titleHighlight": "работать",
        "how.step1.title": "Переходите в телеграм",
        "how.step1.desc": "С вами на связи будет наш HR специалист.",
        "how.step2.title": "Уточняете детали",
        "how.step2.desc": "Наш HR-специалист подробно отвечает на все ваши вопросы.",
        "how.step3.title": "Заполняете анкету",
        "how.step3.desc": "От вас потребуется минимум информации:\n• имя и возраст\n• ваше текущее местонахождение в США\n• номер телефона или Telegram для связи\n• одно фото в полный рост (используется только для предварительного рассмотрения)",
        "how.cta": "Начните сегодня и уже завтра вы будете радоваться стабильному заработку!",
        "offers.title": "Что предоставляет",
        "offers.titleHighlight": "вам компания",
        "offers.1": "Комфортное жильё на время работы",
        "offers.2": "Материалы необходимые для массажа",
        "offers.3": "Стабильный поток клиентов",
        "offers.4": "Круглосуточная поддержка по всем вопросам",
        "cta.main": "Хочешь зарабатывать от $30 000 в месяц без лишней суеты и забот?",
        "cta.sub": "Заполняй анкету и меняй свою жизнь.",
        "footer.desc": "Мы поможем вам адаптироваться и закрыть все финансовые вопросы. Если у вас остались какие-либо вопросы, пишите нашему менеджеру, он поможет вам и ответит на все вопросы.",
        "footer.contacts": "Контакты",
        "footer.address": "Вся территория США",
        "footer.rights": "Все права защищены.",
        "nav.benefits": "Преимущества",
        "nav.requirements": "Требования",
        "nav.howToStart": "Как начать",
        "nav.faq": "FAQ",
        "nav.blog": "Блог",
    },
    "ua": {
        "hero.title": "РОБОТА МАСАЖИСТКОЮ",
        "hero.tag": "в США",
        "hero.subtitle": "Зв'яжіться з нами і почніть заробляти гроші прямо зараз!",
        "hero.salary": "від $500 на день",
        "hero.spa": "Елітний СПА",
        "tg.button": "Зв'язатися в Телеграм",
        "about.tagline": "Захоплива кар'єра та великі заробітки",
        "about.title": "Великі заробітки для",
        "about.titleHighlight": "Масажисток",
        "about.p1": "Робота масажисткою в США — унікальний шанс побудувати успішну кар'єру в індустрії краси та здоров'я. Практика показує: кожна масажистка може заробляти від $1500 на день. Головне — бажання розвиватися.",
        "about.p2": "З таким доходом здійсніть свої мрії: купіть машину, квартиру, допоможіть близьким, запустіть власний бізнес. Ви почнете заробляти з першого дня і одразу відчуєте різницю в якості життя.",
        "about.banner.title": "Почни заробляти вже сьогодні",
        "about.banner.desc": "Приєднуйся до нашої команди та отримуй стабільний дохід з першого дня роботи.",
        "benefits.title": "Чому варто почати працювати з нами",
        "benefits.1.title": "Працюйте анонімно",
        "benefits.1.desc": "Ваші особисті дані захищені. Ми гарантуємо повну конфіденційність усім нашим спеціалістам.",
        "benefits.2.title": "Працюйте коли хочете",
        "benefits.2.desc": "Гнучкий графік дозволяє поєднувати роботу з освітою та особистим життям.",
        "benefits.3.title": "Безпека",
        "benefits.3.desc": "Усі клієнти проходять ретельну перевірку. Ваша безпека — наш пріоритет.",
        "benefits.4.title": "Оплата щодня",
        "benefits.4.desc": "Оплата відбувається перед кожною процедурою, тому ви одразу отримуєте свій дохід і повністю контролюєте свій заробіток.",
        "benefits.5.title": "Навчання та підтримка",
        "benefits.5.desc": "Якщо у вас немає досвіду — це не проблема. Ми надаємо навчання для майбутніх масажисток. Протягом усієї роботи вам доступна підтримка. Адміністратор завжди на зв'язку.",
        "benefits.6.title": "Комфортне житло",
        "benefits.6.desc": "На час співпраці ми надаємо комфортне проживання. Також передбачена можливість зміни локації в різних містах на території США.",
        "req.title1": "Вимоги до",
        "req.title2": "кандидаток",
        "req.intro": "Ви нам підійдете, якщо ви:",
        "req.1": "маєте досвід роботи або готові навчатися з нуля",
        "req.2": "відповідальні та дисципліновані",
        "req.3": "комунікабельні та орієнтовані на клієнта",
        "req.4": "доглянуті та дотримуєтесь акуратного зовнішнього вигляду",
        "req.5": "готові дотримуватися стандартів сервісу",
        "how.title": "Як почати",
        "how.titleHighlight": "працювати",
        "how.step1.title": "Переходьте в телеграм",
        "how.step1.desc": "З вами на зв'язку буде наш HR спеціаліст.",
        "how.step2.title": "Уточнюєте деталі",
        "how.step2.desc": "Наш HR-спеціаліст детально відповідає на всі ваші запитання.",
        "how.step3.title": "Заповнюєте анкету",
        "how.step3.desc": "Від вас потрібен мінімум інформації:\n• ім'я та вік\n• ваше поточне місцезнаходження в США\n• номер телефону або Telegram для зв'язку\n• одне фото на повний зріст (використовується лише для попереднього розгляду)",
        "how.cta": "Почніть сьогодні і вже завтра ви будете радіти стабільному заробітку!",
        "offers.title": "Що надає",
        "offers.titleHighlight": "вам компанія",
        "offers.1": "Комфортне житло на час роботи",
        "offers.2": "Матеріали необхідні для масажу",
        "offers.3": "Стабільний потік клієнтів",
        "offers.4": "Цілодобова підтримка з усіх питань",
        "cta.main": "Хочеш заробляти від $30 000 на місяць без зайвого клопоту?",
        "cta.sub": "Заповнюй анкету і змінюй своє життя.",
        "footer.desc": "Ми допоможемо вам адаптуватися та закрити всі фінансові питання. Якщо у вас залишились будь-які питання, пишіть нашому менеджеру, він допоможе вам і відповість на всі питання.",
        "footer.contacts": "Контакти",
        "footer.address": "Вся територія США",
        "footer.rights": "Всі права захищені.",
        "nav.benefits": "Переваги",
        "nav.requirements": "Вимоги",
        "nav.howToStart": "Як почати",
        "nav.faq": "FAQ",
        "nav.blog": "Блог",
    },
    "en": {
        "hero.title": "WORK AS A MASSEUSE",
        "hero.tag": "IN THE USA",
        "hero.subtitle": "Contact us and start earning money right now!",
        "hero.salary": "from $500 per day",
        "hero.spa": "Elite SPA",
        "tg.button": "Contact via Telegram",
        "about.tagline": "Exciting career and big earnings",
        "about.title": "Big earnings for",
        "about.titleHighlight": "Masseuses",
        "about.p1": "Working as a masseuse in the USA is a unique chance to build a successful career in the beauty and health industry. Practice shows: every masseuse can earn from $1500 per day. The main thing is the desire to grow.",
        "about.p2": "With this income, make your dreams come true: buy a car, apartment, help your loved ones, start your own business. You'll start earning from day one and immediately feel the difference in quality of life.",
        "about.banner.title": "Start earning today",
        "about.banner.desc": "Join our team and receive stable income from your first day of work.",
        "benefits.title": "Why you should start working with us",
        "benefits.1.title": "Work anonymously",
        "benefits.1.desc": "Your personal data is protected. We guarantee complete confidentiality to all our specialists.",
        "benefits.2.title": "Work when you want",
        "benefits.2.desc": "Flexible schedule allows you to combine work with education and personal life.",
        "benefits.3.title": "Safety",
        "benefits.3.desc": "All clients are thoroughly vetted. Your safety is our priority.",
        "benefits.4.title": "Daily payment",
        "benefits.4.desc": "Payment happens before each procedure, so you immediately receive your income and fully control your earnings.",
        "benefits.5.title": "Training and support",
        "benefits.5.desc": "No experience? No problem. We provide training for future masseuses. Support is available throughout your work. The administrator is always in touch.",
        "benefits.6.title": "Comfortable housing provided",
        "benefits.6.desc": "During cooperation, we provide comfortable accommodation. There is also an option to change location in different cities across the USA.",
        "req.title1": "Requirements for",
        "req.title2": "candidates",
        "req.intro": "You are a good fit if you:",
        "req.1": "have work experience or are ready to learn from scratch",
        "req.2": "responsible and disciplined",
        "req.3": "sociable and client-oriented",
        "req.4": "well-groomed and maintain a neat appearance",
        "req.5": "ready to follow service standards",
        "how.title": "How to start",
        "how.titleHighlight": "working",
        "how.step1.title": "Go to Telegram",
        "how.step1.desc": "Our HR specialist will be in touch with you.",
        "how.step2.title": "Clarify details",
        "how.step2.desc": "Our HR specialist answers all your questions in detail.",
        "how.step3.title": "Fill out the form",
        "how.step3.desc": "We need minimal information:\n• name and age\n• your current location in the USA\n• phone number or Telegram\n• one full-length photo (used only for preliminary review)",
        "how.cta": "Start today and tomorrow you'll be enjoying stable earnings!",
        "offers.title": "What the company",
        "offers.titleHighlight": "provides you",
        "offers.1": "Comfortable housing during work",
        "offers.2": "Materials needed for massage",
        "offers.3": "Stable flow of clients",
        "offers.4": "24/7 support on all matters",
        "cta.main": "Want to earn from $30,000/month without hassle?",
        "cta.sub": "Fill out the form and change your life.",
        "footer.desc": "We will help you adapt and resolve all financial matters. If you have any questions, write to our manager.",
        "footer.contacts": "Contacts",
        "footer.address": "All across the USA",
        "footer.rights": "All rights reserved.",
        "nav.benefits": "Benefits",
        "nav.requirements": "Requirements",
        "nav.howToStart": "How to start",
        "nav.faq": "FAQ",
        "nav.blog": "Blog",
    },
}


def _t(site: dict, key: str) -> str:
    lang = site.get("language") or "ru"
    return T.get(lang, T["ru"]).get(key, T["ru"].get(key, key))


# ── CSS ──────────────────────────────────────────────────────────────────────

_JOBS_CSS = """
:root{--primary:__PRIMARY__;--primary-2:__PRIMARY_2__;--primary-3:__PRIMARY_3__;--secondary:__SECONDARY__;--bg:#FFFFFF;--surface:#FDF7FB;--text:#1A1620;--muted:#6B6471;--border:#F0E5EC;--card:#FFFFFF;--gradient-primary:linear-gradient(135deg,__PRIMARY__,__PRIMARY_2__,__PRIMARY_3__);--gradient-hero:linear-gradient(135deg,#FBE5F2,#F2E0EF,#FDE6F1);--gradient-section:linear-gradient(180deg,#FDF7FB,#FFFFFF);--gradient-card:linear-gradient(180deg,#FDF7FB,#FFFFFF);--shadow-card:0 8px 30px -8px rgba(218,39,189,.12);--shadow-elevated:0 20px 50px -12px rgba(218,39,189,.20);--radius:18px}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Open Sans',-apple-system,BlinkMacSystemFont,sans-serif;color:var(--text);background:var(--bg);line-height:1.7;-webkit-font-smoothing:antialiased}
h1,h2,h3,h4,h5,h6{font-family:'Montserrat',sans-serif;font-weight:800;line-height:1.2;color:var(--text)}
h1{font-size:clamp(2rem,5vw,4rem);font-weight:900;letter-spacing:-0.02em;margin-bottom:1rem}
h2{font-size:clamp(1.7rem,3.5vw,2.5rem);margin:0 0 1rem;font-weight:900;letter-spacing:-0.01em}
h3{font-size:1.25rem;margin:0 0 .8rem;font-weight:700}
p{margin-bottom:1rem;color:var(--text)}
a{color:var(--primary);text-decoration:none;transition:opacity .2s}
a:hover{opacity:.85}
img{max-width:100%;height:auto;display:block}
.container{max-width:1180px;margin:0 auto;padding:0 24px}
.gradient-text{background:var(--gradient-primary);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.gradient-bg{background:var(--gradient-primary);color:#fff}
.gradient-card{background:var(--gradient-card)}
.gradient-hero{background:var(--gradient-hero)}
.gradient-section{background:var(--gradient-section)}
.btn{display:inline-flex;align-items:center;gap:8px;padding:14px 28px;border-radius:999px;font-weight:700;font-family:'Montserrat',sans-serif;font-size:1rem;border:none;cursor:pointer;transition:all .25s;text-decoration:none}
.btn-primary{background:var(--gradient-primary);color:#fff;box-shadow:var(--shadow-card)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:var(--shadow-elevated);opacity:1}
.btn-inverted{background:#fff;color:var(--primary)}
.btn-inverted:hover{transform:translateY(-2px)}
header.site-header{background:rgba(255,255,255,.92);backdrop-filter:blur(8px);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50;padding:14px 0}
.nav{display:flex;align-items:center;justify-content:space-between;gap:24px}
.brand{font-family:'Montserrat',sans-serif;font-size:1.5rem;font-weight:900;letter-spacing:-0.01em}
.brand a{color:var(--primary)}
.nav-links{display:flex;gap:24px;list-style:none}
.nav-links a{color:var(--text);font-weight:600;font-size:.92rem}
.nav-links a:hover{color:var(--primary)}
@media(max-width:900px){.nav-links{display:none}}
section{padding:80px 0}
.hero{padding:100px 0 80px;background:var(--gradient-hero);position:relative;overflow:hidden}
.hero-grid{display:grid;grid-template-columns:1fr 1fr;gap:48px;align-items:center}
@media(max-width:900px){.hero-grid{grid-template-columns:1fr}.hero{padding:60px 0 40px}}
.hero-tag{display:inline-block;background:var(--gradient-primary);color:#fff;padding:6px 24px;border-radius:999px;font-weight:700;font-size:1rem;margin:0 0 24px;font-family:'Montserrat',sans-serif}
.hero p.lead{font-size:1.2rem;color:var(--muted);max-width:560px;margin-bottom:2rem}
.hero-image-wrap{position:relative;width:100%;max-width:480px;aspect-ratio:1;margin:0 auto}
.hero-image-wrap .glow{position:absolute;inset:0;border-radius:50%;background:var(--gradient-primary);opacity:.25;filter:blur(60px)}
.hero-image-wrap .circle{position:absolute;inset:0;border-radius:50%;overflow:hidden;box-shadow:var(--shadow-elevated);background:var(--gradient-primary)}
.hero-image-wrap .circle img{width:100%;height:100%;object-fit:cover}
.hero-image-wrap .circle::after{content:"";position:absolute;inset:0;background:linear-gradient(135deg,rgba(244,32,155,.4),rgba(218,39,189,.35))}
.hero-image-wrap .person{position:absolute;bottom:0;left:50%;transform:translateX(-50%);height:90%;width:auto;z-index:2}
.hero-badge{position:absolute;bottom:32px;left:-16px;background:#fff;border-radius:18px;padding:10px 16px;box-shadow:var(--shadow-card);font-family:'Montserrat',sans-serif;font-weight:800;font-size:.85rem;display:flex;align-items:center;gap:8px;z-index:3}
.section-title-wrap{text-align:center;margin-bottom:48px}
.tagline{display:inline-block;color:var(--primary);font-weight:600;font-size:.92rem;margin-bottom:8px;font-family:'Montserrat',sans-serif;letter-spacing:.04em;text-transform:uppercase}
.about-card{background:var(--gradient-card);border-radius:32px;padding:48px;box-shadow:var(--shadow-card);max-width:880px;margin:0 auto;position:relative;overflow:hidden}
.about-card .icon-bg{position:absolute;top:16px;right:16px;font-size:6rem;opacity:.08}
.about-card p{font-size:1.1rem;color:var(--muted);line-height:1.75;margin-bottom:1.2rem}
.divider{width:80px;height:3px;background:var(--gradient-primary);margin:1.5rem auto;border-radius:3px}
.banner{position:relative;border-radius:32px;overflow:hidden;box-shadow:var(--shadow-elevated);margin-top:48px;max-width:880px;margin-left:auto;margin-right:auto}
.banner img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.banner-inner{position:relative;background:linear-gradient(135deg,rgba(244,32,155,.85),rgba(218,39,189,.85),rgba(195,46,219,.85));padding:60px 32px;text-align:center;color:#fff}
.banner-inner h3{color:#fff;font-size:clamp(1.5rem,3vw,2rem);margin-bottom:1rem}
.banner-inner p{color:rgba(255,255,255,.95);max-width:540px;margin:0 auto 2rem;font-size:1rem}
.benefits-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;max-width:1080px;margin:0 auto}
@media(max-width:900px){.benefits-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:600px){.benefits-grid{grid-template-columns:1fr}}
.benefit-card{background:var(--gradient-card);border-radius:28px;padding:28px;box-shadow:var(--shadow-card);transition:all .3s}
.benefit-card:hover{transform:translateY(-4px);box-shadow:var(--shadow-elevated)}
.benefit-icon{width:56px;height:56px;border-radius:18px;background:var(--gradient-primary);display:flex;align-items:center;justify-content:center;margin-bottom:18px;color:#fff;font-size:1.5rem;font-weight:900}
.benefit-card h3{margin-bottom:10px}
.benefit-card .div-mini{width:42px;height:2px;background:var(--gradient-primary);margin:0 0 12px;border-radius:2px}
.benefit-card p{color:var(--muted);font-size:.95rem;line-height:1.65;margin:0}
.req-grid{display:grid;grid-template-columns:1fr 1fr;gap:64px;align-items:center;max-width:1080px;margin:0 auto}
@media(max-width:900px){.req-grid{grid-template-columns:1fr}}
.req-list{list-style:none;margin-bottom:2rem}
.req-list li{display:flex;gap:14px;align-items:flex-start;margin-bottom:14px;font-size:1.02rem}
.req-list li::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--gradient-primary);margin-top:8px;flex-shrink:0}
.steps-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px;max-width:1080px;margin-left:auto;margin-right:auto}
.step-card-full{max-width:1080px;margin:0 auto}
@media(max-width:700px){.steps-grid{grid-template-columns:1fr}}
.step-card{background:var(--gradient-card);border-radius:28px;padding:28px;box-shadow:var(--shadow-card);position:relative;transition:all .3s}
.step-card:hover{transform:translateY(-4px);box-shadow:var(--shadow-elevated)}
.step-num{position:absolute;top:18px;right:24px;font-family:'Montserrat',sans-serif;font-size:3.5rem;font-weight:900;color:rgba(218,39,189,.10);line-height:1}
.step-icon{width:56px;height:56px;border-radius:18px;background:var(--gradient-primary);display:flex;align-items:center;justify-content:center;margin-bottom:18px;color:#fff;font-size:1.4rem}
.step-card p{color:var(--muted);font-size:.95rem;white-space:pre-line;line-height:1.65;margin:0}
.offers-card{max-width:720px;margin:0 auto;background:var(--gradient-card);border-radius:32px;padding:48px;box-shadow:var(--shadow-card)}
.offers-list{list-style:none}
.offers-list li{display:flex;gap:18px;align-items:center;padding:14px 0}
.offers-list li:not(:last-child){border-bottom:1px solid var(--border)}
.offers-icon{width:48px;height:48px;border-radius:14px;background:var(--gradient-primary);display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.2rem;flex-shrink:0}
.offers-list span{font-size:1.05rem;font-weight:600}
.cta-section{padding:80px 0;text-align:center}
.cta-card{background:var(--gradient-primary);color:#fff;border-radius:32px;padding:60px 32px;max-width:920px;margin:0 auto;box-shadow:var(--shadow-elevated)}
.cta-card h2{color:#fff;margin-bottom:1rem}
.cta-card p{color:rgba(255,255,255,.95);font-size:1.1rem;margin-bottom:2rem}
footer.site-footer{background:#1A1620;color:#D4CFD7;padding:60px 0 30px}
footer.site-footer h4{color:#fff;font-size:1.05rem;margin-bottom:14px}
footer.site-footer .columns{display:grid;grid-template-columns:2fr 1fr 1fr;gap:48px;margin-bottom:40px}
@media(max-width:700px){footer.site-footer .columns{grid-template-columns:1fr}}
footer.site-footer .brand-foot{font-family:'Montserrat',sans-serif;font-weight:900;font-size:1.6rem;color:#fff;margin-bottom:18px}
footer.site-footer p{color:#D4CFD7;font-size:.92rem;line-height:1.65}
footer.site-footer ul{list-style:none}
footer.site-footer li{padding:5px 0}
footer.site-footer a{color:#D4CFD7;font-weight:500;font-size:.92rem}
footer.site-footer a:hover{color:#fff}
footer.site-footer .copy{text-align:center;font-size:.85rem;color:#7A727F;border-top:1px solid #2D2832;padding-top:24px}
"""


def _build_jobs_css(site: dict) -> str:
    p = site.get("color_primary") or "#DA27BD"
    s = site.get("color_secondary") or "#F4209B"
    return (_JOBS_CSS
            .replace("__PRIMARY__", p)
            .replace("__PRIMARY_2__", _adjust_color(p, -10))
            .replace("__PRIMARY_3__", _adjust_color(p, +20))
            .replace("__SECONDARY__", s))


# ── Head/Header/Footer (свой head с Montserrat) ──────────────────────────────

def _render_jobs_head(site: dict, *, title: str, description: str = "",
                       canonical: str = "", og_image: str = "",
                       og_type: str = "website", schema_jsons=None,
                       extra_head: str = "") -> str:
    title_full = title + (site.get("title_suffix") or "")
    desc = description or site.get("default_meta_description") or ""
    image = og_image or site.get("default_og_image") or ""
    favicon = site.get("favicon_url") or ""
    lang = site.get("language") or "ru"
    brand = site.get("brand_name") or site.get("name") or ""
    custom_header = site.get("header_html") or ""

    schema_blocks = ""
    for s in (schema_jsons or []):
        if isinstance(s, str) and s.strip():
            schema_blocks += f'\n<script type="application/ld+json">{s}</script>'
        elif isinstance(s, (dict, list)):
            schema_blocks += f'\n<script type="application/ld+json">{_json.dumps(s, ensure_ascii=False)}</script>'

    ga = ""
    if site.get("ga_id"):
        gid = _esc(site["ga_id"])
        ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
              f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}'
              f"gtag('js',new Date());gtag('config','{gid}');</script>")
    fbp = ""
    if site.get("fb_pixel_id"):
        pix = _esc(site["fb_pixel_id"])
        fbp = (f"<script>!function(f,b,e,v,n,t,s){{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?n.callMethod.apply(n,arguments):n.queue.push(arguments)}};"
               f"if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;"
               f"t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');"
               f"fbq('init','{pix}');fbq('track','PageView');</script>"
               f'<noscript><img height="1" width="1" src="https://www.facebook.com/tr?id={pix}&ev=PageView&noscript=1"/></noscript>')

    parts = [
        '<!DOCTYPE html>',
        f'<html lang="{_esc(lang)}">',
        '<head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>{_esc(title_full)}</title>',
        f'<meta name="description" content="{_esc(desc)}">',
    ]
    if canonical:
        parts.append(f'<link rel="canonical" href="{_esc(canonical)}">')
    parts.append(f'<meta property="og:type" content="{_esc(og_type)}">')
    parts.append(f'<meta property="og:title" content="{_esc(title_full)}">')
    parts.append(f'<meta property="og:description" content="{_esc(desc)}">')
    if canonical:
        parts.append(f'<meta property="og:url" content="{_esc(canonical)}">')
    if image:
        parts.append(f'<meta property="og:image" content="{_esc(image)}">')
    if brand:
        parts.append(f'<meta property="og:site_name" content="{_esc(brand)}">')
    parts.append('<meta name="twitter:card" content="summary_large_image">')
    parts.append(f'<meta name="twitter:title" content="{_esc(title_full)}">')
    parts.append(f'<meta name="twitter:description" content="{_esc(desc)}">')
    if image:
        parts.append(f'<meta name="twitter:image" content="{_esc(image)}">')
    if favicon:
        parts.append(f'<link rel="icon" href="{_esc(favicon)}">')
    parts.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    parts.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    parts.append('<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800;900&family=Open+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">')
    parts.append(f'<style>{_build_jobs_css(site)}</style>')
    if schema_blocks:
        parts.append(schema_blocks)
    if ga:
        parts.append(ga)
    if fbp:
        parts.append(fbp)
    if custom_header:
        parts.append(custom_header)
    if extra_head:
        parts.append(extra_head)
    parts.append('</head><body>')
    return "\n".join(parts)


def _render_jobs_header(site: dict) -> str:
    brand = site.get("brand_name") or site.get("name") or "Site"
    items = [
        ('#about', _t(site, 'about.tagline').split(' и')[0] if site.get('language') == 'ru' else _t(site, 'about.tagline')),
        ('#benefits', _t(site, 'nav.benefits')),
        ('#requirements', _t(site, 'nav.requirements')),
        ('#how', _t(site, 'nav.howToStart')),
        ('#faq', _t(site, 'nav.faq')),
        ('/blog', _t(site, 'nav.blog')),
    ]
    nav_html = "".join(
        f'<li><a href="{_esc(href)}">{_esc(lbl)}</a></li>'
        for href, lbl in items
    )
    return (
        '<header class="site-header"><div class="container nav">'
        f'<div class="brand"><a href="/">{_esc(brand)}</a></div>'
        f'<ul class="nav-links">{nav_html}</ul>'
        '</div></header>'
    )


def _render_jobs_footer(site: dict) -> str:
    brand = site.get("brand_name") or site.get("name") or ""
    org = site.get("org_name") or brand
    year = datetime.utcnow().year
    return (
        '<footer class="site-footer"><div class="container">'
        '<div class="columns">'
        f'<div><div class="brand-foot">{_esc(brand)}</div>'
        f'<p>{_esc(_t(site, "footer.desc"))}</p></div>'
        f'<div><h4>{_esc(_t(site, "nav.howToStart"))}</h4>'
        f'<ul><li><a href="#about">{_esc(_t(site, "about.tagline").split(" и")[0] if site.get("language")=="ru" else _t(site,"about.tagline"))}</a></li>'
        f'<li><a href="#benefits">{_esc(_t(site, "nav.benefits"))}</a></li>'
        f'<li><a href="#requirements">{_esc(_t(site, "nav.requirements"))}</a></li>'
        f'<li><a href="/blog">{_esc(_t(site, "nav.blog"))}</a></li></ul></div>'
        f'<div><h4>{_esc(_t(site, "footer.contacts"))}</h4>'
        f'<p>{_esc(_t(site, "footer.address"))}</p>'
        f'{f"<p><a href=\"{_esc(site.get('telegram_url'))}\" target=\"_blank\" rel=\"noopener\">Telegram</a></p>" if site.get("telegram_url") else ""}'
        f'{f"<p>{_esc(site.get(chr(39)+chr(111)+chr(114)+chr(103)+chr(95)+chr(101)+chr(109)+chr(97)+chr(105)+chr(108)+chr(39)))}</p>" if site.get("org_email") else ""}'
        '</div>'
        '</div>'
        f'<div class="copy">© {year} {_esc(org)}. {_esc(_t(site, "footer.rights"))}</div>'
        '</div></footer></body></html>'
    )


def _tg_btn(site: dict, *, label: str = None, inverted: bool = False) -> str:
    url = site.get("telegram_url") or "#"
    cls = "btn btn-inverted" if inverted else "btn btn-primary"
    label = label or _t(site, "tg.button")
    return f'<a href="{_esc(url)}" target="_blank" rel="noopener" class="{cls}">📨 {_esc(label)}</a>'


# ── Главная (homepage) для jobs_landing ──────────────────────────────────────

def render_seo_home_jobs(site: dict, page: dict, articles: list = None) -> str:
    """Рендер jobs_landing главной. page — это запись из seo_pages типа home
    (берём оттуда title/meta/schema), articles — recent для нижнего блока."""

    title = page.get("title") or _t(site, "hero.title")
    desc = page.get("meta_description") or site.get("default_meta_description") or ""
    canonical = page.get("canonical_url") or _site_url(site, "/")

    # JobPosting / Organization schema
    schemas = []
    if page.get("schema_json"):
        schemas.append(page["schema_json"])
    schemas.append(_schema_organization(site))
    schemas.append(_schema_website(site))

    head = _render_jobs_head(site, title=title, description=desc,
                              canonical=canonical, og_type="website",
                              og_image=page.get("og_image", ""),
                              schema_jsons=schemas)
    header = _render_jobs_header(site)

    hero_img_html = ""
    if site.get("hero_image_url"):
        hero_img_html = (
            f'<div class="hero-image-wrap">'
            f'<div class="glow"></div>'
            f'<div class="circle"></div>'
            f'<img class="person" src="{_esc(site["hero_image_url"])}" alt="{_esc(_t(site, "hero.title"))}" />'
            f'<div class="hero-badge">⭐ {_esc(_t(site, "hero.spa"))}</div>'
            f'</div>'
        )
    hero = (
        '<section class="hero"><div class="container hero-grid">'
        '<div>'
        f'<h1>{_esc(_t(site, "hero.title"))}</h1>'
        f'<div class="hero-tag">{_esc(_t(site, "hero.tag"))}</div>'
        f'<p class="lead">{_esc(_t(site, "hero.subtitle"))}</p>'
        f'{_tg_btn(site)}'
        '</div>'
        f'{hero_img_html}'
        '</div></section>'
    )

    about_inner = (
        '<div class="about-card"><div class="icon-bg">💆</div>'
        f'<p>{_esc(_t(site, "about.p1"))}</p>'
        f'<p>{_esc(_t(site, "about.p2"))}</p>'
        '<div class="divider"></div>'
        f'<div style="text-align:center">{_tg_btn(site)}</div>'
        '</div>'
    )

    banner_img = ""
    if site.get("secondary_image_url"):
        banner_img = f'<img src="{_esc(site["secondary_image_url"])}" alt="" loading="lazy">'
    banner = (
        '<div class="banner">'
        f'{banner_img}'
        '<div class="banner-inner">'
        f'<h3>{_esc(_t(site, "about.banner.title"))}</h3>'
        f'<p>{_esc(_t(site, "about.banner.desc"))}</p>'
        f'{_tg_btn(site, inverted=True)}'
        '</div></div>'
    )

    about = (
        '<section id="about" class="gradient-section"><div class="container">'
        '<div class="section-title-wrap">'
        f'<div class="tagline">{_esc(_t(site, "about.tagline"))}</div>'
        f'<h2>{_esc(_t(site, "about.title"))} <span class="gradient-text">{_esc(_t(site, "about.titleHighlight"))}</span></h2>'
        '</div>'
        f'{about_inner}{banner}'
        '</div></section>'
    )

    # Benefits — 6 cards
    benefit_icons = ["👁", "⏰", "🛡", "$", "🎓", "🏠"]
    bcards = ""
    for i in range(1, 7):
        bcards += (
            '<div class="benefit-card">'
            f'<div class="benefit-icon">{benefit_icons[i-1]}</div>'
            f'<h3>{_esc(_t(site, f"benefits.{i}.title"))}</h3>'
            '<div class="div-mini"></div>'
            f'<p>{_esc(_t(site, f"benefits.{i}.desc"))}</p>'
            '</div>'
        )
    benefits = (
        '<section id="benefits" class="gradient-section"><div class="container">'
        '<div class="section-title-wrap">'
        f'<h2>{_esc(_t(site, "benefits.title"))}</h2>'
        '</div>'
        f'<div class="benefits-grid">{bcards}</div>'
        '</div></section>'
    )

    # Requirements
    req_items = "".join(
        f'<li>{_esc(_t(site, f"req.{i}"))}</li>' for i in range(1, 6)
    )
    req_img_html = ""
    if site.get("hero_image_url"):
        req_img_html = (
            f'<div><div class="hero-image-wrap" style="max-width:380px;aspect-ratio:1">'
            f'<div class="glow"></div>'
            f'<div class="circle"></div>'
            f'<img class="person" src="{_esc(site["hero_image_url"])}" alt="" loading="lazy" />'
            f'</div></div>'
        )
    req = (
        '<section id="requirements"><div class="container">'
        '<div class="req-grid">'
        '<div>'
        f'<h2>{_esc(_t(site, "req.title1"))} <span class="gradient-text">{_esc(_t(site, "req.title2"))}</span></h2>'
        f'<p style="font-size:1.05rem;color:var(--muted);margin-bottom:1.4rem">{_esc(_t(site, "req.intro"))}</p>'
        f'<ul class="req-list">{req_items}</ul>'
        f'{_tg_btn(site)}'
        '</div>'
        f'{req_img_html}'
        '</div></div></section>'
    )

    # How it works — 3 steps
    step_icons = ["📨", "💬", "📋"]
    step_top = ""
    for i in range(1, 3):
        step_top += (
            '<div class="step-card">'
            f'<div class="step-num">{i}</div>'
            f'<div class="step-icon">{step_icons[i-1]}</div>'
            f'<h3>{i}. {_esc(_t(site, f"how.step{i}.title"))}</h3>'
            f'<p>{_esc(_t(site, f"how.step{i}.desc"))}</p>'
            '</div>'
        )
    step3 = (
        '<div class="step-card-full"><div class="step-card">'
        '<div class="step-num">3</div>'
        f'<div class="step-icon">{step_icons[2]}</div>'
        f'<h3>3. {_esc(_t(site, "how.step3.title"))}</h3>'
        f'<p>{_esc(_t(site, "how.step3.desc"))}</p>'
        '</div></div>'
    )
    how = (
        '<section id="how" class="gradient-section"><div class="container">'
        '<div class="section-title-wrap">'
        f'<h2>{_esc(_t(site, "how.title"))} <span class="gradient-text">{_esc(_t(site, "how.titleHighlight"))}</span></h2>'
        '</div>'
        f'<div class="steps-grid">{step_top}</div>'
        f'{step3}'
        f'<div style="text-align:center;margin-top:32px">'
        f'<p style="color:var(--muted);font-size:1.05rem;margin-bottom:1.4rem">{_esc(_t(site, "how.cta"))}</p>'
        f'{_tg_btn(site)}</div>'
        '</div></section>'
    )

    # Company offers
    offer_icons = ["🏠", "🎒", "👥", "🎧"]
    offers_lis = ""
    for i in range(1, 5):
        offers_lis += (
            '<li>'
            f'<div class="offers-icon">{offer_icons[i-1]}</div>'
            f'<span>{_esc(_t(site, f"offers.{i}"))}</span>'
            '</li>'
        )
    offers = (
        '<section><div class="container">'
        '<div class="section-title-wrap">'
        f'<h2>{_esc(_t(site, "offers.title"))} <span class="gradient-text">{_esc(_t(site, "offers.titleHighlight"))}</span></h2>'
        '</div>'
        f'<div class="offers-card"><ul class="offers-list">{offers_lis}</ul></div>'
        '</div></section>'
    )

    # CTA banner
    cta = (
        '<section class="cta-section"><div class="container">'
        '<div class="cta-card">'
        f'<h2>{_esc(_t(site, "cta.main"))}</h2>'
        f'<p>{_esc(_t(site, "cta.sub"))}</p>'
        f'{_tg_btn(site, inverted=True)}'
        '</div></div></section>'
    )

    # Recent articles на главной (если есть)
    blog_html = ""
    if articles:
        cards = ""
        for art in (articles or [])[:3]:
            art_url = "/blog/" + (art.get("slug") or "").lstrip("/")
            bg = f"background-image:url('{_esc(art.get('og_image') or '')}')" if art.get("og_image") else ""
            cards += (
                f'<a href="{_esc(art_url)}" style="display:block;background:#fff;border-radius:24px;overflow:hidden;box-shadow:var(--shadow-card);transition:all .3s;text-decoration:none;color:inherit">'
                f'<div style="aspect-ratio:16/9;{bg};background-size:cover;background-position:center;background-color:#FBE5F2"></div>'
                '<div style="padding:24px">'
                f'<h3 style="margin-bottom:10px;font-size:1.1rem">{_esc(art.get("title", ""))}</h3>'
                f'<p style="color:var(--muted);font-size:.92rem;margin:0">{_esc((art.get("excerpt") or "")[:140])}</p>'
                '</div></a>'
            )
        blog_html = (
            '<section id="blog" class="gradient-section"><div class="container">'
            f'<div class="section-title-wrap"><h2>{_esc(_t(site, "nav.blog"))}</h2></div>'
            f'<div class="benefits-grid">{cards}</div>'
            '</div></section>'
        )

    return head + header + hero + about + benefits + req + how + offers + blog_html + cta + _render_jobs_footer(site)
