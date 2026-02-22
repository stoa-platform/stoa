/**
 * Tests for CreateApp step (CAB-1306)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { CreateApp } from './CreateApp';
import { renderWithProviders, mockApplication } from '../../../test/helpers';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }));

const mockMutateAsync = vi.fn();
const mockUseCreateApplication = vi.fn();

vi.mock('../../../hooks/useApplications', () => ({
  useCreateApplication: () => mockUseCreateApplication(),
}));

describe('CreateApp', () => {
  const onCreated = vi.fn();
  const onBack = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseCreateApplication.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
      error: null,
    });
    mockMutateAsync.mockResolvedValue(mockApplication());
  });

  it('renders the form title', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    expect(screen.getByText('createApp.title')).toBeInTheDocument();
  });

  it('renders display name and slug text inputs', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    expect(screen.getByLabelText('createApp.appName')).toBeInTheDocument();
    expect(screen.getByLabelText('createApp.slug')).toBeInTheDocument();
  });

  it('submit button is disabled when display name is empty', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    const submitBtn = screen.getByRole('button', { name: 'createApp.submit' });
    expect(submitBtn).toBeDisabled();
  });

  it('submit button is enabled after typing a display name', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My App' },
    });
    expect(screen.getByRole('button', { name: 'createApp.submit' })).not.toBeDisabled();
  });

  it('calls onCreated with the created app after successful submission', async () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My App' },
    });
    const form = screen.getByRole('button', { name: 'createApp.submit' }).closest('form');
    fireEvent.submit(form!);
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(mockApplication()));
  });

  it('calls onBack when Back button is clicked', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    fireEvent.click(screen.getByRole('button', { name: 'createApp.back' }));
    expect(onBack).toHaveBeenCalled();
  });

  it('shows spinner when isPending is true', () => {
    mockUseCreateApplication.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: true,
      error: null,
    });
    const { container } = renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('shows error message when mutation fails', () => {
    mockUseCreateApplication.mockReturnValue({
      mutateAsync: mockMutateAsync,
      isPending: false,
      error: { message: 'Application name already taken' },
    });
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    expect(screen.getByText('Application name already taken')).toBeInTheDocument();
  });

  it('auto-populates slug from display name', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);
    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My App' },
    });
    const slugInput = screen.getByLabelText('createApp.slug') as HTMLInputElement;
    expect(slugInput.value).toBe('my-app');
  });
});
