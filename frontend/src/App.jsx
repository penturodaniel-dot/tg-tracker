import React, { useState, useCallback } from 'react'
import ConvList from './components/ConvList.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ScriptsPanel from './components/ScriptsPanel.jsx'
import NavSidebar from './components/NavSidebar.jsx'
import { useConvs } from './hooks/useConvs.js'

export default function App() {
  const [selectedId, setSelectedId] = useState(null)
  const [pendingScript, setPendingScript] = useState(null)

  const {
    convs,
    status,
    setStatus,
    search,
    setSearch,
    loading,
    hasMore,
    loadMore,
  } = useConvs()

  const handleSelect = useCallback((id) => {
    setSelectedId(id)
  }, [])

  // Called after conv mutation (close/reopen/lead) so ConvList reflects change
  const handleConvUpdate = useCallback(() => {
    // convs will be refreshed on next poll automatically (5s)
    // nothing extra needed unless we want instant refresh
  }, [])

  // Called after delete: deselect if current conv was deleted
  const handleConvDeleted = useCallback((deletedId) => {
    if (selectedId === deletedId) setSelectedId(null)
  }, [selectedId])

  const handleScriptSelect = useCallback((content) => {
    setPendingScript(content)
  }, [])

  const handleScriptConsumed = useCallback(() => {
    setPendingScript(null)
  }, [])

  return (
    <div className="app-layout">
      <NavSidebar />
      <ConvList
        convs={convs}
        status={status}
        setStatus={setStatus}
        search={search}
        setSearch={setSearch}
        loading={loading}
        hasMore={hasMore}
        loadMore={loadMore}
        selectedId={selectedId}
        onSelect={handleSelect}
      />
      <ChatPanel
        convId={selectedId}
        onConvUpdate={handleConvUpdate}
        onConvDeleted={handleConvDeleted}
        scriptText={pendingScript}
        onScriptConsumed={handleScriptConsumed}
      />
      <ScriptsPanel onSelectScript={handleScriptSelect} />
    </div>
  )
}
