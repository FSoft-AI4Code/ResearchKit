import {
  createContext,
  FC,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useMemo,
  useRef,
} from 'react'
import { EditorView } from '@codemirror/view'
import { useProjectContext } from '@/shared/context/project-context'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'
import { useEditorManagerContext } from '@/features/ide-react/context/editor-manager-context'
import { useFileTreeData } from '@/shared/context/file-tree-data-context'
import { findEntityByPath } from '@/features/file-tree/util/path'
import { postJSON, deleteJSON } from '@/infrastructure/fetch-json'
import getMeta from '@/utils/meta'
import { EditorCapture } from '../hooks/use-editor-capture'

export type EditPatch = {
  file_path: string
  selection_from: number
  selection_to: number
  original_text: string
  replacement_text: string
  description: string
  action_id?: string
  response_id?: string
  action_sequence?: number
  command_summary?: string
  _status?: 'pending' | 'accepted' | 'rejected'
}

export type RKMessageContext = {
  filePath: string | null
  cursorLine: number | null
  lineFrom: number | null
  lineTo: number | null
  selectedText: string | null
}

export type RKMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  isStreaming?: boolean
  responseId?: string
  actionId?: string
  patches?: EditPatch[]
  actions?: RKAction[]
  context?: RKMessageContext
}

export type RKAction = {
  tool: string
  status: 'started' | 'completed' | 'error' | 'warning' | string
  iteration: number
  detail: string
  action_id?: string
  response_id?: string
  sequence?: number
  command?: string
  has_patch?: boolean
  patch_count?: number
}

type RKResponseChunk = {
  response_id?: string
  content: string
}

type State = {
  messages: RKMessage[]
  isStreaming: boolean
  error: string | null
  memoryLoaded: boolean
  memorySummary: string | null
}

type Action =
  | { type: 'ADD_USER_MESSAGE'; message: RKMessage }
  | { type: 'START_STREAMING' }
  | { type: 'APPEND_STREAM_CHUNK'; chunk: string; responseId?: string }
  | { type: 'ADD_PATCH'; patch: EditPatch }
  | { type: 'ADD_ACTION'; action: RKAction }
  | { type: 'UPDATE_PATCH_STATUS'; messageId: string; patchIndex: number; status: 'accepted' | 'rejected' }
  | { type: 'END_STREAMING' }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'SET_MEMORY'; summary: string }

function newAssistantMessage(
  partial: Partial<RKMessage> = {}
): RKMessage {
  return {
    id: `assistant-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    role: 'assistant',
    content: '',
    timestamp: Date.now(),
    isStreaming: true,
    patches: [],
    actions: [],
    ...partial,
  }
}

function findAssistantMessageIndex(
  messages: RKMessage[],
  {
    responseId,
    actionId,
    fallbackToLastAssistant = false,
  }: {
    responseId?: string
    actionId?: string
    fallbackToLastAssistant?: boolean
  }
): number {
  if (responseId) {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      if (msg.role === 'assistant' && msg.responseId === responseId) {
        return i
      }
    }
  }

  if (actionId) {
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i]
      if (msg.role === 'assistant' && msg.actionId === actionId) {
        return i
      }
    }
  }

  if (fallbackToLastAssistant) {
    const last = messages[messages.length - 1]
    if (last?.role === 'assistant') {
      return messages.length - 1
    }
  }

  return -1
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return { ...state, messages: [...state.messages, action.message] }
    case 'START_STREAMING':
      return { ...state, isStreaming: true, error: null }
    case 'APPEND_STREAM_CHUNK': {
      const msgs = [...state.messages]
      const targetIdx = findAssistantMessageIndex(msgs, {
        responseId: action.responseId,
        fallbackToLastAssistant: !action.responseId,
      })

      if (targetIdx >= 0) {
        const target = msgs[targetIdx]
        msgs[targetIdx] = {
          ...target,
          responseId: target.responseId || action.responseId,
          content: target.content + action.chunk,
          isStreaming: true,
        }
      } else {
        msgs.push(
          newAssistantMessage({
            content: action.chunk,
            responseId: action.responseId,
          })
        )
      }
      return { ...state, messages: msgs }
    }
    case 'ADD_PATCH': {
      const msgs = [...state.messages]
      const patch = { ...action.patch, _status: 'pending' as const }
      const targetIdx = findAssistantMessageIndex(msgs, {
        responseId: patch.response_id,
        actionId: patch.action_id,
        fallbackToLastAssistant: !patch.response_id && !patch.action_id,
      })

      if (targetIdx >= 0) {
        const target = msgs[targetIdx]
        const patches = [...(target.patches || []), patch]
        msgs[targetIdx] = {
          ...target,
          responseId: target.responseId || patch.response_id,
          actionId: target.actionId || patch.action_id,
          patches,
        }
      } else {
        msgs.push(
          newAssistantMessage({
            responseId: patch.response_id,
            actionId: patch.action_id,
            patches: [patch],
          })
        )
      }
      return { ...state, messages: msgs }
    }
    case 'ADD_ACTION': {
      const msgs = [...state.messages]
      const targetIdx = findAssistantMessageIndex(msgs, {
        responseId: action.action.response_id,
        actionId: action.action.action_id,
        fallbackToLastAssistant:
          !action.action.response_id && !action.action.action_id,
      })

      if (targetIdx >= 0) {
        const target = msgs[targetIdx]
        const actions = [...(target.actions || []), action.action]
        msgs[targetIdx] = {
          ...target,
          responseId: target.responseId || action.action.response_id,
          actionId: target.actionId || action.action.action_id,
          actions,
        }
      } else {
        msgs.push(
          newAssistantMessage({
            responseId: action.action.response_id,
            actions: [action.action],
            actionId: action.action.action_id,
          })
        )
      }
      return { ...state, messages: msgs }
    }
    case 'UPDATE_PATCH_STATUS': {
      const msgs = state.messages.map(msg => {
        if (msg.id !== action.messageId || !msg.patches) return msg
        const patches = msg.patches.map((p, idx) =>
          idx === action.patchIndex ? { ...p, _status: action.status } : p
        )
        return { ...msg, patches }
      })
      return { ...state, messages: msgs }
    }
    case 'END_STREAMING': {
      const msgs = state.messages.map(msg =>
        msg.role === 'assistant' && msg.isStreaming
          ? { ...msg, isStreaming: false }
          : msg
      )
      return { ...state, isStreaming: false, messages: msgs }
    }
    case 'SET_ERROR':
      return { ...state, isStreaming: false, error: action.error }
    case 'CLEAR_ERROR':
      return { ...state, error: null }
    case 'CLEAR_MESSAGES':
      return { ...state, messages: [] }
    case 'SET_MEMORY':
      return { ...state, memoryLoaded: true, memorySummary: action.summary }
    default:
      return state
  }
}

const initialState: State = {
  messages: [],
  isStreaming: false,
  error: null,
  memoryLoaded: false,
  memorySummary: null,
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

type ResearchKitContextValue = {
  messages: RKMessage[]
  isStreaming: boolean
  error: string | null
  memoryLoaded: boolean
  memorySummary: string | null
  sendMessage: (message: string, capture?: EditorCapture) => Promise<void>
  indexProject: () => Promise<void>
  clearConversation: () => Promise<void>
  openPatch: (messageId: string, patchIndex: number) => Promise<void>
  applyPatch: (messageId: string, patchIndex: number) => void
  rejectPatch: (messageId: string, patchIndex: number) => void
}

const ResearchKitContext = createContext<ResearchKitContextValue | undefined>(
  undefined
)

export const ResearchKitProvider: FC<React.PropsWithChildren> = ({
  children,
}) => {
  const { projectId } = useProjectContext()
  const { view } = useEditorViewContext()
  const { openDocName } = useEditorOpenDocContext()
  const { openDocWithId } = useEditorManagerContext()
  const { fileTreeData } = useFileTreeData()
  const editorViewRef = useRef<EditorView | null>(view)
  const isStreamingRef = useRef(false)
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    editorViewRef.current = view
  }, [view])

  useEffect(() => {
    isStreamingRef.current = state.isStreaming
  }, [state.isStreaming])

  const sendMessage = useCallback(
    async (message: string, capture?: EditorCapture) => {
      if (isStreamingRef.current) {
        dispatch({
          type: 'SET_ERROR',
          error: 'Please wait for the current agent run to finish before sending a new message.',
        })
        return
      }

      const selectedText = capture?.selectedText || null
      const filePath = capture?.filePath || null
      const selectionFrom = capture?.selectionFrom ?? null
      const selectionTo = capture?.selectionTo ?? null
      const cursorLine = capture?.cursorLine ?? null
      const lineFrom = capture?.lineFrom ?? null
      const lineTo = capture?.lineTo ?? null

      const msgContext: RKMessageContext | undefined =
        selectedText || cursorLine
          ? { filePath, cursorLine, lineFrom, lineTo, selectedText }
          : undefined

      const userMsg: RKMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: message,
        timestamp: Date.now(),
        context: msgContext,
      }
      dispatch({ type: 'ADD_USER_MESSAGE', message: userMsg })
      dispatch({ type: 'START_STREAMING' })

      try {
        const response = await fetch(
          `/project/${projectId}/researchkit/chat`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Csrf-Token': getMeta('ol-csrfToken'),
            },
            body: JSON.stringify({
              message,
              selected_text: selectedText,
              file_path: filePath,
              selection_from: selectionFrom,
              selection_to: selectionTo,
              cursor_line: cursorLine,
              line_from: lineFrom,
              line_to: lineTo,
            }),
          }
        )

        if (!response.ok) {
          throw new Error(`Chat request failed: ${response.statusText}`)
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error('No response stream')

        const decoder = new TextDecoder()
        let buffer = ''
        let currentEventType = 'message'
        let dataLines: string[] = []

        const flushEvent = () => {
          if (dataLines.length === 0) return

          if (currentEventType === 'done') {
            dispatch({ type: 'END_STREAMING' })
            dataLines = []
            return
          }

          const content = dataLines.join('\n')
          dataLines = []

          if (currentEventType === 'patch') {
            try {
              dispatch({ type: 'ADD_PATCH', patch: JSON.parse(content) as EditPatch })
            } catch (e) {
              console.error('Failed to parse patch event', e)
            }
          } else if (currentEventType === 'response') {
            try {
              const payload = JSON.parse(content) as RKResponseChunk
              dispatch({
                type: 'APPEND_STREAM_CHUNK',
                chunk: payload.content,
                responseId: payload.response_id,
              })
            } catch (e) {
              console.error('Failed to parse response event', e)
            }
          } else if (currentEventType === 'action') {
            try {
              dispatch({ type: 'ADD_ACTION', action: JSON.parse(content) as RKAction })
            } catch (e) {
              console.error('Failed to parse action event', e)
            }
          } else if (content.length > 0) {
            dispatch({ type: 'APPEND_STREAM_CHUNK', chunk: content })
          }
        }

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Parse SSE events from buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmedLine = line.replace(/\r$/, '')

            // Empty line = event boundary per SSE spec
            if (!trimmedLine) {
              flushEvent()
              currentEventType = 'message'
              continue
            }

            if (trimmedLine.startsWith('event:')) {
              flushEvent()
              currentEventType = trimmedLine.slice(6).trim()
              continue
            }

            if (trimmedLine.startsWith('data:')) {
              const data = trimmedLine.slice(5)
              dataLines.push(data.startsWith(' ') ? data.slice(1) : data)
            }
          }
        }

        // Flush any remaining event data
        flushEvent()
        dispatch({ type: 'END_STREAMING' })

        dispatch({ type: 'END_STREAMING' })
      } catch (err) {
        dispatch({
          type: 'SET_ERROR',
          error: err instanceof Error ? err.message : 'Failed to send message',
        })
      }
    },
    [projectId]
  )

  const openPatch = useCallback(
    async (messageId: string, patchIndex: number) => {
      const msg = state.messages.find(m => m.id === messageId)
      const patch = msg?.patches?.[patchIndex]
      if (!patch) return

      const normalizedPath = patch.file_path.replace(/^\/+/, '')
      const found =
        findEntityByPath(fileTreeData, normalizedPath) ||
        findEntityByPath(fileTreeData, `./${normalizedPath}`)

      if (!found || found.type !== 'doc') {
        dispatch({
          type: 'SET_ERROR',
          error: `Could not find "${patch.file_path}" in the editor file tree.`,
        })
        return
      }

      try {
        await openDocWithId(found.entity._id, {
          gotoOffset: patch.selection_from,
        })
      } catch (_err) {
        dispatch({
          type: 'SET_ERROR',
          error: `Failed to open "${patch.file_path}" in the editor.`,
        })
      }
    },
    [fileTreeData, openDocWithId, state.messages]
  )

  const applyPatch = useCallback(
    (messageId: string, patchIndex: number) => {
      const ev = editorViewRef.current
      if (!ev) {
        dispatch({ type: 'SET_ERROR', error: 'Editor not available' })
        return
      }

      // Find the patch
      const msg = state.messages.find(m => m.id === messageId)
      if (!msg?.patches?.[patchIndex]) return
      const patch = msg.patches[patchIndex]

      if (!isPatchForOpenDocument(patch.file_path, openDocName || null)) {
        dispatch({
          type: 'SET_ERROR',
          error: `Open "${patch.file_path}" in the editor before applying this patch.`,
        })
        return
      }

      // Verify the text at the expected range still matches
      let from = patch.selection_from
      let to = patch.selection_to
      const currentText = ev.state.doc.sliceString(from, to)

      if (currentText !== patch.original_text) {
        // Document changed — try to find original text nearby
        const docText = ev.state.doc.toString()
        const searchStart = Math.max(0, from - 500)
        const searchEnd = Math.min(docText.length, to + 500)
        const searchRegion = docText.slice(searchStart, searchEnd)
        const idx = searchRegion.indexOf(patch.original_text)

        if (idx === -1) {
          dispatch({
            type: 'SET_ERROR',
            error: 'The document has changed and the original text could not be found. Please try again.',
          })
          return
        }

        from = searchStart + idx
        to = from + patch.original_text.length
      }

      // Apply the change to CodeMirror
      const changes = ev.state.changes([
        { from, to, insert: patch.replacement_text },
      ])
      ev.dispatch({ changes })

      dispatch({ type: 'UPDATE_PATCH_STATUS', messageId, patchIndex, status: 'accepted' })
    },
    [state.messages, openDocName]
  )

  const rejectPatch = useCallback(
    (messageId: string, patchIndex: number) => {
      dispatch({ type: 'UPDATE_PATCH_STATUS', messageId, patchIndex, status: 'rejected' })
    },
    []
  )

  const indexProject = useCallback(async () => {
    try {
      const data = await postJSON(
        `/project/${projectId}/researchkit/index`,
        { body: {} }
      )
      dispatch({
        type: 'SET_MEMORY',
        summary: (data as { summary?: string }).summary || 'Project indexed successfully',
      })
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        error: 'Failed to index project',
      })
    }
  }, [projectId])

  const clearConversation = useCallback(async () => {
    try {
      await deleteJSON(`/project/${projectId}/researchkit/conversation`)
      dispatch({ type: 'CLEAR_MESSAGES' })
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        error: 'Failed to clear conversation',
      })
    }
  }, [projectId])

  const value = useMemo(
    () => ({
      messages: state.messages,
      isStreaming: state.isStreaming,
      error: state.error,
      memoryLoaded: state.memoryLoaded,
      memorySummary: state.memorySummary,
      sendMessage,
      indexProject,
      clearConversation,
      openPatch,
      applyPatch,
      rejectPatch,
    }),
    [state, sendMessage, indexProject, clearConversation, openPatch, applyPatch, rejectPatch]
  )

  return (
    <ResearchKitContext.Provider value={value}>
      {children}
    </ResearchKitContext.Provider>
  )
}

export const useResearchKitContext = () => {
  const context = useContext(ResearchKitContext)
  if (!context) {
    throw new Error(
      'useResearchKitContext is only available inside ResearchKitProvider'
    )
  }
  return context
}
