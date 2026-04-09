import React, { useRef, useCallback, useEffect, useState } from 'react'
import ConvItem from './ConvItem.jsx'
import { fetchAllTags, fetchTgAccountStatus } from '../api.js'

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
  tagFilter,
  setTagFilter,
  loading,
  hasMore,
  loadMore,
  selectedId,
  onSelect,
}) {
  const scrollRef = useRef(null)
  const [tags, setTags] = useState([])
  const [tgStatus, setTgStatus] = useState(null)

  useEffect(() => {
    fetchAllTags()
      .then(data => setTags(data.tags || []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    const load = () => fetchTgAccountStatus().then(setTgStatus).catch(() => {})
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

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
      {tgStatus && (
        <div className={`tg-status-bar ${tgStatus.status === 'connected' ? 'tg-status-ok' : 'tg-status-err'}`}>
          <span className="tg-status-dot" />
          {tgStatus.status === 'connected'
            ? `Подключён · ${tgStatus.phone || ''}`
            : tgStatus.status === 'banned'
              ? 'Аккаунт заблокирован'
              : 'Не подключён · отправка недоступна'}
        </div>
      )}
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
        {tags.length > 0 && (
          <div className="tag-filter-bar">
            <button
              className={`tag-filter-btn${tagFilter === null ? ' active' : ''}`}
              onClick={() => setTagFilter(null)}
            >
              Все
            </button>
            {tags.map(tag => (
              <button
                key={tag.id}
                className={`tag-filter-btn${tagFilter === tag.id ? ' active' : ''}`}
                onClick={() => setTagFilter(tagFilter === tag.id ? null : tag.id)}
                style={tagFilter === tag.id ? {
                  background: tag.color + '33',
                  color: tag.color,
                  borderColor: tag.color + '88',
                } : {}}
              >
                <span style={{
                  display: 'inline-block',
                  width: 7, height: 7,
                  borderRadius: '50%',
                  background: tag.color || '#888',
                  marginRight: 4,
                  verticalAlign: 'middle',
                }} />
                {tag.name}
              </button>
            ))}
          </div>
        )}
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
