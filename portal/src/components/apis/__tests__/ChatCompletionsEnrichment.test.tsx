/**
 * ChatCompletionsEnrichment Tests (CAB-1611)
 *
 * Tests for the Chat Completions API enrichment panel — conditional rendering,
 * subscription plans, GDPR notice, API key notice, and curl examples.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { ChatCompletionsEnrichment } from '../ChatCompletionsEnrichment';
import { renderWithProviders } from '../../../test/helpers';
import { CHAT_COMPLETIONS_API_NAME } from '../../../data/chatCompletionsConfig';

describe('ChatCompletionsEnrichment', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns null when apiName does not match', () => {
    const { container } = renderWithProviders(
      <ChatCompletionsEnrichment apiName="Some Other API" />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the enrichment panel when apiName matches', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByTestId('chat-completions-enrichment')).toBeInTheDocument();
  });

  it('renders the SSE Streaming badge', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText('SSE Streaming')).toBeInTheDocument();
  });

  it('renders the curl request example section', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText('Exemple de requete')).toBeInTheDocument();
  });

  it('renders the curl response example section', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText('Exemple de reponse')).toBeInTheDocument();
  });

  it('renders both subscription plans', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText(/Projet Alpha/)).toBeInTheDocument();
    expect(screen.getByText(/Projet Beta/)).toBeInTheDocument();
  });

  it('renders plan quota details', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText('1,000')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('5,000')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('renders namespace labels for each plan', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(screen.getByText('alpha')).toBeInTheDocument();
    expect(screen.getByText('beta')).toBeInTheDocument();
  });

  it('renders the GDPR notice with alert role', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    const alert = screen.getByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/Azure OpenAI/);
  });

  it('renders the API key notice', () => {
    renderWithProviders(<ChatCompletionsEnrichment apiName={CHAT_COMPLETIONS_API_NAME} />);
    expect(
      screen.getByText(/cles API Azure OpenAI sont gerees de maniere centralisee/)
    ).toBeInTheDocument();
  });
});
