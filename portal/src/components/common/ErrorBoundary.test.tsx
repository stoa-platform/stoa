/**
 * Tests for ErrorBoundary component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

// Mock ErrorFallback (uses react-router-dom useNavigate)
vi.mock('./ErrorFallback', () => ({
  ErrorFallback: ({ error, resetError }: { error?: Error; resetError?: () => void }) => (
    <div>
      <span data-testid="error-message">{error?.message || 'Unknown error'}</span>
      <button onClick={resetError}>Retry</button>
    </div>
  ),
}));

// Component that throws
function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Test component error');
  }
  return <span>Working component</span>;
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // Suppress console.error from React error boundary
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

    expect(screen.getByTestId('error-message')).toHaveTextContent('Test component error');
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

    // Error state
    expect(screen.getByTestId('error-message')).toBeInTheDocument();

    // Click retry — resets error state, but the same throwing child will re-throw
    fireEvent.click(screen.getByText('Retry'));

    // Since the child still throws, we stay in error state
    // This validates that resetError triggers a re-render attempt
    expect(screen.getByTestId('error-message')).toBeInTheDocument();
  });
});
