import React, { useEffect, useRef } from 'react'
import AgentResponse from './agent-response'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  isStreaming?: boolean
}

interface MessageListProps {
  messages: Message[]
}

export default function MessageList({ messages }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) {
    return (
      <div className="researchkit-messages researchkit-empty">
        <div className="researchkit-welcome">
          <h3>ResearchKit Assistant</h3>
          <p>
            I can help you write and improve your academic paper. Try asking me
            to:
          </p>
          <ul>
            <li>Paraphrase or improve a paragraph</li>
            <li>Fix grammar in a section</li>
            <li>Draft a section from an outline</li>
            <li>Find related work (coming soon)</li>
            <li>Generate figures from data (coming soon)</li>
            <li>Review your paper (coming soon)</li>
          </ul>
        </div>
      </div>
    )
  }

  return (
    <div className="researchkit-messages">
      {messages.map(msg => (
        <div
          key={msg.id}
          className={`researchkit-message researchkit-message-${msg.role}`}
        >
          <div className="researchkit-message-header">
            <span className="researchkit-message-role">
              {msg.role === 'user' ? 'You' : 'ResearchKit'}
            </span>
          </div>
          <div className="researchkit-message-content">
            {msg.role === 'assistant' ? (
              <AgentResponse
                content={msg.content}
                isStreaming={msg.isStreaming}
              />
            ) : (
              <p>{msg.content}</p>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
