import React, { useEffect, useState } from 'react'
import { fetchScripts } from '../api.js'

export default function ScriptsPanel({ onSelectScript, visible, onToggleVisible }) {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchScripts()
      .then(data => {
        if (!cancelled) setGroups(data.groups || [])
      })
      .catch(e => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const q = search.trim().toLowerCase()

  const filteredGroups = q
    ? groups
        .map(g => ({
          ...g,
          scripts: (g.scripts || []).filter(
            s =>
              (s.name || '').toLowerCase().includes(q) ||
              (s.content || '').toLowerCase().includes(q)
          ),
        }))
        .filter(g => g.scripts.length > 0)
    : groups

  const allScripts = groups.flatMap(g => g.scripts || [])

  if (!visible) return null

  return (
    <div className="scripts-panel">
      <div className="scripts-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div className="scripts-title">Скрипты</div>
          <button
            onClick={onToggleVisible}
            title="Скрыть панель"
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text3)',
              cursor: 'pointer',
              fontSize: 14,
              lineHeight: 1,
              padding: '2px 4px',
              borderRadius: 4,
              transition: 'color 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--text3)'}
          >
            ✕
          </button>
        </div>
        <input
          type="search"
          className="search-input"
          placeholder="Поиск скрипта..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <div className="scripts-scroll">
        {loading && (
          <div style={{ display: 'flex', justifyContent: 'center', paddingTop: '24px' }}>
            <div className="spinner" style={{ width: 16, height: 16 }} />
          </div>
        )}
        {!loading && error && (
          <div className="scripts-empty" style={{ color: 'var(--red)' }}>
            Ошибка загрузки
          </div>
        )}
        {!loading && !error && allScripts.length === 0 && (
          <div className="scripts-empty">Скриптов нет</div>
        )}
        {!loading && !error && allScripts.length > 0 && filteredGroups.length === 0 && (
          <div className="scripts-empty">Ничего не найдено</div>
        )}
        {!loading && !error && filteredGroups.map((group, gi) => (
          <div key={gi} className="script-group">
            <div className="script-group-name">{group.name}</div>
            {(group.scripts || []).map(script => (
              <button
                key={script.id}
                className="script-btn"
                title={script.content}
                onClick={() => onSelectScript(script.content)}
              >
                <div className="script-btn-name">{script.name}</div>
                {script.content && (
                  <div className="script-btn-preview">
                    {script.content.slice(0, 90)}{script.content.length > 90 ? '…' : ''}
                  </div>
                )}
              </button>
            ))}
          </div>
        ))}
      </div>

      <div style={{
        borderTop: '1px solid var(--border)',
        padding: '8px 12px',
        flexShrink: 0,
      }}>
        <a
          href="/scripts"
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: 12,
            color: 'var(--text3)',
            textDecoration: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
            transition: 'color 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text2)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text3)'}
        >
          ⚙️ Управление скриптами
        </a>
      </div>
    </div>
  )
}
