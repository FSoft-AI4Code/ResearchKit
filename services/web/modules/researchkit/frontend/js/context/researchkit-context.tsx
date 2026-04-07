import {
  createContext,
  FC,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useMemo,
  useRef,
  useState,
} from 'react'
import { EditorView } from '@codemirror/view'
import { useProjectContext } from '@/shared/context/project-context'
import { useEditorViewContext } from '@/features/ide-react/context/editor-view-context'
import { useEditorOpenDocContext } from '@/features/ide-react/context/editor-open-doc-context'
import { useEditorManagerContext } from '@/features/ide-react/context/editor-manager-context'
import { useFileTreeData } from '@/shared/context/file-tree-data-context'
import { findEntityByPath } from '@/features/file-tree/util/path'
import { deleteJSON, getJSON, postJSON } from '@/infrastructure/fetch-json'
import getMeta from '@/utils/meta'
import { Folder } from '../../../../../types/folder'
import { EditorCapture } from '../hooks/use-editor-capture'

export type EditPatch = {
  file_path: string
  selection_from: number
  selection_to: number
  original_text: string
  replacement_text: string
  description: string
  change_type?: 'create' | 'edit' | 'delete'
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
  artifacts?: RKArtifact[]
  output?: string
}

export type RKArtifact = {
  type: string
  [key: string]: unknown
}

type RKResponseChunk = {
  response_id?: string
  content: string
}

export type RKConversationMessage = {
  role: string
  content: string
  response_id?: string
  action_id?: string
  patches?: EditPatch[]
  actions?: RKAction[]
}

type RKConversationResponse = {
  project_id: string
  conversation_id: string
  messages: RKConversationMessage[]
}

export type RKConversationSummary = {
  conversation_id: string
  updated_at: string | null
  message_count: number
  last_message_preview: string | null
}

type RKConversationListResponse = {
  project_id: string
  conversations: RKConversationSummary[]
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
  | { type: 'SET_MESSAGES'; messages: RKMessage[] }
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

export function hydrateConversationMessages(
  conversationId: string,
  messages: RKConversationMessage[],
  baseTime: number = Date.now()
): RKMessage[] {
  return messages
    .filter(
      message =>
        message.role === 'user' || message.role === 'assistant'
    )
    .map((message, index) => ({
      id: `history-${conversationId}-${index}`,
      role: message.role as 'user' | 'assistant',
      content: message.content,
      timestamp: baseTime + index,
      isStreaming: false,
      responseId: message.response_id,
      actionId: message.action_id,
      patches: Array.isArray(message.patches)
        ? message.patches.map(patch => ({ ...patch }))
        : [],
      actions: Array.isArray(message.actions)
        ? message.actions.map(action => ({ ...action }))
        : [],
    }))
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
    case 'SET_MESSAGES':
      return { ...state, messages: action.messages }
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

function stripLeadingSlash(path: string): string {
  return path.replace(/^\/+/, '')
}

function findEntityByNormalizedPath(folder: Folder, path: string) {
  const normalized = stripLeadingSlash(path)
  return (
    findEntityByPath(folder, normalized) ||
    findEntityByPath(folder, `./${normalized}`)
  )
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

function splitProjectPath(path: string): { folderPath: string; fileName: string } | null {
  const parts = stripLeadingSlash(path)
    .split('/')
    .filter(Boolean)
  if (parts.length === 0) {
    return null
  }

  return {
    folderPath: parts.slice(0, -1).join('/'),
    fileName: parts[parts.length - 1],
  }
}

const DEFAULT_CONVERSATION_ID = 'default'
const CONVERSATION_KEY_PREFIX = 'researchkit:conversation:'

function getConversationStorageKey(projectId: string): string {
  return `${CONVERSATION_KEY_PREFIX}${projectId}`
}

function createConversationId(): string {
  return `conv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function getStoredConversationId(projectId: string): string | null {
  if (typeof window === 'undefined') {
    return null
  }

  const storageKey = getConversationStorageKey(projectId)
  const existing = window.localStorage.getItem(storageKey)?.trim()
  return existing || null
}

function setStoredConversationId(projectId: string, conversationId: string): void {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(getConversationStorageKey(projectId), conversationId)
}

function withActiveConversationSummary(
  conversations: RKConversationSummary[],
  activeConversationId: string
): RKConversationSummary[] {
  if (
    conversations.some(
      conversation => conversation.conversation_id === activeConversationId
    )
  ) {
    return conversations
  }

  return [
    {
      conversation_id: activeConversationId,
      updated_at: null,
      message_count: 0,
      last_message_preview: null,
    },
    ...conversations,
  ]
}

type ResearchKitContextValue = {
  messages: RKMessage[]
  conversations: RKConversationSummary[]
  conversationId: string
  isStreaming: boolean
  error: string | null
  memoryLoaded: boolean
  memorySummary: string | null
  sendMessage: (message: string, capture?: EditorCapture) => Promise<void>
  indexProject: () => Promise<void>
  clearConversation: () => Promise<void>
  startNewConversation: () => void
  resumeConversation: (nextConversationId: string) => void
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
  const openDocNameRef = useRef<string | null>(openDocName || null)
  const fileTreeDataRef = useRef(fileTreeData)
  const isStreamingRef = useRef(false)
  const [conversationId, setConversationId] = useState<string>(() =>
    getStoredConversationId(projectId) || DEFAULT_CONVERSATION_ID
  )
  const [conversations, setConversations] = useState<RKConversationSummary[]>([])
  const [state, dispatch] = useReducer(reducer, initialState)

  useEffect(() => {
    editorViewRef.current = view
  }, [view])

  useEffect(() => {
    openDocNameRef.current = openDocName || null
  }, [openDocName])

  useEffect(() => {
    fileTreeDataRef.current = fileTreeData
  }, [fileTreeData])

  useEffect(() => {
    isStreamingRef.current = state.isStreaming
  }, [state.isStreaming])

  useEffect(() => {
    const stored = getStoredConversationId(projectId)
    const nextConversationId = stored || DEFAULT_CONVERSATION_ID
    setConversationId(nextConversationId)
    setStoredConversationId(projectId, nextConversationId)
  }, [projectId])

  const refreshConversations = useCallback(async () => {
    const activeConversationId = conversationId || DEFAULT_CONVERSATION_ID
    try {
      const data = await getJSON<RKConversationListResponse>(
        `/project/${projectId}/researchkit/conversations`
      )
      const loaded = Array.isArray(data.conversations)
        ? data.conversations
        : []

      const storedConversationId = getStoredConversationId(projectId)
      if (
        !storedConversationId &&
        activeConversationId === DEFAULT_CONVERSATION_ID &&
        loaded.length > 0
      ) {
        const latestConversationId = loaded[0].conversation_id
        if (latestConversationId) {
          setStoredConversationId(projectId, latestConversationId)
          setConversationId(latestConversationId)
          setConversations(
            withActiveConversationSummary(loaded, latestConversationId)
          )
          return
        }
      }

      setConversations(withActiveConversationSummary(loaded, activeConversationId))
    } catch (_err) {
      setConversations(withActiveConversationSummary([], activeConversationId))
    }
  }, [projectId, conversationId])

  useEffect(() => {
    refreshConversations()
  }, [refreshConversations])

  useEffect(() => {
    let cancelled = false

    const loadConversation = async () => {
      try {
        const query = encodeURIComponent(conversationId)
        const data = await getJSON<RKConversationResponse>(
          `/project/${projectId}/researchkit/conversation?conversation_id=${query}`
        )
        if (cancelled) return

        const messages = hydrateConversationMessages(
          conversationId,
          data.messages || []
        )
        dispatch({ type: 'SET_MESSAGES', messages })
      } catch (_err) {
        if (!cancelled) {
          dispatch({ type: 'SET_MESSAGES', messages: [] })
        }
      }
    }

    loadConversation()
    return () => {
      cancelled = true
    }
  }, [projectId, conversationId])

  const resumeConversation = useCallback(
    (nextConversationId: string) => {
      const normalized = nextConversationId.trim()
      if (!normalized || normalized === conversationId || isStreamingRef.current) {
        return
      }

      setStoredConversationId(projectId, normalized)
      setConversationId(normalized)
      dispatch({ type: 'CLEAR_ERROR' })
      dispatch({ type: 'CLEAR_MESSAGES' })
    },
    [projectId, conversationId]
  )

  const startNewConversation = useCallback(() => {
    if (isStreamingRef.current) {
      return
    }
    const nextConversationId = createConversationId()
    setStoredConversationId(projectId, nextConversationId)
    setConversationId(nextConversationId)
    setConversations(prev =>
      withActiveConversationSummary(prev, nextConversationId)
    )
    dispatch({ type: 'CLEAR_ERROR' })
    dispatch({ type: 'CLEAR_MESSAGES' })
  }, [projectId])

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
      const docContent = capture?.docContent || null
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
              conversation_id: conversationId,
              selected_text: selectedText,
              file_path: filePath,
              selection_from: selectionFrom,
              selection_to: selectionTo,
              cursor_line: cursorLine,
              line_from: lineFrom,
              line_to: lineTo,
              current_file_content:
                filePath && docContent ? { [filePath]: docContent } : undefined,
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
          if (currentEventType === 'done') {
            dispatch({ type: 'END_STREAMING' })
            dataLines = []
            return
          }

          if (dataLines.length === 0) return

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
          } else if (currentEventType === 'edit') {
            // `edit` is an internal stream event and should not be rendered as chat text.
          } else if (currentEventType === 'message' && content.length > 0) {
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
      } catch (err) {
        dispatch({
          type: 'SET_ERROR',
          error: err instanceof Error ? err.message : 'Failed to send message',
        })
      } finally {
        refreshConversations()
      }
    },
    [projectId, conversationId, refreshConversations]
  )

  const openPatch = useCallback(
    async (messageId: string, patchIndex: number) => {
      const msg = state.messages.find(m => m.id === messageId)
      const patch = msg?.patches?.[patchIndex]
      if (!patch) return

      if (patch.change_type === 'create') {
        dispatch({
          type: 'SET_ERROR',
          error: `Accept this patch to create "${patch.file_path}" in the project.`,
        })
        return
      }

      const found = findEntityByNormalizedPath(fileTreeData, patch.file_path)

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

  const waitForEntityByPath = useCallback(
    async (
      path: string,
      expectedType: 'doc' | 'folder',
      timeoutMs = 3000
    ) => {
      const startedAt = Date.now()
      while (Date.now() - startedAt < timeoutMs) {
        const found = findEntityByNormalizedPath(fileTreeDataRef.current, path)
        if (found?.type === expectedType) {
          return found
        }
        await new Promise(resolve => window.setTimeout(resolve, 50))
      }
      return null
    },
    []
  )

  const waitForOpenPatchDocument = useCallback(
    async (patchPath: string, timeoutMs = 3000) => {
      const startedAt = Date.now()
      while (Date.now() - startedAt < timeoutMs) {
        const currentView = editorViewRef.current
        if (
          currentView &&
          isPatchForOpenDocument(patchPath, openDocNameRef.current)
        ) {
          return currentView
        }
        await new Promise(resolve => window.setTimeout(resolve, 50))
      }
      return null
    },
    []
  )

  const ensureDocumentForCreatePatch = useCallback(
    async (patch: EditPatch) => {
      const pathParts = splitProjectPath(patch.file_path)
      if (!pathParts) {
        throw new Error(`Invalid file path "${patch.file_path}".`)
      }

      const existingDoc = findEntityByNormalizedPath(
        fileTreeDataRef.current,
        patch.file_path
      )
      if (existingDoc?.type === 'doc') {
        return existingDoc.entity._id
      }
      if (existingDoc) {
        throw new Error(`"${patch.file_path}" already exists and is not a document.`)
      }

      let parentFolderId = fileTreeDataRef.current._id
      if (pathParts.folderPath) {
        let currentFolderId = parentFolderId
        let currentPath = ''
        for (const segment of pathParts.folderPath.split('/')) {
          currentPath = currentPath ? `${currentPath}/${segment}` : segment
          const existingFolder = findEntityByNormalizedPath(
            fileTreeDataRef.current,
            currentPath
          )
          if (existingFolder?.type === 'folder') {
            currentFolderId = existingFolder.entity._id
            continue
          }
          if (existingFolder) {
            throw new Error(`"${currentPath}" exists and is not a folder.`)
          }

          const createdFolder = await postJSON<{ _id: string }>(
            `/project/${projectId}/folder`,
            {
              body: {
                name: segment,
                parent_folder_id: currentFolderId,
              },
            }
          )
          currentFolderId = createdFolder._id
          const syncedFolder = await waitForEntityByPath(currentPath, 'folder')
          if (syncedFolder?.type === 'folder') {
            currentFolderId = syncedFolder.entity._id
          }
        }
        parentFolderId = currentFolderId
      }

      const createdDoc = await postJSON<{ _id: string }>(
        `/project/${projectId}/doc`,
        {
          body: {
            name: pathParts.fileName,
            parent_folder_id: parentFolderId,
          },
        }
      )

      const syncedDoc = await waitForEntityByPath(patch.file_path, 'doc')
      if (syncedDoc?.type === 'doc') {
        return syncedDoc.entity._id
      }

      return createdDoc._id
    },
    [projectId, waitForEntityByPath]
  )

  const applyPatch = useCallback(
    (messageId: string, patchIndex: number) => {
      void (async () => {
        // Find the patch
        const msg = state.messages.find(m => m.id === messageId)
        if (!msg?.patches?.[patchIndex]) return
        const patch = msg.patches[patchIndex]

        let ev = editorViewRef.current
        if (!ev && patch.change_type !== 'create') {
          dispatch({ type: 'SET_ERROR', error: 'Editor not available' })
          return
        }

        if (patch.change_type === 'create') {
          try {
            const docId = await ensureDocumentForCreatePatch(patch)
            await openDocWithId(docId, { gotoOffset: patch.selection_from })
            ev = await waitForOpenPatchDocument(patch.file_path)
          } catch (error) {
            dispatch({
              type: 'SET_ERROR',
              error:
                error instanceof Error
                  ? error.message
                  : `Failed to create "${patch.file_path}".`,
            })
            return
          }

          if (!ev) {
            dispatch({
              type: 'SET_ERROR',
              error: `Created "${patch.file_path}" but could not open it in the editor.`,
            })
            return
          }
        } else if (
          !isPatchForOpenDocument(
            patch.file_path,
            openDocNameRef.current || null
          )
        ) {
          dispatch({
            type: 'SET_ERROR',
            error: `Open "${patch.file_path}" in the editor before applying this patch.`,
          })
          return
        }

        if (!ev) {
          dispatch({ type: 'SET_ERROR', error: 'Editor not available' })
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

        dispatch({
          type: 'UPDATE_PATCH_STATUS',
          messageId,
          patchIndex,
          status: 'accepted',
        })
      })()
    },
    [
      state.messages,
      ensureDocumentForCreatePatch,
      openDocWithId,
      waitForOpenPatchDocument,
    ]
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
      const query = encodeURIComponent(conversationId)
      await deleteJSON(
        `/project/${projectId}/researchkit/conversation?conversation_id=${query}`
      )
      dispatch({ type: 'CLEAR_MESSAGES' })
      refreshConversations()
    } catch (err) {
      dispatch({
        type: 'SET_ERROR',
        error: 'Failed to clear conversation',
      })
    }
  }, [projectId, conversationId, refreshConversations])

  const value = useMemo(
    () => ({
      messages: state.messages,
      conversations,
      conversationId,
      isStreaming: state.isStreaming,
      error: state.error,
      memoryLoaded: state.memoryLoaded,
      memorySummary: state.memorySummary,
      sendMessage,
      indexProject,
      clearConversation,
      startNewConversation,
      resumeConversation,
      openPatch,
      applyPatch,
      rejectPatch,
    }),
    [
      state,
      conversations,
      conversationId,
      sendMessage,
      indexProject,
      clearConversation,
      startNewConversation,
      resumeConversation,
      openPatch,
      applyPatch,
      rejectPatch,
    ]
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
