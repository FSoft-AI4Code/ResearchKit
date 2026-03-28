import React, { useCallback, useEffect, useRef, useState } from 'react'
import MessageInput from './message-input'
import MessageList from './message-list'
import AgentResponse from './agent-response'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  isStreaming?: boolean
}

export default function ResearchKitPanel({ projectId }: { projectId: string }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)

  const handleSend = useCallback(
    async (content: string) => {
      const userMessage: Message = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        timestamp: Date.now(),
      }

      const assistantId = `assistant-${Date.now()}`
      const assistantMessage: Message = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      }

      setMessages(prev => [...prev, userMessage, assistantMessage])
      setIsLoading(true)

      abortControllerRef.current = new AbortController()

      try {
        const response = await fetch(
          `/project/${projectId}/researchkit/chat`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: content, stream: true }),
            signal: abortControllerRef.current.signal,
          }
        )

        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`)
        }

        const reader = response.body?.getReader()
        if (!reader) throw new Error('No response stream')

        const decoder = new TextDecoder()
        let accumulated = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const text = decoder.decode(value, { stream: true })
          const lines = text.split('\n')

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const data = line.slice(6).trim()
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              if (parsed.error) {
                accumulated += `\n\nError: ${parsed.error}`
              } else if (parsed.content) {
                accumulated += parsed.content
              }
            } catch {
              // Skip malformed chunks
            }
          }

          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantId
                ? { ...msg, content: accumulated }
                : msg
            )
          )
        }

        setMessages(prev =>
          prev.map(msg =>
            msg.id === assistantId
              ? { ...msg, isStreaming: false }
              : msg
          )
        )
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          setMessages(prev =>
            prev.map(msg =>
              msg.id === assistantId
                ? {
                    ...msg,
                    content:
                      msg.content ||
                      'Failed to get a response. Please check that the ResearchKit service is running.',
                    isStreaming: false,
                  }
                : msg
            )
          )
        }
      } finally {
        setIsLoading(false)
        abortControllerRef.current = null
      }
    },
    [projectId]
  )

  const handleStop = useCallback(() => {
    abortControllerRef.current?.abort()
  }, [])

  return (
    <div className="researchkit-panel">
      <div className="researchkit-panel-header">
        <h4>ResearchKit</h4>
        <span className="researchkit-badge">AI Assistant</span>
      </div>
      <MessageList messages={messages} />
      <MessageInput
        onSend={handleSend}
        onStop={handleStop}
        isLoading={isLoading}
      />
    </div>
  )
}
