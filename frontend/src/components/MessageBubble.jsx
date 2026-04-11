import React, { useState, useRef } from 'react'

function formatMsgTime(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

function formatDateSeparator(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Сегодня'
  if (d.toDateString() === yesterday.toDateString()) return 'Вчера'
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
}

export function getMessageDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr.includes('T') ? dateStr : dateStr.replace(' ', 'T'))
  if (isNaN(d.getTime())) return ''
  return d.toDateString()
}

export function DateSeparator({ dateStr }) {
  return (
    <div className="msg-date-separator">
      {formatDateSeparator(dateStr)}
    </div>
  )
}

export default function MessageBubble({ message, readMaxId, onDelete, onEdit }) {
  const isManager = message.sender_type === 'manager'
  const isPending = !!message._pending
  const [hovered, setHovered] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState('')
  const editRef = useRef(null)

  // Read receipt for manager messages
  let readReceipt = null
  if (isManager && !isPending) {
    const isRead = message.is_read || (readMaxId >= message.id)
    readReceipt = (
      <span className="msg-read" title={isRead ? 'Прочитано' : 'Доставлено'}>
        {isRead ? '✓✓' : '✓'}
      </span>
    )
  }

  // Detect image: by media_type or by URL extension
  function looksLikeImage(url) {
    return /\.(jpe?g|png|gif|webp|bmp|avif)(\?|$)/i.test(url || '')
  }
  const PLACEHOLDER_TEXTS = ['[файл]', '[медиафайл]', '[файл отправляется...]']

  // Media content
  let mediaContent = null
  if (message.media_url) {
    const isImg = (message.media_type && message.media_type.startsWith('image/')) ||
                  looksLikeImage(message.media_url)
    if (isImg) {
      mediaContent = (
        <a href={message.media_url} target="_blank" rel="noopener noreferrer">
          <img
            className="msg-image"
            src={message.media_url}
            alt="изображение"
            onError={e => { e.target.style.display = 'none' }}
          />
        </a>
      )
    } else {
      const fileName = message.media_url.split('/').pop().split('?')[0] || 'файл'
      mediaContent = (
        <a
          className="msg-file-link"
          href={message.media_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span>📎</span>
          <span>{fileName}</span>
        </a>
      )
    }
  }

  // Hide placeholder text when real media is present
  const showText = message.content &&
    !(message.media_url && PLACEHOLDER_TEXTS.includes(message.content))

  function startEdit() {
    setEditText(message.content || '')
    setEditing(true)
    setTimeout(() => {
      if (editRef.current) {
        editRef.current.focus()
        editRef.current.selectionStart = editRef.current.value.length
      }
    }, 0)
  }

  function cancelEdit() {
    setEditing(false)
    setEditText('')
  }

  function submitEdit() {
    const text = editText.trim()
    if (!text || text === message.content) { cancelEdit(); return }
    if (onEdit) onEdit(message.id, text)
    setEditing(false)
    setEditText('')
  }

  function handleEditKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitEdit() }
    if (e.key === 'Escape') cancelEdit()
  }

  const canEdit = isManager && !isPending && !message.media_url && onEdit
  const canDelete = !isPending && onDelete

  // Action buttons (shown on hover, outside the bubble)
  const actions = (canDelete || canEdit) && hovered && !editing && (
    <div
      className="msg-actions"
      style={{
        display: 'flex',
        gap: '2px',
        alignItems: 'center',
        order: isManager ? -1 : 1,
      }}
    >
      {canEdit && (
        <button
          className="msg-action-btn"
          title="Редактировать"
          onClick={startEdit}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '3px 5px',
            borderRadius: '4px',
            fontSize: '13px',
            color: 'var(--text3)',
            lineHeight: 1,
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text3)'}
        >
          ✏️
        </button>
      )}
      {canDelete && (
        <button
          className="msg-action-btn"
          title="Удалить"
          onClick={() => {
            if (window.confirm('Удалить сообщение?')) onDelete(message.id)
          }}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: '3px 5px',
            borderRadius: '4px',
            fontSize: '13px',
            color: 'var(--text3)',
            lineHeight: 1,
          }}
          onMouseEnter={e => e.currentTarget.style.color = '#ef4444'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text3)'}
        >
          🗑
        </button>
      )}
    </div>
  )

  return (
    <div
      className={`msg-wrapper ${isManager ? 'manager' : 'user'}${isPending ? ' msg-pending' : ''}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ alignItems: 'flex-end' }}
    >
      {isManager && actions}

      <div className={`msg-bubble ${isManager ? 'manager' : 'user'}`}>
        {/* Sender name for manager messages */}
        {isManager && message.sender_name && (
          <div className="msg-sender-name">{message.sender_name}</div>
        )}

        {/* Media */}
        {mediaContent}

        {/* Inline edit */}
        {editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <textarea
              ref={editRef}
              value={editText}
              onChange={e => setEditText(e.target.value)}
              onKeyDown={handleEditKeyDown}
              rows={2}
              style={{
                width: '100%',
                minWidth: '180px',
                background: 'rgba(255,255,255,0.07)',
                border: '1px solid rgba(255,255,255,0.2)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '13px',
                padding: '4px 6px',
                resize: 'none',
                fontFamily: 'inherit',
              }}
            />
            <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
              <button
                onClick={cancelEdit}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', fontSize: '11px' }}
              >
                Отмена
              </button>
              <button
                onClick={submitEdit}
                style={{ background: '#3b82f6', border: 'none', cursor: 'pointer', color: '#fff', fontSize: '11px', borderRadius: '4px', padding: '2px 8px' }}
              >
                Сохранить
              </button>
            </div>
          </div>
        ) : (
          /* Text content (hidden if placeholder and media present) */
          showText && (
            <div className="msg-content">{message.content}</div>
          )
        )}

        {/* Meta: time + read receipt */}
        {!editing && (
          <div className="msg-meta">
            <span className="msg-time">{formatMsgTime(message.created_at)}</span>
            {isPending && <span className="msg-read" style={{ opacity: 0.4 }}>⏳</span>}
            {readReceipt}
          </div>
        )}
      </div>

      {!isManager && actions}
    </div>
  )
}
