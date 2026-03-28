import { FC, FormEvent, KeyboardEvent, useCallback, useState } from 'react'

type Props = {
  onSend: (message: string) => void
  isStreaming: boolean
  selectedText?: string
  autoDetected?: boolean
}

export const ResearchKitMessageInput: FC<Props> = ({
  onSend,
  isStreaming,
  selectedText,
  autoDetected,
}) => {
  const [input, setInput] = useState('')

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault()
      const trimmed = input.trim()
      if (!trimmed || isStreaming) return
      onSend(trimmed)
      setInput('')
    },
    [input, isStreaming, onSend]
  )

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        const trimmed = input.trim()
        if (trimmed && !isStreaming) {
          onSend(trimmed)
          setInput('')
        }
      }
    },
    [input, isStreaming, onSend]
  )

  const label = autoDetected ? 'Paragraph:' : 'Selected:'

  return (
    <form className="rk-input-form" onSubmit={handleSubmit}>
      {selectedText && (
        <div className="rk-selected-text-preview">
          <span className="rk-selected-label">{label}</span>
          <span className="rk-selected-content">
            {selectedText.length > 100
              ? selectedText.slice(0, 100) + '...'
              : selectedText}
          </span>
        </div>
      )}
      <div className="rk-input-wrapper">
        <textarea
          className="rk-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            selectedText
              ? autoDetected
                ? 'What should I do with this paragraph?'
                : 'What should I do with the selected text?'
              : 'Ask ResearchKit...'
          }
          rows={1}
          disabled={isStreaming}
        />
        <button
          type="submit"
          className="rk-send-button"
          disabled={!input.trim() || isStreaming}
          aria-label="Send message"
        >
          {isStreaming ? '...' : 'Send'}
        </button>
      </div>
    </form>
  )
}
