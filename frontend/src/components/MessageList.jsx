import React, { useEffect, useRef } from 'react'
import MessageBubble, { DateSeparator, getMessageDate } from './MessageBubble.jsx'

export default function MessageList({ messages, readMaxId, loading, onDeleteMsg, onEditMsg }) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  const prevLengthRef = useRef(0)
  const isInitialRef = useRef(true)

  useEffect(() => {
    if (loading) return
    const len = messages.length
    const prevLen = prevLengthRef.current

    if (isInitialRef.current && len > 0) {
      // First load: scroll to bottom instantly
      bottomRef.current?.scrollIntoView({ behavior: 'instant' })
      isInitialRef.current = false
    } else if (len > prevLen) {
      // New message arrived: check if near bottom before scrolling
      const el = containerRef.current
      if (el) {
        const { scrollTop, scrollHeight, clientHeight } = el
        const distFromBottom = scrollHeight - scrollTop - clientHeight
        if (distFromBottom < 160) {
          bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
        }
      }
    }
    prevLengthRef.current = len
  }, [messages, loading])

  // Reset on conv change (messages cleared to [])
  useEffect(() => {
    if (messages.length === 0) {
      isInitialRef.current = true
      prevLengthRef.current = 0
    }
  }, [messages])

  if (loading && messages.length === 0) {
    return (
      <div className="message-list">
        <div className="loading-center">
          <div className="spinner" />
        </div>
      </div>
    )
  }

  // Insert date separators between messages on different days
  const items = []
  let lastDate = null
  messages.forEach((msg, idx) => {
    const dateKey = getMessageDate(msg.created_at)
    if (dateKey && dateKey !== lastDate) {
      items.push(
        <DateSeparator key={`sep-${dateKey}-${idx}`} dateStr={msg.created_at} />
      )
      lastDate = dateKey
    }
    items.push(
      <MessageBubble key={msg.id} message={msg} readMaxId={readMaxId} onDelete={onDeleteMsg} onEdit={onEditMsg} />
    )
  })

  return (
    <div className="message-list" ref={containerRef}>
      {items.length === 0 ? (
        <div style={{ color: 'var(--text3)', textAlign: 'center', marginTop: '32px', fontSize: '13px' }}>
          Нет сообщений
        </div>
      ) : items}
      <div ref={bottomRef} style={{ height: 1 }} />
    </div>
  )
}
