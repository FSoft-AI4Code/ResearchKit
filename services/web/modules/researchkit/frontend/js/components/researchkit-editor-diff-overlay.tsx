import { FC, useCallback, useEffect, useMemo, useRef } from 'react'
import { createRoot } from 'react-dom/client'
import type { Root } from 'react-dom/client'
import { Compartment, StateEffect, StateField } from '@codemirror/state'
import {
  Decoration,
  EditorView,
  WidgetType,
} from '@codemirror/view'
import type { DecorationSet } from '@codemirror/view'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useResearchKitContext } from '../context/researchkit-context'
import type { EditPatch, RKMessage } from '../context/researchkit-context'
import { ResearchKitDiffView } from './researchkit-diff-view'

type PatchEntry = {
  messageId: string
  patchIndex: number
  patch: EditPatch
}

type SetInlineDiffsPayload = {
  patches: PatchEntry[]
  onAccept: (messageId: string, patchIndex: number) => void
  onReject: (messageId: string, patchIndex: number) => void
}

const noopPatchHandler = (_messageId: string, _patchIndex: number) => {}

const setInlineDiffsEffect = StateEffect.define<SetInlineDiffsPayload>()

const inlineDiffCompartment = new Compartment()

class ResearchKitInlineDiffWidget extends WidgetType {
  static roots: WeakMap<HTMLElement, Root> = new WeakMap()

  constructor(
    private readonly entry: PatchEntry,
    private readonly onAccept: (messageId: string, patchIndex: number) => void,
    private readonly onReject: (messageId: string, patchIndex: number) => void
  ) {
    super()
  }

  private renderInto(element: HTMLElement) {
    let root = ResearchKitInlineDiffWidget.roots.get(element)
    if (!root) {
      root = createRoot(element)
      ResearchKitInlineDiffWidget.roots.set(element, root)
    }

    root.render(
      <ResearchKitDiffView
        patch={this.entry.patch}
        messageId={this.entry.messageId}
        patchIndex={this.entry.patchIndex}
        onOpen={noopPatchHandler}
        onAccept={this.onAccept}
        onReject={this.onReject}
        alwaysExpanded
      />
    )
  }

  toDOM() {
    const element = document.createElement('div')
    element.className = 'rk-editor-block-widget'
    this.renderInto(element)
    return element
  }

  eq() {
    return false
  }

  updateDOM(element: HTMLElement) {
    this.renderInto(element)
    return true
  }

  ignoreEvent() {
    return true
  }

  destroy(element: HTMLElement) {
    const root = ResearchKitInlineDiffWidget.roots.get(element)
    if (root) {
      root.unmount()
      ResearchKitInlineDiffWidget.roots.delete(element)
    }
  }
}

const inlineDiffsField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none
  },
  update(value, tr) {
    let mapped = value.map(tr.changes)

    for (const effect of tr.effects) {
      if (effect.is(setInlineDiffsEffect)) {
        mapped = buildInlineDiffDecorations(
          effect.value.patches,
          effect.value.onAccept,
          effect.value.onReject,
          tr.state.doc.length
        )
      }
    }

    return mapped
  },
})

const inlineDiffsExtension = [
  inlineDiffsField,
  EditorView.decorations.from(inlineDiffsField),
]

function ensureInlineDiffExtension(view: EditorView) {
  if (view.state.field(inlineDiffsField, false)) {
    return
  }

  view.dispatch({
    effects: StateEffect.appendConfig.of(
      inlineDiffCompartment.of(inlineDiffsExtension)
    ),
  })
}

function buildInlineDiffDecorations(
  patches: PatchEntry[],
  onAccept: (messageId: string, patchIndex: number) => void,
  onReject: (messageId: string, patchIndex: number) => void,
  docLength: number
) {
  const decorations = patches
    .map(entry => {
      const from = Math.max(0, Math.min(entry.patch.selection_from, docLength))
      const to = Math.max(from, Math.min(entry.patch.selection_to, docLength))
      return { entry, from, to }
    })
    .sort(
      (a, b) =>
        a.from - b.from ||
        a.entry.messageId.localeCompare(b.entry.messageId) ||
        a.entry.patchIndex - b.entry.patchIndex
    )
    .map(({ entry, from, to }) => {
      const widget = new ResearchKitInlineDiffWidget(entry, onAccept, onReject)
      if (from < to) {
        // Replace the original text region with the diff widget (git-diff style)
        return Decoration.replace({
          widget,
          block: true,
        }).range(from, to)
      }
      // Pure insertion — place widget at the insert point
      return Decoration.widget({
        widget,
        block: true,
        side: 1,
      }).range(from)
    })

  return Decoration.set(decorations, true)
}

function normalizePath(path: string): string {
  return path.replace(/^\/+/, '').toLowerCase()
}

function isPatchForOpenDocument(
  patchPath: string,
  openDocName: string | null
): boolean {
  if (!openDocName) return true

  const patch = normalizePath(patchPath)
  const openDoc = normalizePath(openDocName)

  return (
    patch === openDoc ||
    patch.endsWith(`/${openDoc}`) ||
    openDoc.endsWith(`/${patch}`)
  )
}

function collectPendingPatches(
  messages: RKMessage[],
  openDocName: string | null
): PatchEntry[] {
  return messages
    .flatMap(message =>
      (message.patches || []).map((patch, patchIndex) => ({
        messageId: message.id,
        patchIndex,
        patch,
      }))
    )
    .filter(
      entry =>
        (entry.patch._status || 'pending') === 'pending' &&
        isPatchForOpenDocument(entry.patch.file_path, openDocName)
    )
}

export const ResearchKitEditorDiffOverlay: FC = () => {
  const { messages, applyPatch, rejectPatch } = useResearchKitContext()
  const { openDocName } = useEditorOpenDocContext()
  const { view } = useEditorViewContext()
  const latestViewRef = useRef<EditorView | null>(null)

  const pendingPatches = useMemo(
    () => collectPendingPatches(messages, openDocName),
    [messages, openDocName]
  )

  useEffect(() => {
    latestViewRef.current = view
  }, [view])

  const applyInlineDiffs = useCallback(() => {
    if (!view) return

    ensureInlineDiffExtension(view)
    view.dispatch({
      effects: setInlineDiffsEffect.of({
        patches: pendingPatches,
        onAccept: applyPatch,
        onReject: rejectPatch,
      }),
    })
  }, [view, pendingPatches, applyPatch, rejectPatch])

  useEffect(() => {
    applyInlineDiffs()
  }, [applyInlineDiffs])

  useEffect(() => {
    if (!view) return

    // The open-doc context can update before the editor document transaction
    // completes. Re-apply diffs after doc-open lifecycle events to avoid
    // losing inline widgets when navigating between files.
    const reapplyAfterDocOpen = () => {
      window.requestAnimationFrame(() => {
        applyInlineDiffs()
      })
    }

    window.addEventListener('doc:after-opened', reapplyAfterDocOpen)
    window.addEventListener(
      'editor:scroll-position-restored',
      reapplyAfterDocOpen
    )
    return () => {
      window.removeEventListener('doc:after-opened', reapplyAfterDocOpen)
      window.removeEventListener(
        'editor:scroll-position-restored',
        reapplyAfterDocOpen
      )
    }
  }, [view, applyInlineDiffs])

  useEffect(() => {
    // Cleanup only on unmount. Clearing on dependency changes can remove diffs
    // during normal file navigation.
    return () => {
      const currentView = latestViewRef.current
      if (!currentView) return

      if (currentView.state.field(inlineDiffsField, false)) {
        currentView.dispatch({
          effects: setInlineDiffsEffect.of({
            patches: [],
            onAccept: noopPatchHandler,
            onReject: noopPatchHandler,
          }),
        })
      }
    }
  }, [])

  return null
}
