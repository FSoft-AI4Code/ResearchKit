import { useMemo } from 'react'
import { EditorView } from '@codemirror/view'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'

export type EditorCapture = {
  filePath: string | null
  selectedText: string | null
  selectionFrom: number | null
  selectionTo: number | null
  autoDetected: boolean
}

const BOUNDARY_RE =
  /^\\(section|subsection|subsubsection|chapter|part|begin|end|documentclass|usepackage|title|author|date|maketitle|tableofcontents|bibliography|newcommand|renewcommand|input|include)\b/

/**
 * Detect the LaTeX paragraph surrounding the cursor.
 * A "paragraph" is contiguous non-empty lines that aren't structural commands,
 * bounded by blank lines or LaTeX structural commands.
 */
export function detectParagraphAroundCursor(
  view: EditorView
): { text: string; from: number; to: number } | null {
  const doc = view.state.doc
  const cursor = view.state.selection.main.head
  const totalLines = doc.lines

  const isBoundary = (lineNum: number): boolean => {
    if (lineNum < 1 || lineNum > totalLines) return true
    const text = doc.line(lineNum).text.trim()
    return text === '' || BOUNDARY_RE.test(text)
  }

  // Find a content line near cursor (if cursor is on a boundary, look upward then downward)
  let contentLine = doc.lineAt(cursor).number
  if (isBoundary(contentLine)) {
    let up = contentLine - 1
    while (up >= 1 && isBoundary(up)) up--
    if (up >= 1) {
      contentLine = up
    } else {
      let down = contentLine + 1
      while (down <= totalLines && isBoundary(down)) down++
      if (down <= totalLines) {
        contentLine = down
      } else {
        return null
      }
    }
  }

  // Expand outward to find full paragraph
  let startLine = contentLine
  while (startLine > 1 && !isBoundary(startLine - 1)) startLine--

  let endLine = contentLine
  while (endLine < totalLines && !isBoundary(endLine + 1)) endLine++

  const from = doc.line(startLine).from
  const to = doc.line(endLine).to
  const text = doc.sliceString(from, to)

  return text.trim() ? { text, from, to } : null
}

export function useEditorCapture(): EditorCapture {
  const { view } = useEditorViewContext()
  const { openDocName } = useEditorOpenDocContext()

  return useMemo(() => {
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
  }, [view, view?.state.selection, openDocName])
}
