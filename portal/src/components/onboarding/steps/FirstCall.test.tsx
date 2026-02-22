/**
 * Tests for FirstCall step (CAB-1306)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { FirstCall } from './FirstCall';
import { renderWithProviders, mockApplication, mockAPI } from '../../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

vi.mock('../../../config', () => ({
  config: {
    api: { baseUrl: 'https://api.example.com' },
    mcp: { baseUrl: 'https://mcp.example.com' },
    services: { docs: { url: 'https://docs.example.com' } },
  },
}));

describe('FirstCall', () => {
  const onFinish = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
  });

  it('renders the step title', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    expect(screen.getByText('firstCall.title')).toBeInTheDocument();
  });

  it('renders without credentials section when app is null', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    expect(screen.queryByText('firstCall.credentials')).not.toBeInTheDocument();
  });

  it('shows credentials section when app is provided', () => {
    renderWithProviders(
      <FirstCall
        app={mockApplication() as never}
        selectedApi={null}
        useCase="rest-api"
        onFinish={onFinish}
      />
    );
    expect(screen.getByText('firstCall.credentials')).toBeInTheDocument();
    expect(screen.getByText('My App')).toBeInTheDocument();
  });

  it('shows curl example for rest-api use case', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    expect(screen.getByText('firstCall.exampleCall')).toBeInTheDocument();
    // The code block contains the API base URL
    expect(screen.getByText(/api\.example\.com/)).toBeInTheDocument();
  });

  it('shows MCP config section heading for mcp-agent use case', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="mcp-agent" onFinish={onFinish} />
    );
    expect(screen.getByText('firstCall.mcpConfig')).toBeInTheDocument();
  });

  it('shows MCP base URL in config block for mcp-agent use case', () => {
    renderWithProviders(
      <FirstCall
        app={mockApplication() as never}
        selectedApi={null}
        useCase="mcp-agent"
        onFinish={onFinish}
      />
    );
    expect(screen.getByText(/mcp\.example\.com/)).toBeInTheDocument();
  });

  it('clicking finish button calls onFinish', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    fireEvent.click(screen.getByRole('button', { name: 'firstCall.goToDashboard' }));
    expect(onFinish).toHaveBeenCalled();
  });

  it('shows documentation link', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    expect(screen.getByText('firstCall.documentation')).toBeInTheDocument();
  });

  it('shows sandbox link when API is selected', () => {
    renderWithProviders(
      <FirstCall
        app={null}
        selectedApi={mockAPI() as never}
        useCase="rest-api"
        onFinish={onFinish}
      />
    );
    expect(screen.getByText('firstCall.trySandbox')).toBeInTheDocument();
  });

  it('does not show sandbox link when no API is selected', () => {
    renderWithProviders(
      <FirstCall app={null} selectedApi={null} useCase="rest-api" onFinish={onFinish} />
    );
    expect(screen.queryByText('firstCall.trySandbox')).not.toBeInTheDocument();
  });
});
