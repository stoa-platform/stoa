/**
 * FloatingChat tests (CAB-285)
 *
 * Covers: toggle open/close, message display, message sending,
 * keyboard shortcuts, loading state, error handling, ARIA attributes.
 */

import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { FloatingChat } from './FloatingChat';
import type { ChatMessage } from './FloatingChat';

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
  test('shows typing indicator while waiting for response', async () => {
    const user = userEvent.setup();
    let resolve: (value: string) => void = () => {};
    const onSendMessage = vi.fn<SendHandler>().mockImplementation(
      () =>
        new Promise<string>((r) => {
          resolve = r;
        })
    );
    render(<FloatingChat initialOpen={true} onSendMessage={onSendMessage} />);

    await user.type(screen.getByRole('textbox', { name: /message input/i }), 'Loading?');
    await user.click(screen.getByRole('button', { name: /send message/i }));

    expect(screen.getByLabelText(/assistant is typing/i)).toBeInTheDocument();

    await act(async () => {
      resolve('Done!');
    });
    await waitFor(() => {
      expect(screen.queryByLabelText(/assistant is typing/i)).not.toBeInTheDocument();
    });
  });

  test('send button is disabled while loading', async () => {
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

    expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();

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
