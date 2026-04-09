import { useEffect, useRef } from 'react'

// Inline base64 short beep (100ms, 440Hz sine wave)
const BEEP_SRC = (() => {
  const sr = 8000, dur = 0.15, freq = 880
  const n = Math.floor(sr * dur)
  const buf = new Uint8Array(44 + n * 2)
  const view = new DataView(buf.buffer)
  const set = (o, v, l) => l === 4 ? view.setUint32(o, v, true) : l === 2 ? view.setUint16(o, v, true) : view.setUint8(o, v)
  // RIFF header
  ;[...('RIFF')].forEach((c, i) => set(i, c.charCodeAt(0), 1))
  set(4,  36 + n * 2, 4) // chunk size
  ;[...('WAVE')].forEach((c, i) => set(8  + i, c.charCodeAt(0), 1))
  ;[...('fmt ')].forEach((c, i) => set(12 + i, c.charCodeAt(0), 1))
  set(16, 16, 4); set(20, 1, 2); set(22, 1, 2)
  set(24, sr, 4); set(28, sr * 2, 4); set(32, 2, 2); set(34, 16, 2)
  ;[...('data')].forEach((c, i) => set(36 + i, c.charCodeAt(0), 1))
  set(40, n * 2, 4)
  for (let i = 0; i < n; i++) {
    const v = Math.round(Math.sin(2 * Math.PI * freq * i / sr) * 8000 * (1 - i / n))
    view.setInt16(44 + i * 2, v, true)
  }
  const b64 = btoa(String.fromCharCode(...buf))
  return `data:audio/wav;base64,${b64}`
})()

function playBeep() {
  try {
    const a = new Audio(BEEP_SRC)
    a.volume = 0.4
    a.play().catch(() => {})
  } catch {}
}

function showBrowserNotification(title, body) {
  if (!('Notification' in window)) return
  if (Notification.permission === 'granted') {
    try {
      new Notification(title, { body, icon: '/favicon.ico', tag: 'tg-new-msg' })
    } catch {}
  } else if (Notification.permission === 'default') {
    Notification.requestPermission()
  }
}

/**
 * Watches convs for new unread messages.
 * - Updates document.title with unread count
 * - Plays beep + shows browser notification when new unread conv appears
 */
export function useNotifications(convs) {
  const prevUnreadRef = useRef(new Map()) // convId → unread_count
  const titleBase = 'TG Чаты'

  useEffect(() => {
    const totalUnread = convs.reduce((s, c) => s + (c.unread_count || 0), 0)
    document.title = totalUnread > 0 ? `(${totalUnread}) ${titleBase}` : titleBase
  }, [convs])

  useEffect(() => {
    const prev = prevUnreadRef.current
    let hasNew = false
    let newSender = ''
    let newText = ''

    for (const conv of convs) {
      const prevCount = prev.get(conv.id) || 0
      const curCount = conv.unread_count || 0
      if (curCount > prevCount) {
        hasNew = true
        newSender = conv.visitor_name || 'Новое сообщение'
        newText = conv.last_message || ''
      }
      prev.set(conv.id, curCount)
    }

    if (hasNew) {
      playBeep()
      if (document.hidden) {
        showBrowserNotification(`💬 ${newSender}`, newText)
      }
    }
  }, [convs])

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission()
    }
  }, [])
}
