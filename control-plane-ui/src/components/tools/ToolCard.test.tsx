// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolCard } from './ToolCard';
import { mockTool } from '../../test/mocks';

describe('ToolCard', () => {
  it('renders tool name and description', () => {
    render(<ToolCard tool={mockTool} />);

    expect(screen.getByText(mockTool.name)).toBeInTheDocument();
    expect(screen.getByText(mockTool.description)).toBeInTheDocument();
  });

  it('displays HTTP method badge', () => {
    render(<ToolCard tool={mockTool} />);

    expect(screen.getByText(mockTool.method)).toBeInTheDocument();
  });

  it('displays version', () => {
    render(<ToolCard tool={mockTool} />);

    expect(screen.getByText(`v${mockTool.version}`)).toBeInTheDocument();
  });

  it('displays tags', () => {
    render(<ToolCard tool={mockTool} />);

    mockTool.tags.forEach((tag) => {
      expect(screen.getByText(tag)).toBeInTheDocument();
    });
  });

  it('displays tenant info', () => {
    render(<ToolCard tool={mockTool} />);

    expect(screen.getByText(`Tenant: ${mockTool.tenantId}`)).toBeInTheDocument();
  });

  it('displays API-backed indicator when endpoint exists', () => {
    render(<ToolCard tool={mockTool} />);

    expect(screen.getByText('API-backed')).toBeInTheDocument();
  });

  it('calls onClick when clicked', () => {
    const onClick = vi.fn();
    render(<ToolCard tool={mockTool} onClick={onClick} />);

    const card = screen.getByText(mockTool.name).closest('div');
    fireEvent.click(card!);

    expect(onClick).toHaveBeenCalled();
  });

  it('displays Subscribe button when onSubscribe provided', () => {
    const onSubscribe = vi.fn();
    render(<ToolCard tool={mockTool} onSubscribe={onSubscribe} />);

    expect(screen.getByText('Subscribe')).toBeInTheDocument();
  });

  it('displays Subscribed button when isSubscribed is true', () => {
    const onSubscribe = vi.fn();
    render(<ToolCard tool={mockTool} onSubscribe={onSubscribe} isSubscribed={true} />);

    expect(screen.getByText('Subscribed')).toBeInTheDocument();
  });

  it('calls onSubscribe when Subscribe button clicked', () => {
    const onSubscribe = vi.fn();
    const onClick = vi.fn();
    render(<ToolCard tool={mockTool} onClick={onClick} onSubscribe={onSubscribe} />);

    const subscribeButton = screen.getByText('Subscribe');
    fireEvent.click(subscribeButton);

    expect(onSubscribe).toHaveBeenCalled();
    expect(onClick).not.toHaveBeenCalled(); // Should not trigger card click
  });

  it('shows parameter count', () => {
    render(<ToolCard tool={mockTool} />);

    const paramCount = Object.keys(mockTool.inputSchema.properties).length;
    expect(screen.getByText(`${paramCount} params`)).toBeInTheDocument();
  });

  it('shows required count when there are required params', () => {
    render(<ToolCard tool={mockTool} />);

    const requiredCount = mockTool.inputSchema.required?.length || 0;
    if (requiredCount > 0) {
      expect(screen.getByText(`${requiredCount} required`)).toBeInTheDocument();
    }
  });
});
