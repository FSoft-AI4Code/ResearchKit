import { FC, useEffect, useRef } from 'react'
import {
  RKAction,
  RKArtifact,
  RKMessage,
} from '../context/researchkit-context'
import { ResearchKitDiffView } from './researchkit-diff-view'

type TextSegment = { type: 'text' | 'strong' | 'code'; value: string }
type MessageBlock =
  | { type: 'paragraph'; lines: string[] }
  | { type: 'unordered-list'; items: string[] }
  | { type: 'ordered-list'; items: string[] }
  | { type: 'code'; language: string; content: string }

function parseInlineSegments(text: string): TextSegment[] {
  const segments: TextSegment[] = []
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g
  let last = 0
  let m: RegExpExecArray | null = re.exec(text)

  while (m) {
    if (m.index > last) {
      segments.push({ type: 'text', value: text.slice(last, m.index) })
    }

    if (m[2] != null) {
      segments.push({ type: 'strong', value: m[2] })
    } else if (m[3] != null) {
      segments.push({ type: 'code', value: m[3] })
    }

    last = m.index + m[0].length
    m = re.exec(text)
  }

  if (last < text.length) {
    segments.push({ type: 'text', value: text.slice(last) })
  }

  return segments
}

function renderInlineSegments(
  text: string,
  keyPrefix: string
) {
  return parseInlineSegments(text).map((segment, idx) => {
    const key = `${keyPrefix}-${idx}`
    if (segment.type === 'strong') {
      return <strong key={key}>{segment.value}</strong>
    }
    if (segment.type === 'code') {
      return <code key={key} className="rk-inline-code">{segment.value}</code>
    }
    return <span key={key}>{segment.value}</span>
  })
}

function parseBlocks(content: string): MessageBlock[] {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: MessageBlock[] = []

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    if (!line.trim()) {
      i++
      continue
    }

    if (/^\s*```/.test(line)) {
      const language = line.replace(/^\s*```/, '').trim()
      i++
      const codeLines: string[] = []
      while (i < lines.length && !/^\s*```/.test(lines[i])) {
        codeLines.push(lines[i])
        i++
      }
      if (i < lines.length) i++
      blocks.push({
        type: 'code',
        language,
        content: codeLines.join('\n'),
      })
      continue
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        const match = lines[i].match(/^(\s*)[-*+]\s+(.*)$/)
        items.push(match ? `${match[1]}${match[2]}` : lines[i])
        i++
      }
      blocks.push({ type: 'unordered-list', items })
      continue
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const match = lines[i].match(/^(\s*)\d+\.\s+(.*)$/)
        items.push(match ? `${match[1]}${match[2]}` : lines[i])
        i++
      }
      blocks.push({ type: 'ordered-list', items })
      continue
    }

    const paragraphLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*```/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      paragraphLines.push(lines[i])
      i++
    }
    blocks.push({ type: 'paragraph', lines: paragraphLines })
  }

  return blocks
}

const RichText: FC<{ content: string }> = ({ content }) => {
  const blocks = parseBlocks(content)

  return (
    <div className="rk-rich-content">
      {blocks.map((block, idx) => {
        if (block.type === 'code') {
          return (
            <pre key={`code-${idx}`} className="rk-rich-code">
              <code>{block.content}</code>
            </pre>
          )
        }

        if (block.type === 'unordered-list' || block.type === 'ordered-list') {
          const ListTag = block.type === 'ordered-list' ? 'ol' : 'ul'
          return (
            <ListTag key={`list-${idx}`} className="rk-rich-list">
              {block.items.map((item, itemIdx) => (
                <li key={`item-${idx}-${itemIdx}`}>
                  {renderInlineSegments(item, `list-${idx}-${itemIdx}`)}
                </li>
              ))}
            </ListTag>
          )
        }

        return (
          <p key={`p-${idx}`} className="rk-rich-paragraph">
            {renderInlineSegments(block.lines.join('\n'), `p-${idx}`)}
          </p>
        )
      })}
    </div>
  )
}

function formatActionStatus(status: string): string {
  if (status === 'started') return 'Working'
  if (status === 'completed') return 'Completed'
  if (status === 'error') return 'Error'
  if (status === 'warning') return 'Warning'
  return status
}

function summarizeAssistantMessage(
  actions: RKAction[],
  isStreaming: boolean
): string | null {
  if (isStreaming) {
    return 'Working'
  }

  if (actions.length === 0) {
    return null
  }

  const lastAction = [...actions].reverse().find(Boolean)
  if (!lastAction) {
    return null
  }

  return `${actions.length} action${actions.length === 1 ? '' : 's'} · ${formatActionStatus(lastAction.status)}`
}

function collectArtifacts(actions: RKAction[]): RKArtifact[] {
  const collected: RKArtifact[] = []
  for (const action of actions) {
    if (action.status !== 'completed' || !Array.isArray(action.artifacts)) {
      continue
    }
    for (const artifact of action.artifacts) {
      if (artifact && typeof artifact === 'object' && typeof artifact.type === 'string') {
        collected.push(artifact)
      }
    }
  }
  return collected
}

const ResearchArtifactCard: FC<{ artifact: RKArtifact }> = ({ artifact }) => {
  if (artifact.type === 'literature_search_result') {
    const query =
      typeof artifact.query === 'string' ? artifact.query : 'Unknown query'
    const resultCount =
      typeof artifact.result_count === 'number' ? artifact.result_count : 0
    const papers = Array.isArray(artifact.papers)
      ? artifact.papers.filter(item => item && typeof item === 'object')
      : []
    const bibtex = typeof artifact.bibtex === 'string' ? artifact.bibtex.trim() : ''

    return (
      <div className="rk-artifact-card">
        <div className="rk-artifact-title">Literature Search</div>
        <div className="rk-artifact-meta">
          <span className="rk-artifact-chip">query</span>
          <code>{query}</code>
        </div>
        <div className="rk-artifact-meta">
          <span className="rk-artifact-chip">results</span>
          <span>{resultCount}</span>
        </div>
        {papers.length > 0 && (
          <ul className="rk-artifact-list-items">
            {papers.slice(0, 5).map((paper, index) => {
              const title =
                typeof (paper as { title?: unknown }).title === 'string'
                  ? ((paper as { title: string }).title || 'Untitled paper')
                  : 'Untitled paper'
              const year = (paper as { year?: unknown }).year
              return (
                <li key={`paper-${index}`}>
                  {title}
                  {typeof year === 'number' && year > 0 ? ` (${year})` : ''}
                </li>
              )
            })}
          </ul>
        )}
        {bibtex && (
          <details className="rk-artifact-details">
            <summary>BibTeX</summary>
            <pre>{bibtex}</pre>
          </details>
        )}
      </div>
    )
  }

  if (artifact.type === 'citation_verification_result') {
    const summary =
      artifact.summary && typeof artifact.summary === 'object'
        ? (artifact.summary as Record<string, unknown>)
        : {}
    const verified = typeof summary.verified === 'number' ? summary.verified : 0
    const suspicious = typeof summary.suspicious === 'number' ? summary.suspicious : 0
    const hallucinated = typeof summary.hallucinated === 'number' ? summary.hallucinated : 0
    const integrityScore =
      typeof summary.integrity_score === 'number' ? summary.integrity_score : null

    return (
      <div className="rk-artifact-card">
        <div className="rk-artifact-title">Citation Verification</div>
        <div className="rk-artifact-grid">
          <div className="rk-artifact-stat">
            <span className="rk-artifact-chip">verified</span>
            <strong>{verified}</strong>
          </div>
          <div className="rk-artifact-stat">
            <span className="rk-artifact-chip">suspicious</span>
            <strong>{suspicious}</strong>
          </div>
          <div className="rk-artifact-stat">
            <span className="rk-artifact-chip">hallucinated</span>
            <strong>{hallucinated}</strong>
          </div>
          <div className="rk-artifact-stat">
            <span className="rk-artifact-chip">integrity</span>
            <strong>{integrityScore != null ? integrityScore.toFixed(3) : 'n/a'}</strong>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="rk-artifact-card">
      <div className="rk-artifact-title">Artifact</div>
      <code>{artifact.type}</code>
    </div>
  )
}

type MessageBubbleProps = {
  message: RKMessage
  onOpenPatch: (messageId: string, patchIndex: number) => void
  onAcceptPatch: (messageId: string, patchIndex: number) => void
  onRejectPatch: (messageId: string, patchIndex: number) => void
}

const MessageBubble: FC<MessageBubbleProps> = ({
  message,
  onOpenPatch,
  onAcceptPatch,
  onRejectPatch,
}) => {
  const isUser = message.role === 'user'
  const actions = message.actions || []
  const patches = message.patches || []
  const artifacts = collectArtifacts(actions)
  const hasAssistantMetadata =
    actions.length > 0 || patches.length > 0 || artifacts.length > 0
  const showAssistantPlaceholder =
    !isUser && !message.content && !hasAssistantMetadata
  const ctx = message.context
  const assistantSummary = summarizeAssistantMessage(actions, Boolean(message.isStreaming))

  const hasContext = isUser && ctx && (ctx.selectedText || ctx.cursorLine)
  const contextLabel = ctx?.selectedText
    ? ctx.lineFrom != null && ctx.lineTo != null
      ? ctx.lineFrom === ctx.lineTo
        ? `Line ${ctx.lineFrom}`
        : `Lines ${ctx.lineFrom}\u2013${ctx.lineTo}`
      : 'Selected text'
    : ctx?.cursorLine
      ? `Line ${ctx.cursorLine}`
      : null
  const contextFileName = ctx?.filePath ? ctx.filePath.split('/').pop() : null

  return (
    <div className={`rk-message rk-message-${message.role}`}>
      <div className="rk-message-header">
        <span className="rk-message-sender">
          {isUser ? 'You' : 'ResearchKit'}
        </span>
        {!isUser && assistantSummary && (
          <span className="rk-step-chip">{assistantSummary}</span>
        )}
      </div>
      <div className="rk-message-content">
        {isUser ? (
          <>
            {hasContext && (
              <div className="rk-user-context">
                <div className="rk-context-meta">
                  <span className="rk-context-meta-label">{contextLabel}</span>
                  {contextFileName && (
                    <span className="rk-context-meta-file">{contextFileName}</span>
                  )}
                </div>
                {ctx!.selectedText && (
                  <details className="rk-user-context-details">
                    <summary>
                      Attached context ({ctx!.selectedText.length} chars)
                    </summary>
                    <pre>{ctx!.selectedText}</pre>
                  </details>
                )}
              </div>
            )}
            <div className="rk-user-request">{message.content}</div>
          </>
        ) : message.content ? (
          <RichText content={message.content} />
        ) : showAssistantPlaceholder ? (
          <div className="rk-assistant-placeholder">
            {message.isStreaming ? 'Preparing response...' : 'No reasoning captured.'}
          </div>
        ) : null}
        {message.isStreaming && (message.content || showAssistantPlaceholder) && (
          <span className="rk-cursor-blink">|</span>
        )}
      </div>
      {!isUser && actions.length > 0 && (
        <details className="rk-message-section">
          <summary>Actions ({actions.length})</summary>
          <div className="rk-action-list">
            {actions.map((action, actionIndex) => (
              <div
                key={`${message.id}-action-${actionIndex}`}
                className="rk-action-item"
              >
                <span
                  className={`rk-action-status rk-action-status-${action.status}`}
                >
                  {formatActionStatus(action.status)}
                </span>
                <div className="rk-action-body">
                  <div className="rk-action-headline">
                    <span className="rk-action-main">{action.tool}</span>
                    {action.sequence != null && (
                      <span className="rk-action-sequence">#{action.sequence}</span>
                    )}
                    {action.patch_count != null && action.patch_count > 0 && (
                      <span className="rk-action-patch-count">
                        {action.patch_count} patch{action.patch_count === 1 ? '' : 'es'}
                      </span>
                    )}
                  </div>
                  {action.command && (
                    <code className="rk-action-command">{action.command}</code>
                  )}
                  <div className="rk-action-detail">{action.detail}</div>
                  {action.output && (
                    <details className="rk-action-output">
                      <summary>Output</summary>
                      <pre>{action.output}</pre>
                    </details>
                  )}
                </div>
              </div>
            ))}
          </div>
        </details>
      )}
      {!isUser && artifacts.length > 0 && (
        <details className="rk-message-section rk-message-section-artifacts" open>
          <summary>Research artifacts ({artifacts.length})</summary>
          <div className="rk-artifact-cards">
            {artifacts.map((artifact, artifactIndex) => (
              <ResearchArtifactCard
                key={`${message.id}-artifact-${artifactIndex}`}
                artifact={artifact}
              />
            ))}
          </div>
        </details>
      )}
      {!isUser && patches.length > 0 && (
        <details className="rk-message-section rk-message-section-patches">
          <summary>Diff patches ({patches.length})</summary>
          <div className="rk-message-patches">
            {patches.map((patch, patchIndex) => (
              <ResearchKitDiffView
                key={`${message.id}-patch-${patchIndex}`}
                patch={patch}
                messageId={message.id}
                patchIndex={patchIndex}
                onOpen={onOpenPatch}
                onAccept={onAcceptPatch}
                onReject={onRejectPatch}
              />
            ))}
          </div>
        </details>
      )}
    </div>
  )
}

type MessageListProps = {
  messages: RKMessage[]
  onOpenPatch: (messageId: string, patchIndex: number) => void
  onAcceptPatch: (messageId: string, patchIndex: number) => void
  onRejectPatch: (messageId: string, patchIndex: number) => void
}

export const ResearchKitMessageList: FC<MessageListProps> = ({
  messages,
  onOpenPatch,
  onAcceptPatch,
  onRejectPatch,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="rk-empty-state">
        <div className="rk-empty-state-title">ResearchKit</div>
        <div className="rk-empty-state-body">
          Your AI research assistant. Each response shows markdown reasoning,
          collapsible actions, and hidden reviewable patches.
        </div>
        <div className="rk-empty-state-hints">
          <div className="rk-hint">"Find all \\todo and fix them"</div>
          <div className="rk-hint">"Normalize refs.bib keys"</div>
          <div className="rk-hint">"Refactor intro and related work flow"</div>
        </div>
      </div>
    )
  }

  return (
    <div className="rk-message-list">
      {messages.map(msg => (
        <MessageBubble
          key={msg.id}
          message={msg}
          onOpenPatch={onOpenPatch}
          onAcceptPatch={onAcceptPatch}
          onRejectPatch={onRejectPatch}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
