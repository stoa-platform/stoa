import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UACSpotlight } from './UACSpotlight';

const defaultProps = {
  onDismiss: vi.fn(),
};

describe('UACSpotlight', () => {
  it('should render educational content', () => {
    render(<UACSpotlight {...defaultProps} />);
    expect(screen.getByText('Did you know?')).toBeInTheDocument();
    expect(screen.getByText('STOA uses Universal API Contracts (UAC).')).toBeInTheDocument();
  });

  it('should render description', () => {
    render(<UACSpotlight {...defaultProps} />);
    expect(screen.getByText(/Define your API once, expose it everywhere/)).toBeInTheDocument();
  });

  it('should render docs link with default URL', () => {
    render(<UACSpotlight {...defaultProps} />);
    const link = screen.getByText('See how it works');
    expect(link).toHaveAttribute('href', '/docs/uac');
  });

  it('should render docs link with custom URL', () => {
    render(<UACSpotlight {...defaultProps} docsUrl="/custom/docs" />);
    const link = screen.getByText('See how it works');
    expect(link).toHaveAttribute('href', '/custom/docs');
  });

  it('should call onDismiss when Got it button clicked', () => {
    render(<UACSpotlight {...defaultProps} />);
    fireEvent.click(screen.getByText('Got it'));
    expect(defaultProps.onDismiss).toHaveBeenCalled();
  });

  it('should call onDismiss when X button clicked', () => {
    render(<UACSpotlight {...defaultProps} />);
    fireEvent.click(screen.getByLabelText('Dismiss'));
    expect(defaultProps.onDismiss).toHaveBeenCalled();
  });

  it('should have alert role', () => {
    render(<UACSpotlight {...defaultProps} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('should apply custom className', () => {
    render(<UACSpotlight {...defaultProps} className="my-class" />);
    expect(screen.getByRole('alert')).toHaveClass('my-class');
  });
});
