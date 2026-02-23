import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DeployProgress } from '../DeployProgress';

describe('DeployProgress', () => {
  it('shows all steps as pending when no current step', () => {
    render(<DeployProgress currentStep={null} status={null} />);

    expect(screen.getByText('Validating')).toBeInTheDocument();
    expect(screen.getByText('Syncing')).toBeInTheDocument();
    expect(screen.getByText('Health Check')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
  });

  it('marks steps before current as done and current as active', () => {
    const { container } = render(<DeployProgress currentStep="sync" status="in_progress" />);

    // "Validating" (init) is before sync → done (green)
    const labels = container.querySelectorAll('span');
    const validatingLabel = Array.from(labels).find((el) => el.textContent === 'Validating');
    expect(validatingLabel?.className).toContain('text-green-600');

    // "Syncing" is current → active (blue, font-medium)
    const syncingLabel = Array.from(labels).find((el) => el.textContent === 'Syncing');
    expect(syncingLabel?.className).toContain('text-blue-600');
    expect(syncingLabel?.className).toContain('font-medium');

    // "Health Check" is after → pending (gray)
    const healthLabel = Array.from(labels).find((el) => el.textContent === 'Health Check');
    expect(healthLabel?.className).toContain('text-neutral-400');
  });

  it('marks all steps as done on success', () => {
    const { container } = render(<DeployProgress currentStep="complete" status="success" />);

    const labels = container.querySelectorAll('span');
    const allGreen = Array.from(labels).every((el) => el.className.includes('text-green-600'));
    expect(allGreen).toBe(true);
  });

  it('marks failed step with red styling on failure', () => {
    const { container } = render(<DeployProgress currentStep="health-check" status="failed" />);

    const labels = container.querySelectorAll('span');
    // init and sync before health-check → done (green)
    const validatingLabel = Array.from(labels).find((el) => el.textContent === 'Validating');
    expect(validatingLabel?.className).toContain('text-green-600');

    const syncingLabel = Array.from(labels).find((el) => el.textContent === 'Syncing');
    expect(syncingLabel?.className).toContain('text-green-600');

    // health-check is the failed step → red
    const healthLabel = Array.from(labels).find((el) => el.textContent === 'Health Check');
    expect(healthLabel?.className).toContain('text-red-600');

    // complete is after → pending
    const completeLabel = Array.from(labels).find((el) => el.textContent === 'Complete');
    expect(completeLabel?.className).toContain('text-neutral-400');
  });

  it('renders 3 connector lines between 4 steps', () => {
    const { container } = render(<DeployProgress currentStep={null} status={null} />);

    // Connector lines have h-0.5 class
    const connectors = container.querySelectorAll('.h-0\\.5');
    expect(connectors).toHaveLength(3);
  });
});
