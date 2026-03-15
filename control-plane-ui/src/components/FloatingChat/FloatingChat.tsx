/**
 * FloatingChat — AI assistant chat widget (CAB-285, CAB-1816)
 *
 * Fixed-position chat bubble at bottom-right of the console.
 * Supports progressive SSE streaming, tool call rendering,
 * mutation tool confirmation, and conversation list management.
 *
 * Integration: rendered inside ProtectedRoutes (above Layout)
 * so it floats over all pages without being re-mounted on navigation.
 *
 * CAB-1816 Phase 2: Mutation tool confirmation + token budget.
 */

import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react';
import Markdown from 'react-markdown';
import {
  MessageCircle,
  X,
  Send,
  Bot,
  User,
  Minimize2,
  ChevronDown,
  ChevronRight,
  Plus,
  MessageSquare,
  Trash2,
  Loader2,
  Square,
  CheckCircle2,
  XCircle,
  Zap,
} from 'lucide-react';

import type {
  ChatToolCall,
  StreamCallbacks,
  ConversationSummary,
  PendingConfirmation,
  TokenBudgetStatus,
} from '@/hooks/useChatService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  toolCalls?: ChatToolCall[];
  isStreaming?: boolean;
}

export interface FloatingChatProps {
  /** Override the initial open state (useful for testing) */
  initialOpen?: boolean;
  /** Send message with streaming callbacks (primary) */
  onSendMessageStream?: (message: string, callbacks: StreamCallbacks) => Promise<void>;
  /** Confirm or reject a pending mutation tool */
  onConfirmTool?: (
    confirmation: PendingConfirmation,
    approved: boolean,
    callbacks: StreamCallbacks
  ) => Promise<void>;
  /** Fetch token budget status */
  onFetchBudgetStatus?: () => Promise<TokenBudgetStatus | null>;
  /** Abort the current stream */
  onAbort?: () => void;
  /** Load conversations list */
  onLoadConversations?: () => Promise<ConversationSummary[]>;
  /** Switch to an existing conversation */
  onSwitchConversation?: (id: string | null) => void;
  /** Start a new conversation */
  onNewConversation?: () => void;
  /** Delete a conversation */
  onDeleteConversation?: (id: string) => Promise<boolean>;
  /** Load messages for a specific conversation */
  onLoadConversationMessages?: (
    id: string
  ) => Promise<{ role: string; content: string; created_at: string }[]>;
  /** Currently active conversation ID */
  activeConversationId?: string | null;
  /** Backward-compat: simple send that returns full response */
  onSendMessage?: (message: string, history: ChatMessage[]) => Promise<string>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// ToolBlock — expandable tool call result
// ---------------------------------------------------------------------------

function ToolBlock({ tool }: { tool: ChatToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const truncated =
    tool.result && tool.result.length > 500 ? tool.result.slice(0, 500) + '\u2026' : tool.result;

  return (
    <div className="mt-1.5 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 px-2.5 py-1.5 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 font-medium text-blue-700 dark:text-blue-300 w-full text-left"
        aria-label={`Toggle tool result for ${tool.tool_name}`}
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        Tool: {tool.tool_name}
        {!tool.result && <Loader2 className="w-3 h-3 animate-spin ml-auto text-blue-400" />}
      </button>
      {expanded && truncated && (
        <pre className="mt-1 whitespace-pre-wrap text-neutral-600 dark:text-neutral-400 overflow-hidden max-h-32">
          {truncated}
        </pre>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConfirmationBlock — inline confirm/cancel for mutation tools
// ---------------------------------------------------------------------------

function ConfirmationBlock({
  confirmation,
  onConfirm,
  onCancel,
  isProcessing,
}: {
  confirmation: PendingConfirmation;
  onConfirm: () => void;
  onCancel: () => void;
  isProcessing: boolean;
}) {
  return (
    <div className="mt-2 rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 px-3 py-2.5 text-xs">
      <div className="flex items-start gap-2 mb-2">
        <Zap className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
        <div>
          <p className="font-medium text-amber-800 dark:text-amber-200">
            Action requires confirmation
          </p>
          <p className="text-amber-700 dark:text-amber-300 mt-0.5">{confirmation.description}</p>
          <p className="text-amber-600 dark:text-amber-400 mt-1">
            Tool:{' '}
            <code className="bg-amber-100 dark:bg-amber-800/40 px-1 rounded">
              {confirmation.tool_name}
            </code>
          </p>
        </div>
      </div>
      <div className="flex gap-2 ml-5">
        <button
          onClick={onConfirm}
          disabled={isProcessing}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-xs font-medium transition-colors"
          aria-label="Confirm action"
        >
          {isProcessing ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <CheckCircle2 className="w-3 h-3" />
          )}
          Confirm
        </button>
        <button
          onClick={onCancel}
          disabled={isProcessing}
          className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-neutral-200 dark:bg-neutral-600 hover:bg-neutral-300 dark:hover:bg-neutral-500 disabled:opacity-50 text-neutral-700 dark:text-neutral-200 text-xs font-medium transition-colors"
          aria-label="Cancel action"
        >
          <XCircle className="w-3 h-3" />
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BudgetWidget — token usage bar
// ---------------------------------------------------------------------------

function BudgetWidget({ budget }: { budget: TokenBudgetStatus }) {
  const pct = Math.min(budget.usage_percent, 100);
  const barColor = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-amber-500' : 'bg-green-500';

  return (
    <div className="px-4 py-1.5 border-b border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-850">
      <div className="flex items-center justify-between text-xs text-neutral-500 dark:text-neutral-400 mb-0.5">
        <span>Daily tokens</span>
        <span>{Math.round(pct)}%</span>
      </div>
      <div className="h-1 bg-neutral-200 dark:bg-neutral-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} rounded-full transition-all duration-300`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Token budget: ${Math.round(pct)}% used`}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConversationList — sidebar for switching conversations
// ---------------------------------------------------------------------------

function ConversationList({
  conversations,
  activeId,
  onSwitch,
  onNew,
  onDelete,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  onSwitch: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b border-neutral-200 dark:border-neutral-700">
        <button
          onClick={onNew}
          className="flex items-center gap-1.5 w-full px-2 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
          aria-label="New conversation"
        >
          <Plus className="w-3.5 h-3.5" />
          New conversation
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {conversations.length === 0 ? (
          <p className="text-xs text-neutral-400 dark:text-neutral-500 text-center py-4">
            No conversations yet
          </p>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={`group flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs cursor-pointer transition-colors ${
                conv.id === activeId
                  ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-700'
              }`}
            >
              <MessageSquare className="w-3 h-3 flex-shrink-0" />
              <button
                className="flex-1 text-left truncate"
                onClick={() => onSwitch(conv.id)}
                title={conv.title}
              >
                {conv.title}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-all"
                aria-label={`Delete conversation: ${conv.title}`}
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FloatingChat — main component
// ---------------------------------------------------------------------------

export function FloatingChat({
  initialOpen = false,
  onSendMessageStream,
  onConfirmTool,
  onFetchBudgetStatus,
  onAbort,
  onLoadConversations,
  onSwitchConversation,
  onNewConversation,
  onDeleteConversation,
  onLoadConversationMessages,
  activeConversationId,
  onSendMessage,
}: FloatingChatProps) {
  const [isOpen, setIsOpen] = useState(initialOpen);
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showConversations, setShowConversations] = useState(false);
  const [conversationList, setConversationList] = useState<ConversationSummary[]>([]);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);
  const [budgetStatus, setBudgetStatus] = useState<TokenBudgetStatus | null>(null);
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
      const timer = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Load conversations when sidebar opens
  useEffect(() => {
    if (showConversations && onLoadConversations) {
      void onLoadConversations().then(setConversationList);
    }
  }, [showConversations, onLoadConversations]);

  // Fetch budget status when panel opens
  useEffect(() => {
    if (isOpen && onFetchBudgetStatus) {
      void onFetchBudgetStatus().then((b) => {
        if (b) setBudgetStatus(b);
      });
    }
  }, [isOpen, onFetchBudgetStatus]);

  const handleToggle = useCallback(() => setIsOpen((prev) => !prev), []);
  const handleClose = useCallback(() => setIsOpen(false), []);

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

    // Streaming mode (progressive rendering)
    if (onSendMessageStream) {
      const assistantId = generateId();

      // Insert a placeholder assistant message that we'll update progressively
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          timestamp: new Date(),
          toolCalls: [],
          isStreaming: true,
        },
      ]);

      try {
        await onSendMessageStream(text, {
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + delta } : m))
            );
          },
          onToolStart: (toolUseId, toolName) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      toolCalls: [
                        ...(m.toolCalls || []),
                        { tool_use_id: toolUseId, tool_name: toolName },
                      ],
                    }
                  : m
              )
            );
          },
          onToolResult: (toolUseId, _toolName, result) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      toolCalls: (m.toolCalls || []).map((tc) =>
                        tc.tool_use_id === toolUseId ? { ...tc, result } : tc
                      ),
                    }
                  : m
              )
            );
          },
          onConfirmationRequired: (confirmation) => {
            setPendingConfirmation(confirmation);
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content || `Error: ${error}`, isStreaming: false }
                  : m
              )
            );
          },
          onComplete: () => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
            );
          },
        });
      } catch (error) {
        const detail = error instanceof Error ? error.message : 'Unknown error';
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: m.content || `Sorry, I encountered an error: ${detail}`,
                  isStreaming: false,
                }
              : m
          )
        );
      } finally {
        setIsLoading(false);
      }
      return;
    }

    // Fallback: non-streaming mode (backward-compatible)
    try {
      let assistantContent: string;
      if (onSendMessage) {
        assistantContent = await onSendMessage(text, messages);
      } else {
        assistantContent = `I received your message: "${text}". AI backend integration is not yet configured for this environment.`;
      }
      setMessages((prev) => [
        ...prev,
        { id: generateId(), role: 'assistant', content: assistantContent, timestamp: new Date() },
      ]);
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unknown error';
      setMessages((prev) => [
        ...prev,
        {
          id: generateId(),
          role: 'assistant',
          content: `Sorry, I encountered an error: ${detail}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, isLoading, messages, onSendMessageStream, onSendMessage]);

  const handleAbort = useCallback(() => {
    onAbort?.();
    setIsLoading(false);
    setMessages((prev) => prev.map((m) => (m.isStreaming ? { ...m, isStreaming: false } : m)));
  }, [onAbort]);

  const handleConfirmation = useCallback(
    async (approved: boolean) => {
      if (!pendingConfirmation || !onConfirmTool) return;
      const confirmation = pendingConfirmation;
      setPendingConfirmation(null);
      setIsLoading(true);

      const assistantId = generateId();
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          timestamp: new Date(),
          toolCalls: [],
          isStreaming: true,
        },
      ]);

      try {
        await onConfirmTool(confirmation, approved, {
          onDelta: (delta) => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + delta } : m))
            );
          },
          onToolResult: (toolUseId, toolName, result) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      toolCalls: [
                        ...(m.toolCalls || []),
                        { tool_use_id: toolUseId, tool_name: toolName, result },
                      ],
                    }
                  : m
              )
            );
          },
          onError: (error) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content || `Error: ${error}`, isStreaming: false }
                  : m
              )
            );
          },
          onComplete: () => {
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m))
            );
          },
        });
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: m.content || 'Failed to process confirmation', isStreaming: false }
              : m
          )
        );
      } finally {
        setIsLoading(false);
        // Refresh budget after mutation
        if (onFetchBudgetStatus) {
          void onFetchBudgetStatus().then((b) => {
            if (b) setBudgetStatus(b);
          });
        }
      }
    },
    [pendingConfirmation, onConfirmTool, onFetchBudgetStatus]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    },
    [handleSend]
  );

  const handleNewConversation = useCallback(() => {
    onNewConversation?.();
    setMessages([WELCOME_MESSAGE]);
    setShowConversations(false);
  }, [onNewConversation]);

  const handleSwitchConversation = useCallback(
    (id: string) => {
      onSwitchConversation?.(id);
      setShowConversations(false);

      if (onLoadConversationMessages) {
        setIsLoading(true);
        void onLoadConversationMessages(id)
          .then((msgs) => {
            const loaded: ChatMessage[] = msgs.map((m, i) => ({
              id: `hist-${id}-${i}`,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: new Date(m.created_at),
            }));
            setMessages(loaded.length > 0 ? loaded : [WELCOME_MESSAGE]);
          })
          .catch(() => setMessages([WELCOME_MESSAGE]))
          .finally(() => setIsLoading(false));
      } else {
        setMessages([WELCOME_MESSAGE]);
      }
    },
    [onSwitchConversation, onLoadConversationMessages]
  );

  const handleDeleteConversation = useCallback(
    async (id: string) => {
      if (onDeleteConversation) {
        const deleted = await onDeleteConversation(id);
        if (deleted) {
          setConversationList((prev) => prev.filter((c) => c.id !== id));
        }
      }
    },
    [onDeleteConversation]
  );

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat Panel */}
      {isOpen && (
        <div
          className="w-96 bg-white dark:bg-neutral-800 rounded-2xl shadow-2xl border border-neutral-200 dark:border-neutral-700 flex flex-col overflow-hidden"
          style={{ height: '520px' }}
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
            <div className="flex items-center gap-1">
              {onLoadConversations && (
                <button
                  onClick={() => setShowConversations(!showConversations)}
                  className="text-blue-100 hover:text-white transition-colors rounded-lg p-1"
                  aria-label="Toggle conversation list"
                  title="Conversations"
                >
                  <MessageSquare className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={handleClose}
                className="text-blue-100 hover:text-white transition-colors rounded-lg p-1"
                aria-label="Close chat"
              >
                <Minimize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Token budget bar */}
          {budgetStatus && <BudgetWidget budget={budgetStatus} />}

          <div className="flex flex-1 overflow-hidden">
            {/* Conversation sidebar */}
            {showConversations && (
              <div className="w-40 border-r border-neutral-200 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-850 flex-shrink-0">
                <ConversationList
                  conversations={conversationList}
                  activeId={activeConversationId ?? null}
                  onSwitch={handleSwitchConversation}
                  onNew={handleNewConversation}
                  onDelete={(id) => void handleDeleteConversation(id)}
                />
              </div>
            )}

            {/* Messages area */}
            <div className="flex-1 flex flex-col overflow-hidden">
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
                        {message.role === 'assistant' && message.content ? (
                          <Markdown
                            components={{
                              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                              ul: ({ children }) => (
                                <ul className="list-disc pl-4 mb-2 last:mb-0">{children}</ul>
                              ),
                              ol: ({ children }) => (
                                <ol className="list-decimal pl-4 mb-2 last:mb-0">{children}</ol>
                              ),
                              li: ({ children }) => <li className="mb-0.5">{children}</li>,
                              strong: ({ children }) => (
                                <strong className="font-semibold">{children}</strong>
                              ),
                              code: ({ children, className }) =>
                                className ? (
                                  <pre className="bg-neutral-200 dark:bg-neutral-600 rounded-lg p-2 my-1 overflow-x-auto text-xs">
                                    <code>{children}</code>
                                  </pre>
                                ) : (
                                  <code className="bg-neutral-200 dark:bg-neutral-600 px-1 py-0.5 rounded text-xs">
                                    {children}
                                  </code>
                                ),
                              a: ({ href, children }) => (
                                <a
                                  href={href}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-blue-600 dark:text-blue-400 underline"
                                >
                                  {children}
                                </a>
                              ),
                              h1: ({ children }) => (
                                <p className="font-bold text-base mb-1">{children}</p>
                              ),
                              h2: ({ children }) => <p className="font-bold mb-1">{children}</p>,
                              h3: ({ children }) => (
                                <p className="font-semibold mb-1">{children}</p>
                              ),
                            }}
                          >
                            {message.content}
                          </Markdown>
                        ) : (
                          message.content
                        )}
                        {message.isStreaming && !message.content && (
                          <div
                            className="flex gap-1 items-center h-5"
                            aria-label="Assistant is thinking"
                          >
                            <span className="w-1.5 h-1.5 bg-neutral-400 rounded-full animate-bounce [animation-delay:0ms]" />
                            <span className="w-1.5 h-1.5 bg-neutral-400 rounded-full animate-bounce [animation-delay:150ms]" />
                            <span className="w-1.5 h-1.5 bg-neutral-400 rounded-full animate-bounce [animation-delay:300ms]" />
                          </div>
                        )}
                        {message.toolCalls?.map((tool) => (
                          <ToolBlock key={tool.tool_use_id} tool={tool} />
                        ))}
                      </div>
                      <span className="text-xs text-neutral-400 dark:text-neutral-500 mt-1">
                        {formatTime(message.timestamp)}
                      </span>
                    </div>
                  </div>
                ))}

                {/* Pending confirmation */}
                {pendingConfirmation && (
                  <ConfirmationBlock
                    confirmation={pendingConfirmation}
                    onConfirm={() => void handleConfirmation(true)}
                    onCancel={() => void handleConfirmation(false)}
                    isProcessing={isLoading}
                  />
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
                  {isLoading ? (
                    <button
                      onClick={handleAbort}
                      className="flex-shrink-0 w-9 h-9 bg-red-500 hover:bg-red-600 text-white rounded-xl flex items-center justify-center transition-colors"
                      aria-label="Stop generating"
                      title="Stop"
                    >
                      <Square className="w-4 h-4" />
                    </button>
                  ) : (
                    <button
                      onClick={() => void handleSend()}
                      disabled={!inputValue.trim()}
                      className="flex-shrink-0 w-9 h-9 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl flex items-center justify-center transition-colors"
                      aria-label="Send message"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  )}
                </div>
                <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-1.5 text-center">
                  Press Enter to send, Shift+Enter for new line
                </p>
              </div>
            </div>
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
