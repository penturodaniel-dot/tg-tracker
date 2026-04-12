import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchConvs } from '../api.js'

const POLL_INTERVAL = 5000

export function useConvs() {
  const [status, setStatus] = useState('open')
  const [search, setSearch] = useState('')
  const [tagFilter, setTagFilter] = useState(null)
  const [categoryFilter, setCategoryFilter] = useState(null)
  const [convs, setConvs] = useState([])
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const offsetRef = useRef(0)
  const statusRef = useRef(status)
  const tagFilterRef = useRef(tagFilter)
  const categoryFilterRef = useRef(categoryFilter)

  useEffect(() => { statusRef.current = status }, [status])
  useEffect(() => { offsetRef.current = offset }, [offset])
  useEffect(() => { tagFilterRef.current = tagFilter }, [tagFilter])
  useEffect(() => { categoryFilterRef.current = categoryFilter }, [categoryFilter])

  const loadInitial = useCallback(async (st, tag, cat) => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchConvs(st, 0, tag, cat)
      setConvs(data.convs || [])
      setHasMore(data.has_more || false)
      setOffset(data.convs?.length || 0)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadInitial(status, tagFilter, categoryFilter)
  }, [status, tagFilter, categoryFilter, loadInitial])

  const pollConvs = useCallback(async () => {
    try {
      const data = await fetchConvs(statusRef.current, 0, tagFilterRef.current, categoryFilterRef.current)
      const incoming = data.convs || []
      setConvs(prev => {
        const existingMap = new Map(prev.map(c => [c.id, c]))
        incoming.forEach(c => existingMap.set(c.id, c))
        const incomingIds = new Set(incoming.map(c => c.id))
        const extras = prev.filter(c => !incomingIds.has(c.id))
        return [...incoming, ...extras]
      })
      setHasMore(data.has_more || false)
    } catch {
      // silently ignore poll errors
    }
  }, [])

  useEffect(() => {
    const id = setInterval(pollConvs, POLL_INTERVAL)
    return () => clearInterval(id)
  }, [pollConvs])

  const loadMore = useCallback(async () => {
    if (loading || !hasMore) return
    setLoading(true)
    try {
      const data = await fetchConvs(statusRef.current, offsetRef.current, tagFilterRef.current, categoryFilterRef.current)
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

  const filtered = search.trim()
    ? convs.filter(c => {
        const q = search.toLowerCase()
        return (
          (c.visitor_name || '').toLowerCase().includes(q) ||
          (c.username || '').toLowerCase().includes(q)
        )
      })
    : convs

  const removeConv = useCallback((id) => {
    setConvs(prev => prev.filter(c => c.id !== id))
  }, [])

  return {
    convs: filtered,
    status, setStatus,
    search, setSearch,
    tagFilter, setTagFilter,
    categoryFilter, setCategoryFilter,
    loading, error,
    hasMore: hasMore && !search.trim(),
    loadMore,
    removeConv,
  }
}
