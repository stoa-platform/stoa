import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorFallback, CompactErrorFallback } from './ErrorFallback';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}));

describe('ErrorFallback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should render default title and description', () => {
    render(<ErrorFallback />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText(/We encountered an unexpected error/)).toBeInTheDocument();
  });

  it('should render custom title and description', () => {
    render(<ErrorFallback title="Custom Error" description="Custom message" />);
    expect(screen.getByText('Custom Error')).toBeInTheDocument();
    expect(screen.getByText('Custom message')).toBeInTheDocument();
  });

  it('should display error details when error is provided', () => {
    render(<ErrorFallback error={new Error('Test error message')} />);
    expect(screen.getByText('Test error message')).toBeInTheDocument();
    expect(screen.getByText('Error details:')).toBeInTheDocument();
  });

  it('should not display error details when no error', () => {
    render(<ErrorFallback />);
    expect(screen.queryByText('Error details:')).not.toBeInTheDocument();
  });

  it('should call resetError when Try Again is clicked', () => {
    const resetError = vi.fn();
    render(<ErrorFallback resetError={resetError} />);
    fireEvent.click(screen.getByText('Try Again'));
    expect(resetError).toHaveBeenCalledTimes(1);
  });

  it('should reload page when Try Again is clicked without resetError', () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    });

    render(<ErrorFallback />);
    fireEvent.click(screen.getByText('Try Again'));
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it('should navigate home and reset error when Go Home is clicked', () => {
    const resetError = vi.fn();
    render(<ErrorFallback resetError={resetError} />);
    fireEvent.click(screen.getByText('Go Home'));
    expect(resetError).toHaveBeenCalledTimes(1);
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });

  it('should navigate home without reset when no resetError', () => {
    render(<ErrorFallback />);
    fireEvent.click(screen.getByText('Go Home'));
    expect(mockNavigate).toHaveBeenCalledWith('/');
  });
});

describe('CompactErrorFallback', () => {
  it('should render default message', () => {
    render(<CompactErrorFallback />);
    expect(screen.getByText('Failed to load')).toBeInTheDocument();
  });

  it('should render custom message', () => {
    render(<CompactErrorFallback message="Custom failure" />);
    expect(screen.getByText('Custom failure')).toBeInTheDocument();
  });

  it('should show Retry button when resetError is provided', () => {
    const resetError = vi.fn();
    render(<CompactErrorFallback resetError={resetError} />);
    fireEvent.click(screen.getByText('Retry'));
    expect(resetError).toHaveBeenCalledTimes(1);
  });

  it('should not show Retry button when no resetError', () => {
    render(<CompactErrorFallback />);
    expect(screen.queryByText('Retry')).not.toBeInTheDocument();
  });
});
