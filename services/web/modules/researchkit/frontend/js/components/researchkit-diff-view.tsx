import { FC, useCallback, useState } from 'react'
import { EditPatch } from '../context/researchkit-context'

const MAX_PREVIEW_LINES = 3

type Props = {
  patch: EditPatch
  messageId: string
  patchIndex: number
  onOpen: (messageId: string, patchIndex: number) => void
  onAccept: (messageId: string, patchIndex: number) => void
  onReject: (messageId: string, patchIndex: number) => void
  alwaysExpanded?: boolean
}

export const ResearchKitDiffView: FC<Props> = ({
  patch,
  messageId,
  patchIndex,
  onOpen,
  onAccept,
  onReject,
  alwaysExpanded,
}) => {
  const status = patch._status || 'pending'
  const [expanded, setExpanded] = useState(false)
  const isCreatePatch = patch.change_type === 'create'

  const handleAccept = useCallback(
    () => onAccept(messageId, patchIndex),
    [messageId, patchIndex, onAccept]
  )
  const handleReject = useCallback(
    () => onReject(messageId, patchIndex),
    [messageId, patchIndex, onReject]
  )
  const handleOpen = useCallback(
    () => onOpen(messageId, patchIndex),
    [messageId, onOpen, patchIndex]
  )

  const originalLines = patch.original_text.split('\n')
  const replacementLines = patch.replacement_text.split('\n')
  const isLong =
    !alwaysExpanded &&
    (originalLines.length > MAX_PREVIEW_LINES ||
    replacementLines.length > MAX_PREVIEW_LINES)

  const showFull = alwaysExpanded || expanded
  const displayOriginal = showFull
    ? patch.original_text
    : originalLines.slice(0, MAX_PREVIEW_LINES).join('\n') +
      (originalLines.length > MAX_PREVIEW_LINES ? '\n\u2026' : '')
  const displayReplacement = showFull
    ? patch.replacement_text
    : replacementLines.slice(0, MAX_PREVIEW_LINES).join('\n') +
      (replacementLines.length > MAX_PREVIEW_LINES ? '\n\u2026' : '')

  return (
    <div className={`rk-diff rk-diff-${status}`}>
      <div className="rk-diff-header">
        <div className="rk-diff-meta">
          {isCreatePatch ? (
            <span className="rk-diff-file-link">{patch.file_path}</span>
          ) : (
            <button type="button" className="rk-diff-file-link" onClick={handleOpen}>
              {patch.file_path}
            </button>
          )}
          {isCreatePatch && (
            <span className="rk-diff-description">New file</span>
          )}
          <span className="rk-diff-description">{patch.description}</span>
        </div>
        {!isCreatePatch && (
          <button type="button" className="rk-diff-open-btn" onClick={handleOpen}>
            Open in editor
          </button>
        )}
      </div>
      <div className="rk-diff-body">
        <div className="rk-diff-line rk-diff-removed">
          <span className="rk-diff-gutter">-</span>
          <pre className="rk-diff-text">{displayOriginal}</pre>
        </div>
        <div className="rk-diff-line rk-diff-added">
          <span className="rk-diff-gutter">+</span>
          <pre className="rk-diff-text">{displayReplacement}</pre>
        </div>
      </div>
      {isLong && (
        <button
          className="rk-diff-toggle"
          onClick={() => setExpanded(prev => !prev)}
        >
          {expanded ? 'Show less' : 'Show full diff'}
        </button>
      )}
      {status === 'pending' && (
        <div className="rk-diff-actions">
          <button className="rk-diff-accept-btn" onClick={handleAccept}>
            Accept
          </button>
          <button className="rk-diff-reject-btn" onClick={handleReject}>
            Reject
          </button>
        </div>
      )}
      {status === 'accepted' && (
        <div className="rk-diff-status rk-diff-status-accepted">Applied</div>
      )}
      {status === 'rejected' && (
        <div className="rk-diff-status rk-diff-status-rejected">Dismissed</div>
      )}
    </div>
  )
}
