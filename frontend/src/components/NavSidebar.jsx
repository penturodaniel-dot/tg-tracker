import React, { useState, useEffect } from 'react'

const NAV_SECTIONS = [
  {
    id: 'clients',
    label: 'Клиенты',
    items: [
      { icon: '📡', label: 'Каналы',          href: '/channels' },
      { icon: '🔗', label: 'Кампании',        href: '/campaigns' },
      { icon: '📣', label: 'Автопостинг',     href: '/autopost' },
      { icon: '📝', label: 'Шаблоны постов',  href: '/autopost/templates' },
      { icon: '🎨', label: 'Шаблоны',         href: '/landings' },
      { icon: '📈', label: 'Статистика',      href: '/analytics/clients' },
    ]
  },
  {
    id: 'staff',
    label: 'Сотрудники',
    items: [
      { icon: '📱', label: 'TG Чаты',      href: '/tg_account/chat', active: true },
      { icon: '💚', label: 'WA Чаты',      href: '/wa/chat' },
      { icon: '🗂',  label: 'База',          href: '/staff' },
      { icon: '💰', label: 'Бонусы',       href: '/staff/bonuses' },
      { icon: '📝', label: 'Скрипты',      href: '/scripts' },
      { icon: '🌐', label: 'Лендинги HR',  href: '/landings_staff' },
      { icon: '📊', label: 'Статистика',   href: '/analytics/staff' },
    ]
  },
  {
    id: 'settings',
    label: 'Настройки',
    items: [
      { icon: '🏷️', label: 'Теги',          href: '/tags' },
      { icon: '🔐', label: 'Пользователи',  href: '/users' },
      { icon: '🎯', label: 'Проекты',       href: '/projects' },
      { icon: '⚙️', label: 'Настройки',    href: '/settings' },
    ]
  },
]

const STORAGE_KEY = 'nav_expanded'

export default function NavSidebar() {
  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === '1' } catch { return false }
  })

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, expanded ? '1' : '0') } catch {}
  }, [expanded])

  return (
    <div className={`nav-sidebar ${expanded ? 'nav-sidebar--open' : ''}`}>
      {/* Toggle button */}
      <button
        className="nav-toggle"
        onClick={() => setExpanded(v => !v)}
        title={expanded ? 'Свернуть меню' : 'Развернуть меню'}
      >
        {expanded ? '✕' : '☰'}
      </button>

      {/* Logo (only when expanded) */}
      {expanded && (
        <div className="nav-logo">
          <div className="nav-logo-brand">📡 TGTracker</div>
        </div>
      )}

      {/* Sections */}
      {NAV_SECTIONS.map(section => (
        <div key={section.id} className="nav-section">
          {expanded && (
            <div className="nav-section-label">{section.label}</div>
          )}
          {section.items.map(item => (
            <a
              key={item.href}
              href={item.href}
              className={`nav-link ${item.active ? 'nav-link--active' : ''}`}
              title={!expanded ? item.label : undefined}
            >
              <span className="nav-link-icon">{item.icon}</span>
              {expanded && <span className="nav-link-text">{item.label}</span>}
            </a>
          ))}
        </div>
      ))}
    </div>
  )
}
