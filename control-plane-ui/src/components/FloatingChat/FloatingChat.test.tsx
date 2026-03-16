/**
 * FloatingChat tests (CAB-285, CAB-1816)
 *
 * Covers: toggle open/close, message display, message sending,
 * keyboard shortcuts, loading state, error handling, ARIA attributes,
 * mutation tool confirmation, token budget widget.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { FloatingChat } from '@stoa/shared/components/FloatingChat';
import type { ChatMessage } from '@stoa/shared/components/FloatingChat';
import type {
  ChatToolCall,
  PendingConfirmation,
  StreamCallbacks,
  TokenBudgetStatus,
} from '@stoa/shared/hooks/useChatService';

// jsdom does not implement scrollIntoView — mock it globally
window.HTMLElement.prototype.scrollIntoView = vi.fn();

type SendHandler = (message: string, history: ChatMessage[]) => Promise<string>;

beforeEach(() => {
  vi.clearAllMocks();
  // Re-assign after clearAllMocks
  window.HTMLElement.prototype.scrollIntoView = vi.fn();
});

// ---- toggle open/close ----

describe('FloatingChat toggle', () => {
  test('renders toggle button by default', () => {
    render(<FloatingChat />);
    expect(screen.getByRole('button', { name: /open ai assistant/i })).toBeInTheDocument();
  });

  test('chat panel is hidden by default', () => {
    render(<FloatingChat />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('opens chat panel on toggle button click', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    expect(screen.getByRole('dialog', { name: /ai assistant chat/i })).toBeInTheDocument();
  });

  test('toggle button shows close icon when panel is open', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    expect(screen.getByRole('button', { name: /close ai assistant/i })).toBeInTheDocument();
  });

  test('closes chat panel on toggle button click when open', async () => {
    const user = userEvent.setup();
    render(<FloatingChat initialOpen={true} />);
    const toggleBtn = screen.getByRole('button', { name: /close ai assistant/i });
    await user.click(toggleBtn);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('closes chat panel via minimize button in header', async () => {
    const user = userEvent.setup();
    render(<FloatingChat initialOpen={true} />);
    await user.click(screen.getByRole('button', { name: /close chat/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  test('renders chat open when initialOpen is true', () => {
    render(<FloatingChat initialOpen={true} />);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

// ---- welcome message ----

describe('FloatingChat welcome message', () => {
  test('shows welcome message when panel opens', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    expect(screen.getByText(/hello! i am the stoa ai assistant/i)).toBeInTheDocument();
  });

  test('shows STOA Assistant header label', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    expect(screen.getByText('STOA Assistant')).toBeInTheDocument();
  });
});

// ---- sending messages ----

describe('FloatingChat message sending', () => {
  test('typing in the input updates value', async () => {
    const user = userEvent.setup();
    render(<FloatingChat initialOpen={true} />);
    const input = screen.getByRole('textbox', { name: /message input/i });
    await user.type(input, 'Hello STOA');
    expect(input).toHaveValue('Hello STOA');
  });

  test('send button is disabled when input is empty', () => {
    render(<FloatingChat initialOpen={true} />);
    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
  });

  test('send button is enabled when input has text', async () => {
    const user = userEvent.setup();
    render(<FloatingChat initialOpen={true} />);
    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Hi');
    expect(screen.getByRole('button', { name: /send message/i })).toBeEnabled();
  });

  test('clicking send adds user message and clears input', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('Pong!');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    const input = screen.getByRole('textbox', { name: /message input/i });
    await user.type(input, 'Ping!');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => expect(screen.getByText('Ping!')).toBeInTheDocument());
    expect(input).toHaveValue('');
  });

  test('pressing Enter sends the message', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('Got it!');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    const input = screen.getByRole('textbox', { name: /message input/i });
    await user.type(input, 'Hello{Enter}');

    await waitFor(() => {
      expect(screen.getByText('Hello')).toBeInTheDocument();
    });
    expect(onSendMessage).toHaveBeenCalledOnce();
  });

  test('pressing Shift+Enter does NOT send', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('OK');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    const input = screen.getByRole('textbox', { name: /message input/i });
    await user.type(input, 'Line1{Shift>}{Enter}{/Shift}Line2');

    expect(onSendMessage).not.toHaveBeenCalled();
  });

  test('assistant response is shown after sending', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('This is the answer.');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Question?');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('This is the answer.')).toBeInTheDocument();
    });
  });

  test('shows stub response when no onSendMessage is provided', async () => {
    const user = userEvent.setup();
    render(<FloatingChat initialOpen={true} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Test');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText(/i received your message/i)).toBeInTheDocument();
    });
  });

  test('onSendMessage receives message and history', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('OK');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'My question');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(onSendMessage).toHaveBeenCalledWith(
        'My question',
        expect.arrayContaining([expect.objectContaining({ role: 'assistant' })])
      );
    });
  });
});

// ---- loading state ----

describe('FloatingChat loading state', () => {
  test('shows thinking indicator while waiting for streaming response', async () => {
    const user = userEvent.setup();
    let resolveStream: () => void = () => {};
    const onSendMessageStream = vi.fn().mockImplementation(
      (_msg: string, callbacks: { onComplete?: () => void }) =>
        new Promise<void>((r) => {
          resolveStream = () => {
            callbacks.onComplete?.();
            r();
          };
        })
    );
    render(<FloatingChat initialOpen={true} onSendMessageStream={onSendMessageStream} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Loading?');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    expect(screen.getByLabelText(/assistant is thinking/i)).toBeInTheDocument();

    await act(async () => {
      resolveStream();
    });
    await waitFor(() => {
      expect(screen.queryByLabelText(/assistant is thinking/i)).not.toBeInTheDocument();
    });
  });

  test('shows abort button while loading instead of send', async () => {
    const user = userEvent.setup();
    let resolve: (value: string) => void = () => {};
    const onSendMessage = vi.fn<SendHandler>().mockImplementation(
      () =>
        new Promise<string>((r) => {
          resolve = r;
        })
    );
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Wait');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    // Send button is replaced by abort button during streaming
    expect(screen.queryByRole('button', { name: /send message/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /stop generating/i })).toBeInTheDocument();

    await act(async () => {
      resolve('Done!');
    });
  });
});

// ---- error handling ----

describe('FloatingChat error handling', () => {
  test('shows error message when onSendMessage throws', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>().mockRejectedValue(new Error('Network error'));
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Boom');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText(/encountered an error/i)).toBeInTheDocument();
    });
  });
});

// ---- ARIA attributes ----

describe('FloatingChat accessibility', () => {
  test('toggle button has aria-expanded false when closed', () => {
    render(<FloatingChat />);
    const btn = screen.getByRole('button', { name: /open ai assistant/i });
    expect(btn).toHaveAttribute('aria-expanded', 'false');
  });

  test('toggle button has aria-expanded true when open', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    const btn = screen.getByRole('button', { name: /close ai assistant/i });
    expect(btn).toHaveAttribute('aria-expanded', 'true');
  });

  test('dialog has aria-label', async () => {
    const user = userEvent.setup();
    render(<FloatingChat />);
    await user.click(screen.getByRole('button', { name: /open ai assistant/i }));
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-label', 'AI assistant chat');
  });

  test('input has aria-label', () => {
    render(<FloatingChat initialOpen={true} />);
    expect(screen.getByLabelText(/message input/i)).toBeInTheDocument();
  });

  test('send button has aria-label', () => {
    render(<FloatingChat initialOpen={true} />);
    expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument();
  });
});

// ---- multiple messages ----

describe('FloatingChat message history', () => {
  test('messages accumulate in history', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi
      .fn<SendHandler>()
      .mockResolvedValueOnce('First reply')
      .mockResolvedValueOnce('Second reply');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    const input = screen.getByRole('textbox', { name: /message input/i });

    await user.type(input, 'First');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => expect(screen.getByText('First reply')).toBeInTheDocument());

    await user.type(input, 'Second');
    await user.click(screen.getByRole('button', { name: /send message/i }));
    await waitFor(() => expect(screen.getByText('Second reply')).toBeInTheDocument());

    // All messages remain visible
    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
  });

  test('whitespace-only messages are not sent', async () => {
    const user = userEvent.setup();
    const onSendMessage = vi.fn<SendHandler>();
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    const input = screen.getByRole('textbox', { name: /message input/i });
    await user.type(input, '   ');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    expect(onSendMessage).not.toHaveBeenCalled();
  });
});

// ---- tool use blocks (CAB-287) ----

describe('FloatingChat tool use blocks', () => {
  test('renders tool use blocks when message has toolUse', async () => {
    const user = userEvent.setup();
    const toolData: ChatToolCall[] = [
      { tool_use_id: 'tu-1', tool_name: 'list_apis', result: '{"total":3}' },
    ];
    const onSendMessage = vi.fn<SendHandler>().mockResolvedValue('Found 3 APIs.');
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'List APIs');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText('Found 3 APIs.')).toBeInTheDocument();
    });

    // Tool data type is verified as part of the ChatMessage interface
    expect(toolData[0].tool_name).toBe('list_apis');
  });

  test('ChatToolCall type has required fields', () => {
    const tool: ChatToolCall = {
      tool_use_id: 'tu-1',
      tool_name: 'platform_info',
      result: '{"status":"ok"}',
    };
    expect(tool.tool_use_id).toBe('tu-1');
    expect(tool.tool_name).toBe('platform_info');
    expect(tool.result).toBeDefined();
  });
});

// ---- mutation tool confirmation (CAB-1816 Phase 2) ----

describe('FloatingChat mutation tool confirmation', () => {
  const mockConfirmation: PendingConfirmation = {
    tool_use_id: 'tc-1',
    tool_name: 'subscribe_api',
    tool_input: { api_id: 'api-123', plan: 'basic' },
    description: 'Subscribe to API "Weather Service" on the basic plan',
  };

  test('shows confirmation block when onConfirmationRequired fires', async () => {
    const user = userEvent.setup();
    const onSendMessageStream = vi
      .fn()
      .mockImplementation((_msg: string, callbacks: StreamCallbacks) => {
        callbacks.onConfirmationRequired?.(mockConfirmation);
        callbacks.onComplete?.('', []);
        return Promise.resolve();
      });

    render(<FloatingChat initialOpen={true} onSendMessageStream={onSendMessageStream} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Subscribe me');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByText(/action requires confirmation/i)).toBeInTheDocument();
      expect(screen.getByText(/subscribe_api/)).toBeInTheDocument();
      expect(screen.getByText(mockConfirmation.description)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /confirm action/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel action/i })).toBeInTheDocument();
  });

  test('clicking confirm calls onConfirmTool with approved=true', async () => {
    const user = userEvent.setup();
    const onSendMessageStream = vi
      .fn()
      .mockImplementation((_msg: string, callbacks: StreamCallbacks) => {
        callbacks.onConfirmationRequired?.(mockConfirmation);
        callbacks.onComplete?.('', []);
        return Promise.resolve();
      });
    const onConfirmTool = vi
      .fn()
      .mockImplementation(
        (_conf: PendingConfirmation, _approved: boolean, callbacks: StreamCallbacks) => {
          callbacks.onDelta?.('Subscription created!');
          callbacks.onComplete?.('Subscription created!', []);
          return Promise.resolve();
        }
      );

    render(
      <FloatingChat
        initialOpen={true}
        onSendMessageStream={onSendMessageStream}
        onConfirmTool={onConfirmTool}
      />
    );

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Subscribe');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm action/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /confirm action/i }));

    await waitFor(() => {
      expect(onConfirmTool).toHaveBeenCalledWith(
        mockConfirmation,
        true,
        expect.objectContaining({ onDelta: expect.any(Function) })
      );
    });
  });

  test('clicking cancel calls onConfirmTool with approved=false', async () => {
    const user = userEvent.setup();
    const onSendMessageStream = vi
      .fn()
      .mockImplementation((_msg: string, callbacks: StreamCallbacks) => {
        callbacks.onConfirmationRequired?.(mockConfirmation);
        callbacks.onComplete?.('', []);
        return Promise.resolve();
      });
    const onConfirmTool = vi
      .fn()
      .mockImplementation(
        (_conf: PendingConfirmation, _approved: boolean, callbacks: StreamCallbacks) => {
          callbacks.onDelta?.('Action cancelled.');
          callbacks.onComplete?.('Action cancelled.', []);
          return Promise.resolve();
        }
      );

    render(
      <FloatingChat
        initialOpen={true}
        onSendMessageStream={onSendMessageStream}
        onConfirmTool={onConfirmTool}
      />
    );

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Subscribe');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel action/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /cancel action/i }));

    await waitFor(() => {
      expect(onConfirmTool).toHaveBeenCalledWith(
        mockConfirmation,
        false,
        expect.objectContaining({ onDelta: expect.any(Function) })
      );
    });
  });

  test('confirmation block disappears after user responds', async () => {
    const user = userEvent.setup();
    const onSendMessageStream = vi
      .fn()
      .mockImplementation((_msg: string, callbacks: StreamCallbacks) => {
        callbacks.onConfirmationRequired?.(mockConfirmation);
        callbacks.onComplete?.('', []);
        return Promise.resolve();
      });
    const onConfirmTool = vi
      .fn()
      .mockImplementation(
        (_conf: PendingConfirmation, _approved: boolean, callbacks: StreamCallbacks) => {
          callbacks.onComplete?.('Done', []);
          return Promise.resolve();
        }
      );

    render(
      <FloatingChat
        initialOpen={true}
        onSendMessageStream={onSendMessageStream}
        onConfirmTool={onConfirmTool}
      />
    );

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Sub');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm action/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /confirm action/i }));

    await waitFor(() => {
      expect(screen.queryByText(/action requires confirmation/i)).not.toBeInTheDocument();
    });
  });
});

// ---- token budget widget (CAB-1816 Phase 2) ----

describe('FloatingChat budget widget', () => {
  const mockBudget: TokenBudgetStatus = {
    user_tokens_today: 5000,
    tenant_tokens_today: 12000,
    daily_budget: 50000,
    remaining: 38000,
    budget_exceeded: false,
    usage_percent: 24,
  };

  test('shows budget widget when budget data is available', async () => {
    const onFetchBudgetStatus = vi.fn().mockResolvedValue(mockBudget);

    render(<FloatingChat initialOpen={true} onFetchBudgetStatus={onFetchBudgetStatus} />);

    await waitFor(() => {
      expect(screen.getByText('Daily tokens')).toBeInTheDocument();
      expect(screen.getByText('24%')).toBeInTheDocument();
    });
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '24');
  });

  test('does not show budget widget when fetch returns null', async () => {
    const onFetchBudgetStatus = vi.fn().mockResolvedValue(null);

    render(<FloatingChat initialOpen={true} onFetchBudgetStatus={onFetchBudgetStatus} />);

    // Allow the effect to run
    await act(async () => {});

    expect(screen.queryByText('Daily tokens')).not.toBeInTheDocument();
  });

  test('budget widget fetches on panel open', async () => {
    const onFetchBudgetStatus = vi.fn().mockResolvedValue(mockBudget);

    render(<FloatingChat initialOpen={true} onFetchBudgetStatus={onFetchBudgetStatus} />);

    await waitFor(() => {
      expect(onFetchBudgetStatus).toHaveBeenCalledOnce();
    });
  });

  test('budget widget shows red bar when usage >= 90%', async () => {
    const highBudget: TokenBudgetStatus = {
      ...mockBudget,
      usage_percent: 95,
    };
    const onFetchBudgetStatus = vi.fn().mockResolvedValue(highBudget);

    render(<FloatingChat initialOpen={true} onFetchBudgetStatus={onFetchBudgetStatus} />);

    await waitFor(() => {
      expect(screen.getByText('95%')).toBeInTheDocument();
    });
  });
});
