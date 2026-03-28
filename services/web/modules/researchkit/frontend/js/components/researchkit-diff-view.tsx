import { FC, useCallback } from 'react'
import { EditPatch } from '../context/researchkit-context'

type Props = {
  patch: EditPatch
  messageId: string
  patchIndex: number
  onAccept: (messageId: string, patchIndex: number) => void
  onReject: (messageId: string, patchIndex: number) => void
}

export const ResearchKitDiffView: FC<Props> = ({
  patch,
  messageId,
  patchIndex,
  onAccept,
  onReject,
}) => {
  const status = patch._status || 'pending'
  const handleAccept = useCallback(
    () => onAccept(messageId, patchIndex),
    [messageId, patchIndex, onAccept]
  )
  const handleReject = useCallback(
    () => onReject(messageId, patchIndex),
    [messageId, patchIndex, onReject]
  )

  return (
    <div className={`rk-diff rk-diff-${status}`}>
      <div className="rk-diff-header">
        <span className="rk-diff-file">{patch.file_path}</span>
        <span className="rk-diff-description">{patch.description}</span>
      </div>
      <div className="rk-diff-body">
        <div className="rk-diff-line rk-diff-removed">
          <span className="rk-diff-gutter">-</span>
          <pre className="rk-diff-text">{patch.original_text}</pre>
        </div>
        <div className="rk-diff-line rk-diff-added">
          <span className="rk-diff-gutter">+</span>
          <pre className="rk-diff-text">{patch.replacement_text}</pre>
        </div>
      </div>
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
