import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary, ErrorFallback, CompactErrorFallback } from './ErrorBoundary';

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

  it('should display friendly message when error is provided', () => {
    render(<ErrorFallback error={new Error('Test error message')} />);
    expect(screen.getByText('Something went wrong. Please try again later.')).toBeInTheDocument();
  });

  it('should display friendly message for HTTP status errors', () => {
    render(<ErrorFallback error={new Error('Request failed with status code 401')} />);
    expect(screen.getByText('Your session has expired. Please log in again.')).toBeInTheDocument();
  });

  it('should show Login button for 401 errors', () => {
    render(<ErrorFallback error={new Error('Request failed with status code 401')} />);
    expect(screen.getByText('Log In Again')).toBeInTheDocument();
    expect(screen.queryByText('Try Again')).not.toBeInTheDocument();
  });

  it('should show Application Updated message for ChunkLoadError', () => {
    const error = new Error('Loading chunk abc123 failed');
    render(<ErrorFallback error={error} />);
    expect(screen.getByText('Application Updated')).toBeInTheDocument();
    expect(screen.getByText('A new version is available. Please reload the page.')).toBeInTheDocument();
    expect(screen.getByText('Reload')).toBeInTheDocument();
    // Go Home should not appear for chunk errors
    expect(screen.queryByText('Go Home')).not.toBeInTheDocument();
  });

  it('should show Application Updated for dynamically imported module errors', () => {
    const error = new Error('Failed to fetch dynamically imported module: /assets/foo.js');
    render(<ErrorFallback error={error} />);
    expect(screen.getByText('Application Updated')).toBeInTheDocument();
    expect(screen.getByText('Reload')).toBeInTheDocument();
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
      value: { reload: reloadMock, href: '/' },
      writable: true,
    });

    render(<ErrorFallback />);
    fireEvent.click(screen.getByText('Try Again'));
    expect(reloadMock).toHaveBeenCalledTimes(1);
  });

  it('should reload page when Reload is clicked for chunk errors', () => {
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock, href: '/' },
      writable: true,
    });

    const error = new Error('Loading chunk abc123 failed');
    const resetError = vi.fn();
    render(<ErrorFallback error={error} resetError={resetError} />);
    fireEvent.click(screen.getByText('Reload'));
    // ChunkLoadError always does full reload, not resetError
    expect(reloadMock).toHaveBeenCalledTimes(1);
    expect(resetError).not.toHaveBeenCalled();
  });

  it('should navigate home when Go Home is clicked', () => {
    render(<ErrorFallback />);
    fireEvent.click(screen.getByText('Go Home'));
    expect(window.location.href).toBe('/');
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

// Component that throws during render
function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Test component error');
  }
  return <span>Working component</span>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('should render children when no error', () => {
    render(
      <ErrorBoundary>
        <span>Child content</span>
      </ErrorBoundary>
    );
    expect(screen.getByText('Child content')).toBeInTheDocument();
  });

  it('should render ErrorFallback when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByText('Working component')).not.toBeInTheDocument();
  });

  it('should render custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<span>Custom error UI</span>}>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(screen.getByText('Custom error UI')).toBeInTheDocument();
  });

  it('should call onError callback when error occurs', () => {
    const onError = vi.fn();
    render(
      <ErrorBoundary onError={onError}>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    expect(onError).toHaveBeenCalledOnce();
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: 'Test component error' }),
      expect.objectContaining({ componentStack: expect.any(String) })
    );
  });

  it('should reset error state when resetError is called', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    );
    // Error state — shows fallback
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();

    // Click Try Again — resets error but child will re-throw
    fireEvent.click(screen.getByText('Try Again'));

    // Still in error state because ThrowingComponent keeps throwing
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });
});
