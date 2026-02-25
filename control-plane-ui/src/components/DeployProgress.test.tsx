import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DeployProgress } from './DeployProgress';

describe('DeployProgress', () => {
  it('renders all 4 step labels', () => {
    render(<DeployProgress currentStep={null} status={null} />);
    expect(screen.getByText('Validating')).toBeInTheDocument();
    expect(screen.getByText('Syncing')).toBeInTheDocument();
    expect(screen.getByText('Health Check')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
  });

  it('shows all steps as pending when no current step', () => {
    const { container } = render(<DeployProgress currentStep={null} status={null} />);
    const pendingCircles = container.querySelectorAll('.bg-neutral-100');
    expect(pendingCircles.length).toBe(4);
  });

  it('shows active step with blue styling', () => {
    const { container } = render(<DeployProgress currentStep="sync" status="in_progress" />);
    const activeCircles = container.querySelectorAll('.bg-blue-100');
    expect(activeCircles.length).toBe(1);
  });

  it('shows done steps with green styling when status is success', () => {
    const { container } = render(<DeployProgress currentStep="complete" status="success" />);
    const doneCircles = container.querySelectorAll('.bg-green-100');
    expect(doneCircles.length).toBe(4);
  });

  it('shows failed step with red styling', () => {
    const { container } = render(<DeployProgress currentStep="sync" status="failed" />);
    const failedCircles = container.querySelectorAll('.bg-red-100');
    expect(failedCircles.length).toBe(1);
  });

  it('shows completed steps before failed step as done', () => {
    const { container } = render(<DeployProgress currentStep="sync" status="failed" />);
    const doneCircles = container.querySelectorAll('.bg-green-100');
    expect(doneCircles.length).toBe(1);
  });
});
