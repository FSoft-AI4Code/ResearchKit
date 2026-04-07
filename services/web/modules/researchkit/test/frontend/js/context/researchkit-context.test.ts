import { expect } from 'chai'
import {
  hydrateConversationMessages,
  type RKConversationMessage,
} from '../../../../frontend/js/context/researchkit-context'

describe('hydrateConversationMessages', function () {
  it('restores assistant metadata for saved history messages', function () {
    const messages: RKConversationMessage[] = [
      {
        role: 'user',
        content: 'Create a draft',
      },
      {
        role: 'assistant',
        content: 'Inspecting the file.',
        response_id: 'response-1',
        actions: [
          {
            tool: 'str_replace_editor',
            status: 'completed',
            iteration: 1,
            detail: 'Viewed `draft.tex`.',
            response_id: 'response-1',
          },
        ],
        patches: [
          {
            file_path: 'draft.tex',
            selection_from: 0,
            selection_to: 0,
            original_text: '',
            replacement_text: 'hello\n',
            description: 'Create draft',
            response_id: 'response-1',
            change_type: 'create',
          },
        ],
      },
      {
        role: 'assistant',
        content: 'Done.',
        response_id: 'response-2',
      },
    ]

    const hydrated = hydrateConversationMessages('thread-1', messages, 1000)

    expect(hydrated).to.deep.equal([
      {
        id: 'history-thread-1-0',
        role: 'user',
        content: 'Create a draft',
        timestamp: 1000,
        isStreaming: false,
        responseId: undefined,
        actionId: undefined,
        patches: [],
        actions: [],
      },
      {
        id: 'history-thread-1-1',
        role: 'assistant',
        content: 'Inspecting the file.',
        timestamp: 1001,
        isStreaming: false,
        responseId: 'response-1',
        actionId: undefined,
        patches: [
          {
            file_path: 'draft.tex',
            selection_from: 0,
            selection_to: 0,
            original_text: '',
            replacement_text: 'hello\n',
            description: 'Create draft',
            response_id: 'response-1',
            change_type: 'create',
          },
        ],
        actions: [
          {
            tool: 'str_replace_editor',
            status: 'completed',
            iteration: 1,
            detail: 'Viewed `draft.tex`.',
            response_id: 'response-1',
          },
        ],
      },
      {
        id: 'history-thread-1-2',
        role: 'assistant',
        content: 'Done.',
        timestamp: 1002,
        isStreaming: false,
        responseId: 'response-2',
        actionId: undefined,
        patches: [],
        actions: [],
      },
    ])
  })
})
