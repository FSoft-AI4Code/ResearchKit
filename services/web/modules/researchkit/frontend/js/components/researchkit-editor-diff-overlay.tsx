import { FC, useEffect, useMemo } from 'react'
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
        onAccept={this.onAccept}
        onReject={this.onReject}
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
    .map(entry => ({
      entry,
      pos: Math.max(0, Math.min(entry.patch.selection_to, docLength)),
    }))
    .sort(
      (a, b) =>
        a.pos - b.pos ||
        a.entry.messageId.localeCompare(b.entry.messageId) ||
        a.entry.patchIndex - b.entry.patchIndex
    )
    .map(({ entry, pos }) =>
      Decoration.widget({
        widget: new ResearchKitInlineDiffWidget(entry, onAccept, onReject),
        block: true,
        side: 1,
      }).range(pos)
    )

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

  const pendingPatches = useMemo(
    () => collectPendingPatches(messages, openDocName),
    [messages, openDocName]
  )

  useEffect(() => {
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
    if (!view) return

    return () => {
      if (view.state.field(inlineDiffsField, false)) {
        view.dispatch({
          effects: setInlineDiffsEffect.of({
            patches: [],
            onAccept: applyPatch,
            onReject: rejectPatch,
          }),
        })
      }
    }
  }, [view, applyPatch, rejectPatch])

  return null
}
