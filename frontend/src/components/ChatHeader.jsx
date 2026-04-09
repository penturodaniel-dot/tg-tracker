import React, { useState, useEffect, useRef } from 'react'
import { closeConv, reopenConv, deleteConv, sendLead, fetchUserStatus } from '../api.js'

function useOnlineStatus(tgUserId) {
  const [status, setStatus] = useState(null) // null | 'online' | 'recently' | string
  const timerRef = useRef(null)

  useEffect(() => {
    if (!tgUserId) { setStatus(null); return }

    const fetch = async () => {
      try {
        const data = await fetchUserStatus(tgUserId)
        if (data.ok) setStatus(data.status || null)
      } catch { /* ignore */ }
    }

    fetch()
    timerRef.current = setInterval(fetch, 60000)
    return () => clearInterval(timerRef.current)
  }, [tgUserId])

  return status
}

function StatusDot({ status }) {
  if (!status) return null
  const isOnline = status === 'online'
  const isRecent = status === 'recently'
  const color = isOnline ? '#22c55e' : isRecent ? '#f97316' : '#4b5675'
  const label = isOnline ? 'онлайн' : isRecent ? 'был недавно' : status

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, color }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: color, display: 'inline-block', flexShrink: 0
      }} />
      {label}
    </span>
  )
}

export default function ChatHeader({ conv, onUpdate, onDeleted }) {
  const [busy, setBusy] = useState(false)
  const [leadSentLocal, setLeadSentLocal] = useState(false)
  const onlineStatus = useOnlineStatus(conv?.tg_user_id)

  // Sync local lead state when conv changes
  useEffect(() => { setLeadSentLocal(false) }, [conv?.id])

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

  const isOpen    = conv.status === 'open'
  const leadSent  = !!conv.fb_event_sent || leadSentLocal
  const appUrl    = window.location.origin

  return (
    <div className="chat-header">
      <div className="chat-header-left">
        {/* Avatar */}
        {conv.photo_url
          ? <img src={conv.photo_url} className="chat-avatar" alt="" />
          : <div className="chat-avatar-placeholder">
              {(conv.visitor_name || '?')[0].toUpperCase()}
            </div>
        }

        <div className="chat-header-info">
          {/* Name row */}
          <div className="chat-header-name">
            <span>{conv.visitor_name || 'Без имени'}</span>
            <StatusDot status={onlineStatus} />
            <span className={`status-badge ${conv.status}`}>
              {isOpen ? 'Открыт' : 'Закрыт'}
            </span>
          </div>

          {/* Sub row: username · phone · utm */}
          <div className="chat-header-sub">
            {conv.username && (
              <a href={`https://t.me/${conv.username.replace('@','')}`}
                 target="_blank" rel="noopener noreferrer"
                 style={{ color: 'var(--blue)' }}>
                {conv.username}
              </a>
            )}
            {conv.phone && <span>{conv.phone}</span>}
            {conv.utm_campaign && (
              <span style={{ color: 'var(--text3)', fontSize: 11 }}>
                {conv.utm_campaign}{conv.utm_source ? ` · ${conv.utm_source}` : ''}
              </span>
            )}
          </div>

          {/* Tags */}
          {conv.tags && conv.tags.length > 0 && (
            <div className="chat-header-tags">
              {conv.tags.map(tag => (
                <span key={tag.id} className="tag-badge"
                  style={{ background: tag.color + '22', color: tag.color, borderColor: tag.color + '55' }}>
                  #{tag.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="chat-header-actions">
        {/* Open in TG */}
        {conv.tg_user_id && (
          <a href={`tg://user?id=${conv.tg_user_id}`}
             className="btn btn-gray btn-sm" title="Открыть в Telegram">
            📱 TG
          </a>
        )}

        {/* Lead button */}
        <button
          className={`btn ${leadSent ? 'btn-green' : 'btn-orange'} btn-sm`}
          disabled={leadSent || busy}
          title={leadSent ? 'Lead уже отправлен' : 'Отправить Lead в Facebook/TikTok'}
          onClick={() => handleAction(async () => {
            await sendLead(conv.id)
            setLeadSentLocal(true)
          })}
        >
          {leadSent ? '✅ Lead ✓' : 'Lead'}
        </button>

        {/* Close / Reopen */}
        {isOpen ? (
          <button className="btn btn-gray btn-sm" disabled={busy}
            onClick={() => handleAction(() => closeConv(conv.id))}>
            Закрыть
          </button>
        ) : (
          <button className="btn btn-gray btn-sm" disabled={busy}
            onClick={() => handleAction(() => reopenConv(conv.id))}>
            Открыть
          </button>
        )}

        {/* Delete */}
        <button className="btn btn-red btn-sm" disabled={busy}
          onClick={() => {
            if (window.confirm('Удалить диалог? Это нельзя отменить.')) {
              handleAction(async () => {
                await deleteConv(conv.id)
                onDeleted(conv.id)
              })
            }
          }}>
          🗑
        </button>
      </div>
    </div>
  )
}
