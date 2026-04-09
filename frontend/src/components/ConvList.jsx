import React, { useRef, useCallback } from 'react'
import ConvItem from './ConvItem.jsx'

const TABS = [
  { value: 'open',   label: 'Открытые' },
  { value: 'closed', label: 'Закрытые' },
  { value: 'all',    label: 'Все' },
]

export default function ConvList({
  convs,
  status,
  setStatus,
  search,
  setSearch,
  loading,
  hasMore,
  loadMore,
  selectedId,
  onSelect,
}) {
  const scrollRef = useRef(null)

  // Infinite scroll: detect near-bottom
  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const { scrollTop, scrollHeight, clientHeight } = el
    if (scrollHeight - scrollTop - clientHeight < 80 && hasMore && !loading) {
      loadMore()
    }
  }, [hasMore, loading, loadMore])

  return (
    <div className="conv-list-panel">
      <div className="conv-list-header">
        <div className="conv-list-title">Диалоги</div>
        <div className="status-tabs">
          {TABS.map(tab => (
            <button
              key={tab.value}
              className={`status-tab${status === tab.value ? ' active' : ''}`}
              onClick={() => setStatus(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <input
          type="search"
          className="search-input"
          placeholder="Поиск..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="conv-list-scroll" ref={scrollRef} onScroll={handleScroll}>
        {loading && convs.length === 0 ? (
          <div className="loading-center" style={{ padding: '32px 0' }}>
            <div className="spinner" />
          </div>
        ) : convs.length === 0 ? (
          <div style={{ color: 'var(--text3)', textAlign: 'center', padding: '32px 12px', fontSize: '13px' }}>
            {search ? 'Ничего не найдено' : 'Нет диалогов'}
          </div>
        ) : (
          convs.map(conv => (
            <ConvItem
              key={conv.id}
              conv={conv}
              selected={conv.id === selectedId}
              onClick={() => onSelect(conv.id)}
            />
          ))
        )}

        {hasMore && (
          <div className="load-more-trigger">
            {loading ? (
              <div className="spinner" style={{ width: 16, height: 16 }} />
            ) : (
              <button className="load-more-btn" onClick={loadMore}>
                Загрузить ещё
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
