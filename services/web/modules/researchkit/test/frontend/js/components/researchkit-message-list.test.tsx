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

    const patchesSummary = screen.getByText('Diff patches (1)')
    fireEvent.click(patchesSummary)

    fireEvent.click(screen.getByRole('button', { name: 'Open in editor' }))
    expect(openedPatch).to.deep.equal(['assistant-1', 0])
  })
})
