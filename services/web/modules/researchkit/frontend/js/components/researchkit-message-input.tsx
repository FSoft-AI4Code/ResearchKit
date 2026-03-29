import { FC, FormEvent, KeyboardEvent, useCallback, useState } from 'react'

type Props = {
  onSend: (message: string) => void
  isStreaming: boolean
  selectedText?: string
  cursorLine?: number | null
  lineFrom?: number | null
  lineTo?: number | null
  filePath?: string | null
}

export const ResearchKitMessageInput: FC<Props> = ({
  onSend,
  isStreaming,
  selectedText,
  cursorLine,
  lineFrom,
  lineTo,
  filePath,
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

  const fileName = filePath ? filePath.split('/').pop() : null
  const hasContext = Boolean(selectedText || cursorLine)

  const contextLabel = selectedText
    ? lineFrom != null && lineTo != null
      ? lineFrom === lineTo
        ? `Line ${lineFrom}`
        : `Lines ${lineFrom}\u2013${lineTo}`
      : 'Selected'
    : cursorLine
      ? `Line ${cursorLine}`
      : null

  return (
    <form className="rk-input-form" onSubmit={handleSubmit}>
      {hasContext && (
        <div className="rk-context-pill">
          <span className="rk-context-pill-label">{contextLabel}</span>
          {fileName && <span className="rk-context-pill-file">{fileName}</span>}
          {selectedText && (
            <span className="rk-context-pill-preview">
              {selectedText.length > 60
                ? selectedText.slice(0, 60) + '...'
                : selectedText}
            </span>
          )}
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
              ? 'What should I do with the selected text?'
              : cursorLine
                ? 'Ask about this line...'
                : 'Ask ResearchKit...'
          }
          rows={4}
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
