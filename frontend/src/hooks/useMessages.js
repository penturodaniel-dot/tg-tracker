import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchMessages, markRead, deleteMessage, editMessage } from '../api.js'

// Normalize content for dedup: handles \r\n vs \n differences from FormData
function normContent(s) {
  return typeof s === 'string' ? s.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim() : ''
}

const POLL_INTERVAL = 1500

/**
 * Manages messages for a conversation:
 * - Initial full load
 * - Incremental poll every 1500ms (skips when tab hidden)
 * - Deduplication: matches pending by content+sender, removes exactly ONE per real message
 * - readMaxId: tracked in ref + state so receipts always update
 * - markRead: called on open and when new user messages arrive
 */
export function useMessages(convId) {
  const [messages, setMessages] = useState([])
  const [readMaxId, setReadMaxId] = useState(0)
  const [loading, setLoading] = useState(false)

  const lastIdRef   = useRef(0)
  const convIdRef   = useRef(convId)
  const readMaxRef  = useRef(0)
  const pendingMap  = useRef(new Map()) // tempId → content (for dedup)
  const pollCountRef = useRef(0)        // every 10 polls do a full re-fetch for is_read updates

  useEffect(() => { convIdRef.current = convId }, [convId])

  const updateReadMax = useCallback((val) => {
    if (val > readMaxRef.current) {
      readMaxRef.current = val
      setReadMaxId(val)
    }
  }, [])

  // ── Initial load ────────────────────────────────────────────────────────────
  const loadInitial = useCallback(async (id) => {
    if (!id) {
      setMessages([])
      setReadMaxId(0)
      readMaxRef.current = 0
      lastIdRef.current = 0
      pendingMap.current.clear()
      return
    }
    setLoading(true)
    try {
      const data = await fetchMessages(id, 0)
      const msgs = data.messages || []
      setMessages(msgs)
      const rmax = data.read_max_id || 0
      readMaxRef.current = rmax
      setReadMaxId(rmax)
      lastIdRef.current = msgs.length ? Math.max(...msgs.map(m => m.id)) : 0
      // Mark as read when opening the chat
      if (id) markRead(id).catch(() => {})
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    pendingMap.current.clear()
    loadInitial(convId)
  }, [convId, loadInitial])

  // ── Incremental poll ────────────────────────────────────────────────────────
  const poll = useCallback(async () => {
    const id = convIdRef.current
    if (!id || document.hidden) return
    pollCountRef.current += 1
    // Every 10 polls (~15s): full re-fetch to pick up is_read changes
    const isFullRefresh = pollCountRef.current % 10 === 0
    try {
      const data = await fetchMessages(id, isFullRefresh ? 0 : lastIdRef.current)
      const incoming = data.messages || []

      // Always update readMaxId
      if (data.read_max_id !== undefined) {
        updateReadMax(data.read_max_id)
      }

      if (incoming.length === 0) return

      // Mark as read if new user messages arrived
      const hasNewUserMsgs = incoming.some(m => m.sender_type !== 'manager')
      if (hasNewUserMsgs) markRead(id).catch(() => {})

      if (isFullRefresh) {
        // Replace real messages with fresh data; dedup pending against incoming
        setMessages(prev => {
          let pending = prev.filter(m => m._pending)
          for (const realMsg of incoming) {
            if (realMsg.sender_type !== 'manager') continue
            const idx = pending.findIndex(m => normContent(m.content) === normContent(realMsg.content))
            if (idx !== -1) pending = [...pending.slice(0, idx), ...pending.slice(idx + 1)]
          }
          return [...incoming, ...pending]
        })
      } else {
        setMessages(prev => {
          const existingIds = new Set(prev.filter(m => typeof m.id === 'number' && m.id > 0).map(m => m.id))
          const newReal = incoming.filter(m => !existingIds.has(m.id))
          if (newReal.length === 0) return prev

          // Dedup: for each real manager message, remove exactly ONE matching pending
          let result = [...prev]
          for (const realMsg of newReal) {
            if (realMsg.sender_type !== 'manager') continue
            const idx = result.findIndex(
              m => m._pending && normContent(m.content) === normContent(realMsg.content)
            )
            if (idx !== -1) {
              result = [...result.slice(0, idx), ...result.slice(idx + 1)]
            }
          }

          return [...result, ...newReal]
        })
      }

      const maxIncoming = Math.max(...incoming.map(m => m.id))
      if (maxIncoming > lastIdRef.current) lastIdRef.current = maxIncoming

    } catch {
      // silently ignore poll errors
    }
  }, [updateReadMax])

  useEffect(() => {
    if (!convId) return
    const id = setInterval(poll, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [convId, poll])

  // ── Optimistic add ──────────────────────────────────────────────────────────
  const addOptimistic = useCallback((text, senderName) => {
    const tempId = `pending_${Date.now()}`
    pendingMap.current.set(tempId, text)
    const msg = {
      id: tempId,
      _pending: true,
      conversation_id: convIdRef.current,
      sender_type: 'manager',
      sender_name: senderName || 'Менеджер',
      content: text,
      media_url: null,
      media_type: null,
      created_at: new Date().toISOString(),
      is_read: false,
    }
    setMessages(prev => [...prev, msg])
    return tempId
  }, [])

  const deleteMsg = useCallback(async (msgId) => {
    setMessages(prev => prev.filter(m => m.id !== msgId))
    try {
      await deleteMessage(msgId)
    } catch {
      // re-fetch on failure
      loadInitial(convIdRef.current)
    }
  }, [loadInitial])

  const editMsg = useCallback(async (msgId, text) => {
    setMessages(prev => prev.map(m => m.id === msgId ? { ...m, content: text } : m))
    try {
      await editMessage(msgId, text)
    } catch {
      loadInitial(convIdRef.current)
    }
  }, [loadInitial])

  const refresh = useCallback(() => { poll() }, [poll])

  return { messages, readMaxId, loading, addOptimistic, deleteMsg, editMsg, refresh }
}
