import React, { useRef, useCallback } from 'react'
import ChatHeader from './ChatHeader.jsx'
import MessageList from './MessageList.jsx'
import SendBar from './SendBar.jsx'
import { useConv } from '../hooks/useConv.js'
import { useMessages } from '../hooks/useMessages.js'

export default function ChatPanel({ convId, onConvUpdate, onConvDeleted, scriptText, onScriptConsumed, scriptsVisible, onShowScripts }) {
  const { conv, loading: convLoading, refresh: refreshConv } = useConv(convId)
  const { messages, readMaxId, loading: msgsLoading, addOptimistic, deleteMsg, editMsg, refresh } = useMessages(convId)
  const textareaRef = useRef(null)

  // When a script is selected in the panel, paste it into the textarea
  React.useEffect(() => {
    if (!scriptText || !textareaRef.current) return
    const ta = textareaRef.current
    const start = ta.selectionStart
    const end = ta.selectionEnd
    const current = ta.value
    const newVal = current.slice(0, start) + scriptText + current.slice(end)

    // Trigger React's onChange synthetic event
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
      window.HTMLTextAreaElement.prototype, 'value'
    ).set
    nativeInputValueSetter.call(ta, newVal)
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    ta.focus()
    const pos = start + scriptText.length
    ta.setSelectionRange(pos, pos)
    // Auto-resize
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
    onScriptConsumed()
  }, [scriptText, onScriptConsumed])

  const handleConvUpdate = useCallback(() => {
    refreshConv()
    if (onConvUpdate) onConvUpdate()
  }, [refreshConv, onConvUpdate])

  const handleOptimisticSend = useCallback((text) => {
    addOptimistic(text, 'Менеджер')
  }, [addOptimistic])

  const showScriptsBtn = !scriptsVisible && (
    <button
      className="scripts-show-btn"
      title="Показать скрипты"
      onClick={onShowScripts}
    >
      📝
    </button>
  )

  if (!convId) {
    return (
      <div className="chat-panel" style={{ position: 'relative' }}>
        <div className="chat-empty">
          Выберите диалог
        </div>
        {showScriptsBtn}
      </div>
    )
  }

  return (
    <div className="chat-panel" style={{ position: 'relative' }}>
      <ChatHeader
        conv={conv}
        onUpdate={handleConvUpdate}
        onDeleted={onConvDeleted}
      />
      <MessageList
        messages={messages}
        readMaxId={readMaxId}
        loading={msgsLoading}
        onDeleteMsg={deleteMsg}
        onEditMsg={editMsg}
      />
      <SendBar
        convId={convId}
        onOptimisticSend={handleOptimisticSend}
        onAfterSend={refresh}
        textareaRef={textareaRef}
      />
      {showScriptsBtn}
    </div>
  )
}
