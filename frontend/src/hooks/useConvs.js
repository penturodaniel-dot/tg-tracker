import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchConvs } from '../api.js'

const POLL_INTERVAL = 5000

/**
 * Manages the conversation list with:
 *  - status tab filtering (open / closed / all)
 *  - client-side search
 *  - infinite scroll (offset-based)
 *  - polling every 5 seconds
 */
export function useConvs() {
  const [status, setStatus] = useState('open')
  const [search, setSearch] = useState('')
  const [convs, setConvs] = useState([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const offsetRef = useRef(0)
  const statusRef = useRef(status)

  // Keep refs in sync so interval callbacks see current values
  useEffect(() => { statusRef.current = status }, [status])
  useEffect(() => { offsetRef.current = offset }, [offset])

  // Load first page (or refresh)
  const loadInitial = useCallback(async (st) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchConvs(st, 0)
      setConvs(data.convs || [])
      setHasMore(data.has_more || false)
      setOffset(data.convs?.length || 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  // Re-load when status changes
  useEffect(() => {
    loadInitial(status)
  }, [status, loadInitial])

  // Silent poll: merge new data at the top without resetting scroll
  const pollConvs = useCallback(async () => {
    try {
      const data = await fetchConvs(statusRef.current, 0)
      const incoming = data.convs || []
      setConvs(prev => {
        // Build a map of existing convs by id for O(1) lookup
        const existingMap = new Map(prev.map(c => [c.id, c]))
        // Merge: replace or add incoming convs
        incoming.forEach(c => existingMap.set(c.id, c))
        // Rebuild list: incoming first (preserves new ordering), then any
        // existing convs that weren't in incoming (loaded via load-more)
        const incomingIds = new Set(incoming.map(c => c.id))
        const extras = prev.filter(c => !incomingIds.has(c.id))
        return [...incoming, ...extras]
      })
      setHasMore(data.has_more || false)
    } catch {
      // silently ignore poll errors
    }
  }, [])

  // Polling interval
  useEffect(() => {
    const id = setInterval(pollConvs, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [pollConvs])

  // Load more (infinite scroll)
  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return
    setLoading(true)
    try {
      const data = await fetchConvs(statusRef.current, offsetRef.current)
      const incoming = data.convs || []
      setConvs(prev => {
        const ids = new Set(prev.map(c => c.id))
        const newOnes = incoming.filter(c => !ids.has(c.id))
        return [...prev, ...newOnes]
      })
      setHasMore(data.has_more || false)
      setOffset(o => o + incoming.length)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [loading, hasMore])

  // Client-side filtered list
  const filtered = search.trim()
    ? convs.filter(c => {
        const q = search.toLowerCase()
        return (
          (c.visitor_name || '').toLowerCase().includes(q) ||
          (c.username || '').toLowerCase().includes(q)
        )
      })
    : convs

  return {
    convs: filtered,
    status,
    setStatus,
    search,
    setSearch,
    loading,
    error,
    hasMore: hasMore && !search.trim(),
    loadMore,
  }
}
