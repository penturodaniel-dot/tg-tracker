import React, { useState, useRef, useCallback } from 'react'
import { sendMessage, sendMedia } from '../api.js'

// SVG icons (inline, no external deps)
function PaperclipIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

const MAX_ROWS = 5
const LINE_HEIGHT = 21 // px

export default function SendBar({ convId, onOptimisticSend, textareaRef: externalRef }) {
  const [text, setText] = useState('')
  const [file, setFile] = useState(null)
  const [sending, setSending] = useState(false)
  const fileInputRef = useRef(null)
  const internalRef = useRef(null)
  const textareaRef = externalRef || internalRef

  // Auto-resize textarea
  const autoResize = useCallback((el) => {
    if (!el) return
    el.style.height = 'auto'
    const maxH = LINE_HEIGHT * MAX_ROWS + 16 // padding
    el.style.height = Math.min(el.scrollHeight, maxH) + 'px'
  }, [])

  const handleChange = (e) => {
    setText(e.target.value)
    autoResize(e.target)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSend = async () => {
    if (sending) return
    if (file) {
      await handleSendFile()
      return
    }
    const trimmed = text.trim()
    if (!trimmed) return
    setSending(true)
    const snapshot = trimmed
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
    if (onOptimisticSend) onOptimisticSend(snapshot)
    try {
      await sendMessage(convId, snapshot)
    } catch (e) {
      // restore text if send fails
      setText(snapshot)
      alert('Ошибка отправки: ' + e.message)
    } finally {
      setSending(false)
    }
  }

  const handleSendFile = async () => {
    if (!file || sending) return
    setSending(true)
    const f = file
    setFile(null)
    try {
      await sendMedia(convId, f)
    } catch (e) {
      setFile(f)
      alert('Ошибка отправки файла: ' + e.message)
    } finally {
      setSending(false)
    }
  }

  const handleFileChange = (e) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
    e.target.value = ''
  }

  const canSend = !sending && (text.trim().length > 0 || file)

  return (
    <div className="send-bar">
      <div className="send-bar-inner">
        {file && (
          <div className="file-preview">
            <span>📎</span>
            <span className="file-preview-name">{file.name}</span>
            <span style={{ color: 'var(--text3)', fontSize: '11px' }}>
              ({(file.size / 1024).toFixed(1)} KB)
            </span>
            <button
              className="file-preview-clear"
              onClick={() => setFile(null)}
              title="Убрать файл"
            >
              ✕
            </button>
          </div>
        )}
        <textarea
          ref={textareaRef}
          className="send-textarea"
          placeholder="Написать сообщение... (Enter = отправить)"
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={sending}
        />
      </div>

      <div className="send-bar-actions">
        <button
          className="icon-btn"
          title="Прикрепить файл"
          onClick={() => fileInputRef.current?.click()}
          disabled={sending}
        >
          <PaperclipIcon />
        </button>
        <button
          className={`icon-btn send`}
          title="Отправить (Enter)"
          onClick={handleSend}
          disabled={!canSend}
        >
          <SendIcon />
        </button>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
    </div>
  )
}
