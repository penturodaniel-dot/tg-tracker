import React, { useState, useEffect } from 'react'

// tab= совпадает с tab-id используемым в main.py require_auth(tab=...)
const NAV_SECTIONS = [
  {
    id: 'clients',
    label: 'Клиенты',
    items: [
      { icon: '📡', label: 'Каналы',          href: '/channels',              tab: 'channels' },
      { icon: '🔗', label: 'Кампании',        href: '/campaigns',             tab: 'campaigns' },
      { icon: '📣', label: 'Автопостинг',     href: '/autopost',              tab: 'autopost' },
      { icon: '📝', label: 'Шаблоны постов',  href: '/autopost/templates',    tab: 'autopost_tpl' },
      { icon: '🎨', label: 'Шаблоны',         href: '/landings',              tab: 'landings' },
      { icon: '📈', label: 'Статистика',      href: '/analytics/clients',     tab: 'analytics_clients' },
    ]
  },
  {
    id: 'staff',
    label: 'Сотрудники',
    items: [
      { icon: '📱', label: 'TG Чаты',      href: '/tg_account/chat', tab: 'tg_account_chat', active: true },
      { icon: '💚', label: 'WA Чаты',      href: '/wa/chat',         tab: 'wa_chat' },
      { icon: '🗂',  label: 'База',          href: '/staff',           tab: 'staff' },
      { icon: '💰', label: 'Бонусы',       href: '/staff/bonuses',   tab: 'staff_bonuses' },
      { icon: '📝', label: 'Скрипты',      href: '/scripts',         tab: 'scripts' },
      { icon: '🌐', label: 'Лендинги HR',  href: '/landings_staff',  tab: 'landings_staff' },
      { icon: '📊', label: 'Статистика',   href: '/analytics/staff', tab: 'analytics_staff' },
    ]
  },
  {
    id: 'settings',
    label: 'Настройки',
    adminOnly: true,
    items: [
      { icon: '🏷️', label: 'Теги',          href: '/tags' },
      { icon: '🔐', label: 'Пользователи',  href: '/users' },
      { icon: '🎯', label: 'Проекты',       href: '/projects' },
      { icon: '⚙️', label: 'Настройки',    href: '/settings' },
    ]
  },
]

const STORAGE_KEY = 'nav_expanded'

function canAccessTab(tab) {
  const u = window.__USER
  if (!u || u.role === 'admin') return true
  const perms = (u.permissions || '').split(',').map(p => p.trim()).filter(Boolean)
  return perms.length === 0 || perms.includes(tab)
}

function isAdmin() {
  return window.__USER?.role === 'admin'
}

export default function NavSidebar() {
  const [expanded, setExpanded] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === '1' } catch { return false }
  })

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, expanded ? '1' : '0') } catch {}
  }, [expanded])

  const username = window.__USER?.username || ''

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
      {NAV_SECTIONS.map(section => {
        // Настройки — только для admin
        if (section.adminOnly && !isAdmin()) return null

        // Фильтруем пункты по permissions
        const visibleItems = section.items.filter(item =>
          !item.tab || canAccessTab(item.tab)
        )
        if (visibleItems.length === 0) return null

        return (
          <div key={section.id} className="nav-section">
            {expanded && (
              <div className="nav-section-label">{section.label}</div>
            )}
            {visibleItems.map(item => (
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
        )
      })}

      {/* Logout — прибит к низу */}
      <a
        href="/logout"
        className="nav-link"
        title={!expanded ? 'Выйти' : undefined}
        style={{ marginTop: 'auto', borderTop: '1px solid var(--border)', color: 'var(--text3)', paddingTop: '8px', paddingBottom: '8px', flexShrink: 0 }}
      >
        <span className="nav-link-icon">🚪</span>
        {expanded && (
          <span className="nav-link-text" style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
            <span>Выйти</span>
            {username && <span style={{ fontSize: '10px', opacity: 0.5 }}>{username}</span>}
          </span>
        )}
      </a>
    </div>
  )
}
