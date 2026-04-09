import React from 'react'

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

export default function MessageBubble({ message, readMaxId }) {
  const isManager = message.sender_type === 'manager'
  const isPending = !!message._pending

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

  return (
    <div className={`msg-wrapper ${isManager ? 'manager' : 'user'}${isPending ? ' msg-pending' : ''}`}>
      <div className={`msg-bubble ${isManager ? 'manager' : 'user'}`}>
        {/* Sender name for manager messages */}
        {isManager && message.sender_name && (
          <div className="msg-sender-name">{message.sender_name}</div>
        )}

        {/* Media */}
        {mediaContent}

        {/* Text content (hidden if placeholder and media present) */}
        {showText && (
          <div className="msg-content">{message.content}</div>
        )}

        {/* Meta: time + read receipt */}
        <div className="msg-meta">
          <span className="msg-time">{formatMsgTime(message.created_at)}</span>
          {isPending && <span className="msg-read" style={{ opacity: 0.4 }}>⏳</span>}
          {readReceipt}
        </div>
      </div>
    </div>
  )
}
