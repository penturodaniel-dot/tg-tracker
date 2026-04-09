import React, { useState } from 'react'
import { closeConv, reopenConv, deleteConv, sendLead } from '../api.js'

export default function ChatHeader({ conv, onUpdate, onDeleted }) {
  const [busy, setBusy] = useState(false)

  if (!conv) return null

  async function handleAction(fn) {
    if (busy) return
    setBusy(true)
    try {
      await fn()
      onUpdate()
    } catch (e) {
      alert('Ошибка: ' + e.message)
    } finally {
      setBusy(false)
    }
  }

  const isOpen = conv.status === 'open'
  const leadSent = !!conv.fb_event_sent

  return (
    <div className="chat-header">
      <div className="chat-header-info">
        {/* Name + status badge */}
        <div className="chat-header-name">
          <span>{conv.visitor_name || 'Без имени'}</span>
          <span className={`status-badge ${conv.status}`}>
            {isOpen ? 'Открыт' : 'Закрыт'}
          </span>
        </div>

        {/* Username / phone */}
        <div className="chat-header-sub">
          {conv.username && <span>{conv.username}</span>}
          {conv.phone && (
            <>
              {conv.username && <span style={{ color: 'var(--border2)' }}>·</span>}
              <span>{conv.phone}</span>
            </>
          )}
          {conv.utm_campaign && (
            <span style={{ color: 'var(--text3)', fontSize: '11px' }}>
              utm: {conv.utm_campaign}
              {conv.utm_source ? ` / ${conv.utm_source}` : ''}
            </span>
          )}
        </div>

        {/* Tags */}
        {conv.tags && conv.tags.length > 0 && (
          <div className="chat-header-tags">
            {conv.tags.map(tag => (
              <span
                key={tag.id}
                className="tag-badge"
                style={{
                  background: tag.color + '22',
                  color: tag.color,
                  borderColor: tag.color + '55',
                }}
              >
                {tag.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="chat-header-actions">
        <button
          className="btn btn-orange"
          disabled={leadSent || busy}
          title={leadSent ? 'Lead уже отправлен' : 'Отправить Lead в Facebook'}
          onClick={() => handleAction(() => sendLead(conv.id))}
        >
          {leadSent ? 'Lead ✓' : 'Lead'}
        </button>

        {isOpen ? (
          <button
            className="btn btn-gray"
            disabled={busy}
            onClick={() => handleAction(() => closeConv(conv.id))}
          >
            Закрыть
          </button>
        ) : (
          <button
            className="btn btn-gray"
            disabled={busy}
            onClick={() => handleAction(() => reopenConv(conv.id))}
          >
            Открыть
          </button>
        )}

        <button
          className="btn btn-red"
          disabled={busy}
          onClick={() => {
            if (window.confirm('Удалить диалог? Это действие нельзя отменить.')) {
              handleAction(async () => {
                await deleteConv(conv.id)
                onDeleted(conv.id)
              })
            }
          }}
        >
          Удалить
        </button>
      </div>
    </div>
  )
}
