import { useState, useEffect, useCallback } from 'react'
import { fetchConv } from '../api.js'

/**
 * Fetches and caches a single conversation object.
 * Re-fetches whenever convId changes.
 * Exposes a `refresh` function for after mutations (close/reopen/lead).
 */
export function useConv(convId) {
  const [conv, setConv] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async (id) => {
    if (!id) {
      setConv(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await fetchConv(id)
      setConv(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(convId)
  }, [convId, load])

  const refresh = useCallback(() => load(convId), [convId, load])

  return { conv, setConv, loading, error, refresh }
}
