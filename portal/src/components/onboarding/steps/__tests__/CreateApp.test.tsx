import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { CreateApp } from '../CreateApp';
import { renderWithProviders, mockApplication } from '../../../../test/helpers';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

const mockMutateAsync = vi.fn();
vi.mock('../../../../hooks/useApplications', () => ({
  useCreateApplication: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
    error: null,
  }),
}));

describe('CreateApp', () => {
  const onCreated = vi.fn();
  const onBack = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    onCreated.mockReset();
    onBack.mockReset();
    mockMutateAsync.mockResolvedValue(mockApplication());
  });

  it('renders title via i18n', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByText('createApp.title')).toBeInTheDocument();
  });

  it('renders subtitle via i18n', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByText('createApp.subtitle')).toBeInTheDocument();
  });

  it('renders display name input', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByLabelText('createApp.appName')).toBeInTheDocument();
  });

  it('renders slug input', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByLabelText('createApp.slug')).toBeInTheDocument();
  });

  it('renders description textarea', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByLabelText('createApp.description')).toBeInTheDocument();
  });

  it('renders Back button', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByText('createApp.back')).toBeInTheDocument();
  });

  it('renders Submit button', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByText('createApp.submit')).toBeInTheDocument();
  });

  it('calls onBack when Back clicked', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    fireEvent.click(screen.getByText('createApp.back'));

    expect(onBack).toHaveBeenCalledOnce();
  });

  it('submit button is disabled when display name is empty', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    expect(screen.getByText('createApp.submit')).toBeDisabled();
  });

  it('auto-fills slug from display name', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My Test App' },
    });

    const slugInput = screen.getByLabelText('createApp.slug') as HTMLInputElement;
    expect(slugInput.value).toBe('my-test-app');
  });

  it('enables submit when display name is entered', () => {
    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My App' },
    });

    expect(screen.getByText('createApp.submit')).not.toBeDisabled();
  });

  it('calls onCreated with result after successful submit', async () => {
    const createdApp = mockApplication({ name: 'my-app' });
    mockMutateAsync.mockResolvedValue(createdApp);

    renderWithProviders(<CreateApp onCreated={onCreated} onBack={onBack} />);

    fireEvent.change(screen.getByLabelText('createApp.appName'), {
      target: { value: 'My App' },
    });

    fireEvent.submit(screen.getByRole('button', { name: 'createApp.submit' }).closest('form')!);

    await vi.waitFor(() => {
      expect(onCreated).toHaveBeenCalledWith(createdApp);
    });
  });
});
