import React, { useEffect, useState } from 'react'
import { fetchScripts } from '../api.js'

function ScriptButton({ script, onSelect }) {
  return (
    <button
      className="script-btn"
      title={script.content}
      onClick={() => onSelect(script.content)}
    >
      <div className="script-btn-name">{script.name}</div>
      {script.content && (
        <div className="script-btn-preview">
          {script.content.slice(0, 90)}{script.content.length > 90 ? '…' : ''}
        </div>
      )}
    </button>
  )
}

export default function ScriptsPanel({ onSelectScript, visible, onToggleVisible }) {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchScripts()
      .then(data => {
        if (!cancelled) setProjects(data.projects || [])
      })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const q = search.trim().toLowerCase()

  const filtered = q
    ? projects.map(p => ({
        ...p,
        groups: (p.groups || []).map(g => ({
          ...g,
          scripts: (g.scripts || []).filter(s =>
            (s.name || '').toLowerCase().includes(q) ||
            (s.content || '').toLowerCase().includes(q)
          ),
        })).filter(g => g.scripts.length > 0),
      })).filter(p => p.groups.length > 0)
    : projects

  const totalScripts = projects.reduce((n, p) =>
    n + (p.groups || []).reduce((m, g) => m + (g.scripts || []).length, 0), 0)

  if (!visible) return null

  return (
    <div className="scripts-panel">
      <div className="scripts-header">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div className="scripts-title">Скрипты</div>
          <button onClick={onToggleVisible} title="Скрыть панель" style={{
            background: 'none', border: 'none', color: 'var(--text3)',
            cursor: 'pointer', fontSize: 14, lineHeight: 1, padding: '2px 4px',
            borderRadius: 4,
          }}>✕</button>
        </div>
        <input type="search" className="search-input" placeholder="Поиск скрипта..."
          value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      <div className="scripts-scroll">
        {loading && <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}>
          <div className="spinner" style={{ width: 16, height: 16 }} />
        </div>}
        {!loading && error && <div className="scripts-empty" style={{ color: 'var(--red)' }}>Ошибка загрузки</div>}
        {!loading && !error && totalScripts === 0 && <div className="scripts-empty">Скриптов нет</div>}
        {!loading && !error && totalScripts > 0 && filtered.length === 0 && <div className="scripts-empty">Ничего не найдено</div>}

        {!loading && !error && filtered.map((proj, pi) => (
          <div key={pi} className="script-project">
            <div className="script-project-name">▸ {proj.project}</div>
            {(proj.groups || []).map((group, gi) => (
              <div key={gi} className="script-group">
                <div className="script-group-name">{group.name}</div>
                {(group.scripts || []).map(script => (
                  <ScriptButton key={script.id} script={script} onSelect={onSelectScript} />
                ))}
              </div>
            ))}
          </div>
        ))}
      </div>

      <div style={{ borderTop: '1px solid var(--border)', padding: '8px 12px', flexShrink: 0 }}>
        <a href="/scripts" target="_blank" rel="noopener noreferrer" style={{
          fontSize: 12, color: 'var(--text3)', textDecoration: 'none',
          display: 'flex', alignItems: 'center', gap: 5,
        }}>⚙️ Управление скриптами</a>
      </div>
    </div>
  )
}
