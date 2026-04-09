import React, { useEffect, useState } from 'react'
import { fetchScripts } from '../api.js'

export default function ScriptsPanel({ onSelectScript }) {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

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

  const allScripts = groups.flatMap(g => g.scripts || [])

  return (
    <div className="scripts-panel">
      <div className="scripts-header">
        <div className="scripts-title">Скрипты</div>
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
        {!loading && !error && groups.map((group, gi) => (
          <div key={gi} className="script-group">
            <div className="script-group-name">{group.name}</div>
            {(group.scripts || []).map(script => (
              <button
                key={script.id}
                className="script-btn"
                title={script.content}
                onClick={() => onSelectScript(script.content)}
              >
                {script.name}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
