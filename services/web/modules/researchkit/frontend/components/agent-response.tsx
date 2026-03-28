import React from 'react'

interface AgentResponseProps {
  content: string
  isStreaming?: boolean
}

export default function AgentResponse({
  content,
  isStreaming,
}: AgentResponseProps) {
  if (!content && isStreaming) {
    return (
      <div className="researchkit-response researchkit-thinking">
        <span className="researchkit-dot" />
        <span className="researchkit-dot" />
        <span className="researchkit-dot" />
      </div>
    )
  }

  const blocks = parseContent(content)

  return (
    <div className="researchkit-response">
      {blocks.map((block, i) => {
        if (block.type === 'code') {
          return (
            <pre key={i} className="researchkit-code-block">
              <code>{block.content}</code>
            </pre>
          )
        }
        if (block.type === 'latex') {
          return (
            <pre key={i} className="researchkit-latex-block">
              <code>{block.content}</code>
            </pre>
          )
        }
        return renderMarkdown(block.content, i)
      })}
      {isStreaming && <span className="researchkit-cursor" />}
    </div>
  )
}

interface ContentBlock {
  type: 'text' | 'code' | 'latex'
  content: string
}

function parseContent(content: string): ContentBlock[] {
  const blocks: ContentBlock[] = []
  const codeBlockRe = /```(\w*)\n([\s\S]*?)```/g
  let lastIndex = 0
  let match

  while ((match = codeBlockRe.exec(content)) !== null) {
    if (match.index > lastIndex) {
      blocks.push({
        type: 'text',
        content: content.slice(lastIndex, match.index),
      })
    }
    const lang = match[1].toLowerCase()
    blocks.push({
      type: lang === 'latex' || lang === 'tex' ? 'latex' : 'code',
      content: match[2],
    })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < content.length) {
    blocks.push({ type: 'text', content: content.slice(lastIndex) })
  }

  return blocks
}

function renderMarkdown(text: string, key: number): React.ReactElement {
  const lines = text.split('\n')
  const elements: React.ReactElement[] = []
  let listItems: string[] = []

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`}>
          {listItems.map((item, i) => (
            <li key={i}>{renderInline(item)}</li>
          ))}
        </ul>
      )
      listItems = []
    }
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('- ') || trimmed.match(/^\d+\.\s/)) {
      listItems.push(trimmed.replace(/^[-\d.]+\s*/, ''))
    } else {
      flushList()
      if (trimmed.startsWith('### ')) {
        elements.push(
          <h5 key={`h-${elements.length}`}>{trimmed.slice(4)}</h5>
        )
      } else if (trimmed.startsWith('## ')) {
        elements.push(
          <h4 key={`h-${elements.length}`}>{trimmed.slice(3)}</h4>
        )
      } else if (trimmed) {
        elements.push(
          <p key={`p-${elements.length}`}>{renderInline(trimmed)}</p>
        )
      }
    }
  }
  flushList()

  return <div key={key}>{elements}</div>
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  const boldRe = /\*\*(.+?)\*\*/g
  let lastIdx = 0
  let m

  while ((m = boldRe.exec(text)) !== null) {
    if (m.index > lastIdx) {
      parts.push(text.slice(lastIdx, m.index))
    }
    parts.push(<strong key={m.index}>{m[1]}</strong>)
    lastIdx = m.index + m[0].length
  }

  if (lastIdx < text.length) {
    parts.push(text.slice(lastIdx))
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>
}
