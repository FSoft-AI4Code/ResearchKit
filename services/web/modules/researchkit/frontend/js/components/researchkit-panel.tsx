import { FC, useCallback } from 'react'
import {
  ResearchKitProvider,
  useResearchKitContext,
} from '../context/researchkit-context'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'
import { EditorCapture, detectParagraphAroundCursor } from '../hooks/use-editor-capture'
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
  } = useResearchKitContext()

  const { view } = useEditorViewContext()
  const { openDocName } = useEditorOpenDocContext()

  // Capture editor state at the moment the user clicks Send
  const getCaptureRef = useCallback((): EditorCapture => {
    const filePath = openDocName || null
    const empty: EditorCapture = { filePath, selectedText: null, selectionFrom: null, selectionTo: null, autoDetected: false }

    if (!view) return empty

    const { from, to } = view.state.selection.main
    if (from !== to) {
      const selectedText = view.state.doc.sliceString(from, to)
      return { filePath, selectedText, selectionFrom: from, selectionTo: to, autoDetected: false }
    }

    // No selection — auto-detect paragraph at cursor
    const para = detectParagraphAroundCursor(view)
    if (para) {
      return { filePath, selectedText: para.text, selectionFrom: para.from, selectionTo: para.to, autoDetected: true }
    }

    return empty
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
        <ResearchKitMessageList messages={messages} />
        <ResearchKitMessageInput
          onSend={handleSend}
          isStreaming={isStreaming}
          selectedText={capture.selectedText || undefined}
          autoDetected={capture.autoDetected}
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
