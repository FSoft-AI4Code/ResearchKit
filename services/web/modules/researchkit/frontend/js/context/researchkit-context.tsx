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
  _status?: 'pending' | 'accepted' | 'rejected'
}

export type RKMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  isStreaming?: boolean
  patches?: EditPatch[]
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
  | { type: 'APPEND_STREAM_CHUNK'; chunk: string }
  | { type: 'ADD_PATCH'; patch: EditPatch }
  | { type: 'UPDATE_PATCH_STATUS'; messageId: string; patchIndex: number; status: 'accepted' | 'rejected' }
  | { type: 'END_STREAMING' }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'CLEAR_MESSAGES' }
  | { type: 'SET_MEMORY'; summary: string }

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'ADD_USER_MESSAGE':
      return { ...state, messages: [...state.messages, action.message] }
    case 'START_STREAMING': {
      const assistantMsg: RKMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
        patches: [],
      }
      return {
        ...state,
        isStreaming: true,
        error: null,
        messages: [...state.messages, assistantMsg],
      }
    }
    case 'APPEND_STREAM_CHUNK': {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + action.chunk }
      }
      return { ...state, messages: msgs }
    }
    case 'ADD_PATCH': {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        const patches = [...(last.patches || []), { ...action.patch, _status: 'pending' as const }]
        msgs[msgs.length - 1] = { ...last, patches }
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
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, isStreaming: false }
      }
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

type ResearchKitContextValue = {
  messages: RKMessage[]
  isStreaming: boolean
  error: string | null
  memoryLoaded: boolean
  memorySummary: string | null
  sendMessage: (message: string, capture?: EditorCapture) => Promise<void>
  indexProject: () => Promise<void>
  clearConversation: () => Promise<void>
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
  const editorViewRef = useRef<EditorView | null>(view)
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    editorViewRef.current = view
  }, [view])

  const sendMessage = useCallback(
    async (message: string, capture?: EditorCapture) => {
      const selectedText = capture?.selectedText || null
      const filePath = capture?.filePath || null
      const selectionFrom = capture?.selectionFrom ?? null
      const selectionTo = capture?.selectionTo ?? null

      const contextLabel = capture?.autoDetected ? 'Paragraph' : 'Selected text'
      const userMsg: RKMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: selectedText
          ? `**${contextLabel}:**\n\`\`\`latex\n${selectedText}\n\`\`\`\n\n${message}`
          : message,
        timestamp: Date.now(),
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

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })

          // Parse SSE events from buffer
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            const trimmedLine = line.replace(/\r$/, '')

            if (trimmedLine.startsWith('event:')) {
              currentEventType = trimmedLine.slice(6).trim()
              continue
            }

            if (trimmedLine.startsWith('data:')) {
              const data = trimmedLine.slice(5)
              const content = data.startsWith(' ') ? data.slice(1) : data

              if (currentEventType === 'done') {
                dispatch({ type: 'END_STREAMING' })
                return
              }

              if (currentEventType === 'patch') {
                try {
                  const patch = JSON.parse(content) as EditPatch
                  dispatch({ type: 'ADD_PATCH', patch })
                } catch (e) {
                  console.error('Failed to parse patch event', e)
                }
              } else if (content.length > 0) {
                dispatch({ type: 'APPEND_STREAM_CHUNK', chunk: content })
              }

              currentEventType = 'message'
            }
          }
        }

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
    [state.messages]
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
      applyPatch,
      rejectPatch,
    }),
    [state, sendMessage, indexProject, clearConversation, applyPatch, rejectPatch]
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
