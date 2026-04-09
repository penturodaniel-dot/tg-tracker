import React from 'react'

function formatTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diffDays = Math.floor((now - d) / 86400000)
  if (diffDays === 0) {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }
  if (diffDays < 7) {
    return d.toLocaleDateString('ru-RU', { weekday: 'short' })
  }
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })
}

function getInitials(name) {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

// Deterministic hue from a string
function nameToHue(name) {
  let h = 0
  for (let i = 0; i < (name || '').length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff
  return h % 360
}

export default function ConvItem({ conv, selected, onClick }) {
  const initials = getInitials(conv.visitor_name)
  const hue = nameToHue(conv.visitor_name)

  return (
    <div
      className={`conv-item${selected ? ' selected' : ''}`}
      onClick={onClick}
    >
      {/* Avatar */}
      <div
        className="conv-avatar"
        style={
          conv.photo_url
            ? undefined
            : { background: `hsl(${hue},35%,25%)`, color: `hsl(${hue},70%,75%)`, borderColor: `hsl(${hue},35%,30%)` }
        }
      >
        {conv.photo_url ? (
          <img src={conv.photo_url} alt={initials} />
        ) : (
          initials
        )}
      </div>

      {/* Body */}
      <div className="conv-item-body">
        <div className="conv-item-row1">
          <span className="conv-item-name">{conv.visitor_name || 'Без имени'}</span>
          <span className="conv-item-time">{formatTime(conv.last_message_at)}</span>
        </div>

        <div className="conv-item-row2">
          <span className="conv-item-last">
            {conv.last_message || '\u00a0'}
          </span>
          {conv.unread_count > 0 && (
            <span className="unread-badge">{conv.unread_count > 99 ? '99+' : conv.unread_count}</span>
          )}
        </div>

        {/* Mini badges */}
        {(conv.utm_campaign || conv.fbclid || conv.fb_event_sent || conv.in_staff) && (
          <div className="conv-item-badges">
            {conv.utm_campaign && (
              <span className="badge-utm" title={`Кампания: ${conv.utm_campaign}`}>
                {conv.utm_campaign}
              </span>
            )}
            {/* Traffic source: TT / FB / org */}
            {(conv.utm_source || '').toLowerCase().match(/tiktok|^tt$/) ? (
              <span className="badge-src badge-src-tt">TT</span>
            ) : conv.fbclid || (conv.utm_source || '').toLowerCase().match(/facebook|^fb$/) ? (
              <span className="badge-src badge-src-fb">fb ✓</span>
            ) : conv.utm_campaign ? (
              <span className="badge-src badge-src-org">org</span>
            ) : null}
            {conv.in_staff && (
              <span className="badge-instaff">в базе</span>
            )}
            {conv.fb_event_sent && (
              <span className="badge-lead">Lead ✓</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
