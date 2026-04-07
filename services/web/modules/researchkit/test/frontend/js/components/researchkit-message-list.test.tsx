import { expect } from 'chai'
import { fireEvent, render, screen } from '@testing-library/react'
import { ResearchKitMessageList } from '../../../../frontend/js/components/researchkit-message-list'
import type { RKMessage } from '../../../../frontend/js/context/researchkit-context'

describe('ResearchKitMessageList', function () {
  it('renders reasoning first, then collapsible actions and hidden patches', function () {
    const openPatch = (..._args: unknown[]) => {}
    const acceptPatch = (..._args: unknown[]) => {}
    const rejectPatch = (..._args: unknown[]) => {}

    let openedPatch: [string, number] | null = null

    const messages: RKMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Update the introduction',
        timestamp: Date.now(),
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content:
          '**Plan**\n1. Inspect `intro.tex`\n2. Prepare a minimal revision',
        timestamp: Date.now() + 1,
        responseId: 'response-1',
        actions: [
          {
            tool: 'bash',
            status: 'started',
            iteration: 1,
            sequence: 1,
            command: 'sed -n 1,80p intro.tex',
            detail: 'Running command 1/1: `sed -n 1,80p intro.tex`',
            response_id: 'response-1',
          },
          {
            tool: 'bash',
            status: 'completed',
            iteration: 1,
            sequence: 1,
            command: 'sed -n 1,80p intro.tex',
            detail: '`sed -n 1,80p intro.tex` exited 0; created 1 diff patch.',
            patch_count: 1,
            response_id: 'response-1',
            output: '1\tIntroduction',
          },
        ],
        patches: [
          {
            file_path: 'intro.tex',
            selection_from: 12,
            selection_to: 24,
            original_text: 'Old intro',
            replacement_text: 'New intro',
            description: 'Rewrite introduction',
            response_id: 'response-1',
          },
        ],
      },
      {
        id: 'assistant-2',
        role: 'assistant',
        content: 'Applied the final wording cleanup.',
        timestamp: Date.now() + 2,
        responseId: 'response-2',
      },
    ]

    render(
      <ResearchKitMessageList
        messages={messages}
        onOpenPatch={(messageId, patchIndex) => {
          openedPatch = [messageId, patchIndex]
          openPatch(messageId, patchIndex)
        }}
        onAcceptPatch={acceptPatch}
        onRejectPatch={rejectPatch}
      />
    )

    screen.getByText('Plan')
    screen.getByText('Inspect')
    screen.getAllByText('intro.tex')
    screen.getByText('Applied the final wording cleanup.')

    const actionsSummary = screen.getByText('Actions (2)')
    fireEvent.click(actionsSummary)

    screen.getByText('Running command 1/1: `sed -n 1,80p intro.tex`')
    screen.getAllByText('bash')
    screen.getByText('1 patch')
    fireEvent.click(screen.getByText('Output'))
    screen.getByText('1\tIntroduction')

    const patchesSummary = screen.getByText('Diff patches (1)')
    fireEvent.click(patchesSummary)

    fireEvent.click(screen.getByRole('button', { name: 'Open in editor' }))
    expect(openedPatch).to.deep.equal(['assistant-1', 0])
  })

  it('preserves markdown whitespace and line breaks in assistant messages', function () {
    const messages: RKMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: [
          'First line',
          'Second line with  two spaces',
          '',
          '- bullet one',
          '  - bullet two',
          '',
          '```text',
          '  keep this indentation',
          'next line',
          '```',
        ].join('\n'),
        timestamp: Date.now(),
      },
    ]

    const { container } = render(
      <ResearchKitMessageList
        messages={messages}
        onOpenPatch={() => {}}
        onAcceptPatch={() => {}}
        onRejectPatch={() => {}}
      />
    )

    const paragraph = container.querySelector('.rk-rich-paragraph')
    expect(paragraph?.textContent).to.equal(
      'First line\nSecond line with  two spaces'
    )

    const listItems = Array.from(
      container.querySelectorAll('.rk-rich-list li')
    ).map(item => item.textContent)
    expect(listItems).to.deep.equal(['bullet one', '  bullet two'])

    const code = container.querySelector('.rk-rich-code code')
    expect(code?.textContent).to.equal('  keep this indentation\nnext line')
  })

  it('renders research artifact cards from completed actions', function () {
    const messages: RKMessage[] = [
      {
        id: 'assistant-artifacts',
        role: 'assistant',
        content: 'Research complete.',
        timestamp: Date.now(),
        actions: [
          {
            tool: 'delegate_to_subagent',
            status: 'completed',
            iteration: 1,
            detail: 'Sub-agent returned status `completed` with 2 artifacts.',
            artifacts: [
              {
                type: 'literature_search_result',
                query: 'graph neural networks robustness',
                result_count: 12,
                papers: [{ title: 'Robust GNNs', year: 2024 }],
                bibtex: '@article{robust2024,...}',
              },
              {
                type: 'citation_verification_result',
                summary: {
                  verified: 8,
                  suspicious: 1,
                  hallucinated: 0,
                  integrity_score: 0.889,
                },
              },
            ],
          },
        ],
      },
    ]

    render(
      <ResearchKitMessageList
        messages={messages}
        onOpenPatch={() => {}}
        onAcceptPatch={() => {}}
        onRejectPatch={() => {}}
      />
    )

    screen.getByText('Research artifacts (2)')
    screen.getByText('Literature Search')
    screen.getByText('Citation Verification')
    screen.getByText('graph neural networks robustness')
    screen.getByText('0.889')
  })

  it('does not show a reasoning placeholder for action-only assistant messages', function () {
    const messages: RKMessage[] = [
      {
        id: 'assistant-action-only',
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
        actions: [
          {
            tool: 'bash',
            status: 'completed',
            iteration: 1,
            sequence: 1,
            command: 'ls',
            detail: '`ls` exited 0.',
          },
        ],
      },
    ]

    const { container } = render(
      <ResearchKitMessageList
        messages={messages}
        onOpenPatch={() => {}}
        onAcceptPatch={() => {}}
        onRejectPatch={() => {}}
      />
    )

    screen.getByText('Actions (1)')
    expect(screen.queryByText('Preparing response...')).to.equal(null)
    expect(container.querySelector('.rk-cursor-blink')).to.equal(null)
  })

  it('renders create-file patches without an open-in-editor action', function () {
    const messages: RKMessage[] = [
      {
        id: 'assistant-create-patch',
        role: 'assistant',
        content: 'Drafted a new introduction file.',
        timestamp: Date.now(),
        patches: [
          {
            file_path: 'sections/introduction_rewritten.tex',
            selection_from: 0,
            selection_to: 0,
            original_text: '',
            replacement_text: 'New introduction.\n',
            description: 'Create rewritten introduction',
            change_type: 'create',
          },
        ],
      },
    ]

    render(
      <ResearchKitMessageList
        messages={messages}
        onOpenPatch={() => {}}
        onAcceptPatch={() => {}}
        onRejectPatch={() => {}}
      />
    )

    fireEvent.click(screen.getByText('Diff patches (1)'))
    screen.getByText('sections/introduction_rewritten.tex')
    screen.getByText('New file')
    expect(screen.queryByRole('button', { name: 'Open in editor' })).to.equal(
      null
    )
  })
})
