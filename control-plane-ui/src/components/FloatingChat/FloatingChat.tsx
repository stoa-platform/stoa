/**
 * FloatingChat — AI assistant chat widget (CAB-285)
 *
 * Fixed-position chat bubble at bottom-right of the console.
 * Provides a toggle button to open/close an expandable chat panel
 * with message history and an input field.
 *
 * Integration: rendered inside ProtectedRoutes (above Layout)
 * so it floats over all pages without being re-mounted on navigation.
 */

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import {
  MessageCircle,
  X,
  Send,
  Bot,
  User,
  Minimize2,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

export interface ChatToolUse {
  tool_use_id: string;
  tool_name: string;
  result?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolUse?: ChatToolUse[];
}

export interface FloatingChatProps {
  /** Override the initial open state (useful for testing) */
  initialOpen?: boolean;
  /** Called when the user submits a message — for integration with AI backend */
  onSendMessage?: (message: string, history: ChatMessage[]) => Promise<string>;
}

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    'Hello! I am the STOA AI assistant. I can help you manage your APIs, deployments, and platform configuration. How can I help you today?',
  timestamp: new Date(),
};

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function generateId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function ToolBlock({ tool }: { tool: ChatToolUse }) {
  const [expanded, setExpanded] = useState(false);
  const truncated =
    tool.result && tool.result.length > 500 ? tool.result.slice(0, 500) + '…' : tool.result;

  return (
    <div className="mt-1.5 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-2.5 py-1.5 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 font-medium text-blue-700 dark:text-blue-300 w-full text-left"
        aria-label={`Toggle tool result for ${tool.tool_name}`}
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Tool: {tool.tool_name}
      </button>
      {expanded && truncated && (
        <pre className="mt-1 whitespace-pre-wrap text-neutral-600 dark:text-neutral-400 overflow-hidden max-h-32">
          {truncated}
        </pre>
      )}
    </div>
  );
}

export function FloatingChat({ initialOpen = false, onSendMessage }: FloatingChatProps) {
  const [isOpen, setIsOpen] = useState(initialOpen);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom when messages change or panel opens
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      // Slight delay to let the animation complete
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const handleToggle = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  const handleClose = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleSend = useCallback(async () => {
    const text = inputValue.trim();
    if (!text || isLoading) return;

    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      let assistantContent: string;

      if (onSendMessage) {
        assistantContent = await onSendMessage(text, messages);
      } else {
        // Default stub response when no backend is configured
        assistantContent = `I received your message: "${text}". AI backend integration is not yet configured for this environment.`;
      }

      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: assistantContent,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (_error) {
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, messages, onSendMessage]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend]
  );

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat Panel */}
      {isOpen && (
        <div
          className="w-80 bg-white dark:bg-neutral-800 rounded-2xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col overflow-hidden"
          style={{ height: '420px' }}
          role="dialog"
          aria-label="AI assistant chat"
          aria-modal="false"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-blue-600 dark:bg-blue-700">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5 text-white" />
              <span className="text-sm font-semibold text-white">STOA Assistant</span>
            </div>
            <button
              onClick={handleClose}
              className="text-blue-100 hover:text-white transition-colors rounded-lg p-1"
              aria-label="Close chat"
            >
              <Minimize2 className="w-4 h-4" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-2 ${message.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
              >
                {/* Avatar */}
                <div
                  className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center ${
                    message.role === 'assistant'
                      ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                      : 'bg-neutral-200 dark:bg-neutral-600 text-neutral-600 dark:text-neutral-300'
                  }`}
                  aria-hidden="true"
                >
                  {message.role === 'assistant' ? (
                    <Bot className="w-4 h-4" />
                  ) : (
                    <User className="w-4 h-4" />
                  )}
                </div>

                {/* Bubble */}
                <div
                  className={`flex flex-col ${message.role === 'user' ? 'items-end' : 'items-start'} max-w-[75%]`}
                >
                  <div
                    className={`rounded-2xl px-3 py-2 text-sm ${
                      message.role === 'user'
                        ? 'bg-blue-600 text-white rounded-tr-sm'
                        : 'bg-neutral-100 dark:bg-neutral-700 text-neutral-800 dark:text-neutral-100 rounded-tl-sm'
                    }`}
                  >
                    {message.content}
                    {message.toolUse?.map((tool) => (
                      <ToolBlock key={tool.tool_use_id} tool={tool} />
                    ))}
                  </div>
                  <span className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
                    {formatTime(message.timestamp)}
                  </span>
                </div>
              </div>
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="flex gap-2 flex-row">
                <div className="flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="bg-neutral-100 dark:bg-neutral-700 rounded-2xl rounded-tl-sm px-3 py-2">
                  <div className="flex gap-1 items-center h-5" aria-label="Assistant is typing">
                    <span className="w-1.5 h-1.5 bg-neutral-400 dark:bg-neutral-400 rounded-full animate-bounce [animation-delay:0ms]" />
                    <span className="w-1.5 h-1.5 bg-neutral-400 dark:bg-neutral-400 rounded-full animate-bounce [animation-delay:150ms]" />
                    <span className="w-1.5 h-1.5 bg-neutral-400 dark:bg-neutral-400 rounded-full animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
              </div>
            )}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-neutral-200 dark:border-neutral-700">
            <div className="flex gap-2 items-end">
              <textarea
                ref={inputRef}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask STOA anything..."
                disabled={isLoading}
                rows={1}
                className="flex-1 resize-none rounded-xl border border-neutral-200 dark:border-neutral-600 bg-neutral-50 dark:bg-neutral-900 text-sm text-neutral-800 dark:text-neutral-100 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 placeholder:text-neutral-400 dark:placeholder:text-neutral-500"
                style={{ maxHeight: '80px' }}
                aria-label="Message input"
              />
              <button
                onClick={() => void handleSend()}
                disabled={!inputValue.trim() || isLoading}
                className="flex-shrink-0 w-9 h-9 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl flex items-center justify-center transition-colors"
                aria-label="Send message"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1.5 text-center">
              Press Enter to send, Shift+Enter for new line
            </p>
          </div>
        </div>
      )}

      {/* Toggle Button */}
      <button
        onClick={handleToggle}
        className="w-14 h-14 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg hover:shadow-xl flex items-center justify-center transition-all active:scale-95"
        aria-label={isOpen ? 'Close AI assistant' : 'Open AI assistant'}
        aria-expanded={isOpen}
        aria-haspopup="dialog"
      >
        {isOpen ? <X className="w-6 h-6" /> : <MessageCircle className="w-6 h-6" />}
      </button>
    </div>
  );
}
