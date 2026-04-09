import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchMessages } from '../api.js'

const POLL_INTERVAL = 1500

/**
 * Fetches messages for a conversation and polls for new ones every 1500 ms.
 * Only polls when the document tab is visible.
 *
 * Exposes:
 *  - messages: sorted array
 *  - readMaxId: highest id the server says is read
 *  - loading: initial load in progress
 *  - addOptimistic(msg): insert a pending message immediately
 *  - confirmOptimistic(tempId, serverMsg): replace pending with confirmed
 */
export function useMessages(convId) {
  const [messages, setMessages] = useState([])
  const [readMaxId, setReadMaxId] = useState(0)
  const [loading, setLoading] = useState(false)

  const lastIdRef = useRef(0)
  const convIdRef = useRef(convId)
  const tempIdCounter = useRef(-1)

  useEffect(() => {
    convIdRef.current = convId
  }, [convId])

  // Initial load
  const loadInitial = useCallback(async (id) => {
    if (!id) {
      setMessages([])
      setReadMaxId(0)
      lastIdRef.current = 0
      return
    }
    setLoading(true)
    try {
      const data = await fetchMessages(id, 0)
      const msgs = data.messages || []
      setMessages(msgs)
      setReadMaxId(data.read_max_id || 0)
      lastIdRef.current = msgs.length ? Math.max(...msgs.map(m => m.id)) : 0
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadInitial(convId)
  }, [convId, loadInitial])

  // Incremental poll
  const poll = useCallback(async () => {
    const id = convIdRef.current
    if (!id || document.hidden) return
    try {
      const data = await fetchMessages(id, lastIdRef.current)
      const incoming = data.messages || []
      if (incoming.length > 0) {
        setMessages(prev => {
          const existingIds = new Set(prev.filter(m => m.id > 0).map(m => m.id))
          const newReal = incoming.filter(m => !existingIds.has(m.id))
          if (newReal.length === 0) return prev
          // Remove any optimistic messages whose content matches incoming
          const incomingContents = new Set(newReal.map(m => m.content))
          const withoutOptimistic = prev.filter(
            m => !(m._pending && incomingContents.has(m.content))
          )
          return [...withoutOptimistic, ...newReal]
        })
        const maxIncoming = Math.max(...incoming.map(m => m.id))
        if (maxIncoming > lastIdRef.current) {
          lastIdRef.current = maxIncoming
        }
      }
      if (data.read_max_id !== undefined) {
        setReadMaxId(data.read_max_id)
      }
    } catch {
      // silently ignore
    }
  }, [])

  useEffect(() => {
    if (!convId) return
    const id = setInterval(poll, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [convId, poll])

  // Optimistic add
  const addOptimistic = useCallback((text, senderName) => {
    const tempId = --tempIdCounter.current // negative so never clashes with server ids
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

  return { messages, readMaxId, loading, addOptimistic }
}
