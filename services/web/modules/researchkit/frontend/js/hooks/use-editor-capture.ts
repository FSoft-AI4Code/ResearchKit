import { useMemo } from 'react'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'

export type EditorCapture = {
  filePath: string | null
  docContent: string | null
  selectedText: string | null
  selectionFrom: number | null
  selectionTo: number | null
  cursorLine: number | null
  lineFrom: number | null
  lineTo: number | null
  autoDetected: boolean
}

export function useEditorCapture(): EditorCapture {
  const { view } = useEditorViewContext()
  const { openDocName } = useEditorOpenDocContext()

  return useMemo(() => {
    const filePath = openDocName || null
    const empty: EditorCapture = {
      filePath,
      docContent: null,
      selectedText: null,
      selectionFrom: null,
      selectionTo: null,
      cursorLine: null,
      lineFrom: null,
      lineTo: null,
      autoDetected: false,
    }

    if (!view) return empty

    const docContent = view.state.doc.toString()
    const { from, to } = view.state.selection.main
    if (from !== to) {
      const selectedText = view.state.doc.sliceString(from, to)
      const lineFrom = view.state.doc.lineAt(from).number
      const lineTo = view.state.doc.lineAt(to).number
      return {
        filePath,
        docContent,
        selectedText,
        selectionFrom: from,
        selectionTo: to,
        cursorLine: null,
        lineFrom,
        lineTo,
        autoDetected: false,
      }
    }

    // No selection — just record cursor line number
    const cursorLine = view.state.doc.lineAt(from).number
    return {
      filePath,
      docContent,
      selectedText: null,
      selectionFrom: null,
      selectionTo: null,
      cursorLine,
      lineFrom: null,
      lineTo: null,
      autoDetected: false,
    }
  }, [view, view?.state.selection, openDocName])
}
