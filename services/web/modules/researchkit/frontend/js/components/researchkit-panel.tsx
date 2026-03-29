import { FC, useCallback } from 'react'
import {
  ResearchKitProvider,
  useResearchKitContext,
} from '../context/researchkit-context'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'
import { EditorCapture } from '../hooks/use-editor-capture'
import { ResearchKitMessageList } from './researchkit-message-list'
import { ResearchKitMessageInput } from './researchkit-message-input'
import { ResearchKitEditorDiffOverlay } from './researchkit-editor-diff-overlay'
import '../../stylesheets/researchkit.scss'

const ResearchKitPanelContent: FC = () => {
  const {
    messages,
    isStreaming,
    error,
    sendMessage,
    indexProject,
    clearConversation,
    openPatch,
    applyPatch,
    rejectPatch,
  } = useResearchKitContext()

  const { view } = useEditorViewContext()
  const { openDocName } = useEditorOpenDocContext()

  // Capture editor state at the moment the user clicks Send
  const getCaptureRef = useCallback((): EditorCapture => {
    const filePath = openDocName || null
    const empty: EditorCapture = {
      filePath, selectedText: null, selectionFrom: null, selectionTo: null,
      cursorLine: null, lineFrom: null, lineTo: null, autoDetected: false,
    }

    if (!view) return empty

    const { from, to } = view.state.selection.main
    if (from !== to) {
      const selectedText = view.state.doc.sliceString(from, to)
      const lineFrom = view.state.doc.lineAt(from).number
      const lineTo = view.state.doc.lineAt(to).number
      return {
        filePath, selectedText, selectionFrom: from, selectionTo: to,
        cursorLine: null, lineFrom, lineTo, autoDetected: false,
      }
    }

    // No selection — just record cursor line
    const cursorLine = view.state.doc.lineAt(from).number
    return {
      filePath, selectedText: null, selectionFrom: null, selectionTo: null,
      cursorLine, lineFrom: null, lineTo: null, autoDetected: false,
    }
  }, [view, openDocName])

  const handleSend = useCallback(
    (message: string) => {
      const capture = getCaptureRef()
      sendMessage(message, capture)
    },
    [sendMessage, getCaptureRef]
  )

  // Compute current capture for the input preview
  const capture = getCaptureRef()

  return (
    <div className="rk-panel">
      <div className="rail-panel-header">
        <h4 className="rail-panel-title">ResearchKit</h4>
      </div>
      <div className="rk-toolbar">
        <button
          className="rk-toolbar-btn"
          onClick={indexProject}
          title="Index project to build paper context"
        >
          Index Project
        </button>
        <button
          className="rk-toolbar-btn"
          onClick={clearConversation}
          title="Clear conversation history"
        >
          Clear
        </button>
      </div>
      {error && (
        <div className="rk-error">
          {error}
        </div>
      )}
      <ResearchKitEditorDiffOverlay />
      <div className="rk-chat-wrapper">
        <ResearchKitMessageList
          messages={messages}
          onOpenPatch={openPatch}
          onAcceptPatch={applyPatch}
          onRejectPatch={rejectPatch}
        />
        <ResearchKitMessageInput
          onSend={handleSend}
          isStreaming={isStreaming}
          selectedText={capture.selectedText || undefined}
          cursorLine={capture.cursorLine}
          lineFrom={capture.lineFrom}
          lineTo={capture.lineTo}
          filePath={capture.filePath}
        />
      </div>
    </div>
  )
}

const ResearchKitPanel: FC = () => {
  return (
    <ResearchKitProvider>
      <ResearchKitPanelContent />
    </ResearchKitProvider>
  )
}

export default ResearchKitPanel
