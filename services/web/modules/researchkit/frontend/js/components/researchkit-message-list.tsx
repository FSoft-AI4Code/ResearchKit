import { FC, useEffect, useRef } from 'react'
import { RKMessage, useResearchKitContext } from '../context/researchkit-context'
import { ResearchKitDiffView } from './researchkit-diff-view'

const MessageBubble: FC<{ message: RKMessage }> = ({ message }) => {
  const { applyPatch, rejectPatch } = useResearchKitContext()
  const isUser = message.role === 'user'

  return (
    <div className={`rk-message rk-message-${message.role}`}>
      <div className="rk-message-header">
        <span className="rk-message-sender">
          {isUser ? 'You' : 'ResearchKit'}
        </span>
      </div>
      {message.patches && message.patches.length > 0 && (
        <div className="rk-message-patches">
          {message.patches.map((patch, idx) => (
            <ResearchKitDiffView
              key={`${message.id}-patch-${idx}`}
              patch={patch}
              messageId={message.id}
              patchIndex={idx}
              onAccept={applyPatch}
              onReject={rejectPatch}
            />
          ))}
        </div>
      )}
      <div className="rk-message-content">
        {message.content || (message.isStreaming ? '...' : '')}
        {message.isStreaming && <span className="rk-cursor-blink">|</span>}
      </div>
    </div>
  )
}

export const ResearchKitMessageList: FC<{ messages: RKMessage[] }> = ({
  messages,
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
          Your AI research assistant. Select text in the editor and ask me to
          paraphrase, fix grammar, draft sections, or help with your paper.
        </div>
        <div className="rk-empty-state-hints">
          <div className="rk-hint">Select text + "paraphrase this"</div>
          <div className="rk-hint">"Draft an introduction for..."</div>
          <div className="rk-hint">"Fix grammar in this paragraph"</div>
        </div>
      </div>
    )
  }

  return (
    <div className="rk-message-list">
      {messages.map(msg => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
