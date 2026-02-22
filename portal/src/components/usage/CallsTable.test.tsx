/**
 * Tests for CallsTable (CAB-1390)
 */

import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { CallsTable } from './CallsTable';
import { renderWithProviders } from '../../test/helpers';
import type { UsageCall } from '../../types';

const makeCall = (overrides: Partial<UsageCall> = {}): UsageCall => ({
  id: 'call-1',
  timestamp: '2026-02-22T12:00:00Z',
  tool_id: 'tool-1',
  tool_name: 'list-apis',
  status: 'success',
  latency_ms: 120,
  ...overrides,
});

const mockCalls: UsageCall[] = [
  makeCall({ id: 'c1', status: 'success', tool_name: 'list-apis' }),
  makeCall({ id: 'c2', status: 'error', tool_name: 'create-api', error_message: 'Not found' }),
  makeCall({ id: 'c3', status: 'timeout', tool_name: 'delete-api', latency_ms: 600 }),
];

describe('CallsTable', () => {
  it('shows loading skeletons when isLoading is true', () => {
    const { container } = renderWithProviders(<CallsTable calls={[]} isLoading={true} />);
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows "No calls found" when calls is empty', () => {
    renderWithProviders(<CallsTable calls={[]} />);
    expect(screen.getByText('No calls found')).toBeInTheDocument();
  });

  it('renders call rows', () => {
    renderWithProviders(<CallsTable calls={mockCalls} />);
    expect(screen.getByText('list-apis')).toBeInTheDocument();
    expect(screen.getByText('create-api')).toBeInTheDocument();
  });

  it('renders status filter buttons', () => {
    renderWithProviders(<CallsTable calls={mockCalls} />);
    const buttons = screen.getAllByRole('button');
    const buttonTexts = buttons.map((b) => b.textContent);
    expect(buttonTexts).toContain('All');
    expect(buttonTexts).toContain('Success');
    expect(buttonTexts).toContain('Error');
    expect(buttonTexts).toContain('Timeout');
  });

  it('filters to only success calls when Success filter is clicked', () => {
    renderWithProviders(<CallsTable calls={mockCalls} />);
    // Click the "Success" filter button (first button with text "Success")
    const successBtn = screen.getAllByText('Success')[0];
    fireEvent.click(successBtn);
    expect(screen.getByText('list-apis')).toBeInTheDocument();
    expect(screen.queryByText('create-api')).not.toBeInTheDocument();
  });

  it('calls onFilterChange when a filter button is clicked', () => {
    const onFilterChange = vi.fn();
    renderWithProviders(<CallsTable calls={mockCalls} onFilterChange={onFilterChange} />);
    // Click the "Error" filter button (first one is the filter button)
    const errorBtn = screen.getAllByText('Error')[0];
    fireEvent.click(errorBtn);
    expect(onFilterChange).toHaveBeenCalledWith('error', null);
  });

  it('calls onFilterChange with null when All is clicked', () => {
    const onFilterChange = vi.fn();
    renderWithProviders(<CallsTable calls={mockCalls} onFilterChange={onFilterChange} />);
    fireEvent.click(screen.getByText('All'));
    expect(onFilterChange).toHaveBeenCalledWith(null, null);
  });

  it('shows "No calls found" when filter produces empty result', () => {
    const successOnly: UsageCall[] = [makeCall({ id: 'c1', status: 'success' })];
    renderWithProviders(<CallsTable calls={successOnly} />);
    fireEvent.click(screen.getByText('Error'));
    expect(screen.getByText('No calls found')).toBeInTheDocument();
  });
});
