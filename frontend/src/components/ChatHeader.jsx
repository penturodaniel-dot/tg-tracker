import React, { useState, useEffect, useRef } from 'react'
import { closeConv, reopenConv, deleteConv, sendLead, fetchUserStatus, addConvTag, removeConvTag, fetchAllTags } from '../api.js'

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

function TagDropdown({ convId, convTags, onAdded }) {
  const [allTags, setAllTags] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    fetchAllTags()
      .then(data => setAllTags(data.tags || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const existingIds = new Set((convTags || []).map(t => t.id))
  const available = allTags.filter(t => !existingIds.has(t.id))

  async function handleAdd(tagId) {
    if (busy) return
    setBusy(true)
    try {
      await addConvTag(convId, tagId)
      onAdded()
    } catch (e) {
      alert('Ошибка: ' + e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tag-add-dropdown" ref={ref}>
      {loading && <div className="tag-add-dropdown-empty">Загрузка...</div>}
      {!loading && available.length === 0 && (
        <div className="tag-add-dropdown-empty">Все теги добавлены</div>
      )}
      {!loading && available.map(tag => (
        <button
          key={tag.id}
          className="tag-add-dropdown-item"
          disabled={busy}
          onClick={() => handleAdd(tag.id)}
        >
          <span style={{
            display: 'inline-block',
            width: 8, height: 8,
            borderRadius: '50%',
            background: tag.color || '#888',
            marginRight: 6,
          }} />
          {tag.name}
        </button>
      ))}
    </div>
  )
}

export default function ChatHeader({ conv, onUpdate, onDeleted }) {
  const [busy, setBusy] = useState(false)
  const [leadSentLocal, setLeadSentLocal] = useState(false)
  const [showTagDropdown, setShowTagDropdown] = useState(false)
  const tagDropdownRef = useRef(null)
  const tagBtnRef = useRef(null)
  const onlineStatus = useOnlineStatus(conv?.tg_user_id)

  // Sync local lead state when conv changes
  useEffect(() => { setLeadSentLocal(false) }, [conv?.id])

  // Close dropdown on outside click
  useEffect(() => {
    if (!showTagDropdown) return
    function handleClick(e) {
      if (
        tagDropdownRef.current && !tagDropdownRef.current.contains(e.target) &&
        tagBtnRef.current && !tagBtnRef.current.contains(e.target)
      ) {
        setShowTagDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showTagDropdown])

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

  async function handleRemoveTag(tagId) {
    try {
      await removeConvTag(conv.id, tagId)
      onUpdate()
    } catch (e) {
      alert('Ошибка: ' + e.message)
    }
  }

  const isOpen    = conv.status === 'open'
  const leadSent  = !!conv.fb_event_sent || leadSentLocal

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

          {/* Sub row: username · phone · utm · «В базе» */}
          <div className="chat-header-sub">
            {conv.username && (
              <a href={`https://t.me/${conv.username.replace('@','')}`}
                 target="_blank" rel="noopener noreferrer"
                 style={{ color: 'var(--blue)' }}>
                {conv.username}
              </a>
            )}
            {conv.phone && <span>{conv.phone}</span>}
            {(conv.utm_campaign || conv.utm_source) && (
              <span style={{ color: 'var(--text3)', fontSize: 11, opacity: 0.8 }}>
                {[conv.utm_campaign, conv.utm_source, conv.utm_content, conv.utm_term]
                  .filter(Boolean).join(' · ')}
              </span>
            )}
            {conv.staff_id ? (
              <a
                href={`/staff?edit=${conv.staff_id}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  background: '#052e16', color: '#86efac',
                  border: '1px solid #166534', borderRadius: 6,
                  padding: '2px 8px', fontSize: 11, textDecoration: 'none',
                }}
              >
                ✅ В базе · {conv.staff_name || 'Карточка'} →
              </a>
            ) : (
              <a
                href={`/staff/create_from_tga?conv_id=${conv.id}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  background: 'var(--bg3)', color: 'var(--text3)',
                  border: '1px solid var(--border)', borderRadius: 6,
                  padding: '2px 8px', fontSize: 11, textDecoration: 'none',
                }}
              >
                + Создать карточку
              </a>
            )}
          </div>

          {/* Tags */}
          <div className="chat-header-tags" style={{ position: 'relative' }}>
            {(conv.tags || []).map(tag => (
              <span key={tag.id} className="tag-badge"
                style={{
                  background: tag.color + '22', color: tag.color,
                  borderColor: tag.color + '55',
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                }}>
                #{tag.name}
                <button
                  onClick={() => handleRemoveTag(tag.id)}
                  title="Удалить тег"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: tag.color, opacity: 0.7, padding: 0, fontSize: 11,
                    lineHeight: 1, display: 'inline-flex', alignItems: 'center',
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '0.7'}
                >
                  ✕
                </button>
              </span>
            ))}

            {/* Add tag button */}
            <div style={{ position: 'relative', display: 'inline-block' }}>
              <button
                ref={tagBtnRef}
                className="tag-badge"
                onClick={() => setShowTagDropdown(v => !v)}
                style={{
                  background: 'var(--bg3)', color: 'var(--text3)',
                  borderColor: 'var(--border2)', cursor: 'pointer',
                  border: '1px dashed var(--border2)',
                }}
              >
                + Тег
              </button>
              {showTagDropdown && (
                <div ref={tagDropdownRef}>
                  <TagDropdown
                    convId={conv.id}
                    convTags={conv.tags}
                    onAdded={() => { setShowTagDropdown(false); onUpdate() }}
                  />
                </div>
              )}
            </div>
          </div>
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
