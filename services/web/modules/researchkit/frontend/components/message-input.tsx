import React, { useCallback, useRef, useState } from 'react'

interface MessageInputProps {
  onSend: (message: string) => void
  onStop: () => void
  isLoading: boolean
}

export default function MessageInput({
  onSend,
  onStop,
  isLoading,
}: MessageInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault()
      const trimmed = input.trim()
      if (!trimmed || isLoading) return
      onSend(trimmed)
      setInput('')
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    },
    [input, isLoading, onSend]
  )

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit(e)
      }
    },
    [handleSubmit]
  )

  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setInput(e.target.value)
      const el = e.target
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 150)}px`
    },
    []
  )

  return (
    <form className="researchkit-input" onSubmit={handleSubmit}>
      <textarea
        ref={textareaRef}
        value={input}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder="Ask ResearchKit to help with your paper..."
        rows={1}
        disabled={isLoading}
        className="researchkit-input-textarea"
      />
      {isLoading ? (
        <button
          type="button"
          onClick={onStop}
          className="researchkit-input-btn researchkit-stop-btn"
          title="Stop generating"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          disabled={!input.trim()}
          className="researchkit-input-btn researchkit-send-btn"
          title="Send message"
        >
          Send
        </button>
      )}
    </form>
  )
}
