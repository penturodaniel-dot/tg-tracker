import React, { useState, useCallback } from 'react'
import ConvList from './components/ConvList.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import ScriptsPanel from './components/ScriptsPanel.jsx'
import NavSidebar from './components/NavSidebar.jsx'
import { useConvs } from './hooks/useConvs.js'
import { useNotifications } from './hooks/useNotifications.js'

export default function App() {
  const [selectedId, setSelectedId] = useState(null)
  const [pendingScript, setPendingScript] = useState(null)
  const [scriptsVisible, setScriptsVisible] = useState(true)

  const {
    convs,
    status,
    setStatus,
    search,
    setSearch,
    tagFilter,
    setTagFilter,
    categoryFilter,
    setCategoryFilter,
    loading,
    hasMore,
    loadMore,
    removeConv,
  } = useConvs()

  useNotifications(convs)

  const handleSelect = useCallback((id) => {
    setSelectedId(id)
  }, [])

  const handleConvUpdate = useCallback(() => {
    // convs refresh automatically on next 5s poll
  }, [])

  // Remove from list immediately + deselect
  const handleConvDeleted = useCallback((deletedId) => {
    removeConv(deletedId)
    if (selectedId === deletedId) setSelectedId(null)
  }, [selectedId, removeConv])

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
        tagFilter={tagFilter}
        setTagFilter={setTagFilter}
        categoryFilter={categoryFilter}
        setCategoryFilter={setCategoryFilter}
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
        scriptsVisible={scriptsVisible}
        onShowScripts={() => setScriptsVisible(true)}
      />
      <ScriptsPanel
        onSelectScript={handleScriptSelect}
        visible={scriptsVisible}
        onToggleVisible={() => setScriptsVisible(false)}
      />
    </div>
  )
}
