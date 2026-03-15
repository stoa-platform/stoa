import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EnvironmentPipeline } from '../EnvironmentPipeline';

describe('EnvironmentPipeline', () => {
  // ── Full mode (default) ──────────────────────────────────────────────────

  describe('full mode (compact=false)', () => {
    it('renders all 3 environment labels', () => {
      render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} deployed_prod={false} />
      );
      expect(screen.getByText('DEV')).toBeInTheDocument();
      expect(screen.getByText('STG')).toBeInTheDocument();
      expect(screen.getByText('PROD')).toBeInTheDocument();
    });

    it('applies green styling to deployed environments', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={true} deployed_prod={false} />
      );
      const labels = [...container.querySelectorAll('span')];
      const devLabel = labels.find((el) => el.textContent === 'DEV');
      const stgLabel = labels.find((el) => el.textContent === 'STG');
      const prodLabel = labels.find((el) => el.textContent === 'PROD');

      expect(devLabel?.className).toContain('text-green-700');
      expect(stgLabel?.className).toContain('text-green-700');
      expect(prodLabel?.className).not.toContain('text-green-700');
    });

    it('applies neutral styling to non-deployed environments', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} deployed_prod={false} />
      );
      const labels = [...container.querySelectorAll('span')];
      const devLabel = labels.find((el) => el.textContent === 'DEV');
      expect(devLabel?.className).toContain('text-neutral-400');
    });

    it('renders green border on deployed environment cards', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={false} />
      );
      const cards = container.querySelectorAll('.rounded-lg');
      const devCard = cards[0];
      expect(devCard.className).toContain('border-green-300');
    });

    it('renders neutral border on non-deployed environment cards', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} />
      );
      const cards = container.querySelectorAll('.rounded-lg');
      const devCard = cards[0];
      expect(devCard.className).toContain('border-neutral-200');
    });

    it('defaults deployed_prod to false when not provided', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={true} />
      );
      const labels = [...container.querySelectorAll('span')];
      const prodLabel = labels.find((el) => el.textContent === 'PROD');
      expect(prodLabel?.className).toContain('text-neutral-400');
    });

    it('renders 2 arrow connectors between 3 nodes', () => {
      // ArrowRight icons are rendered as SVGs with lucide classes
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} />
      );
      // The outer flex container (not compact) renders 3 items, each an ArrowRight between nodes
      // We check the structure: the top-level flex has 3 children
      const topFlex = container.firstChild as HTMLElement;
      expect(topFlex.children).toHaveLength(3);
    });

    it('renders all 3 environments as deployed when all props are true', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={true} deployed_prod={true} />
      );
      const labels = [...container.querySelectorAll('span')];
      const envLabels = labels.filter((el) =>
        ['DEV', 'STG', 'PROD'].includes(el.textContent || '')
      );
      envLabels.forEach((label) => {
        expect(label.className).toContain('text-green-700');
      });
    });
  });

  // ── Compact mode ─────────────────────────────────────────────────────────

  describe('compact mode', () => {
    it('renders all 3 environment labels in compact mode', () => {
      render(<EnvironmentPipeline deployed_dev={false} deployed_staging={false} compact={true} />);
      expect(screen.getByText('DEV')).toBeInTheDocument();
      expect(screen.getByText('STG')).toBeInTheDocument();
      expect(screen.getByText('PROD')).toBeInTheDocument();
    });

    it('renders inline badges (span with text-xs) in compact mode', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={false} compact={true} />
      );
      const badges = container.querySelectorAll('span.inline-flex');
      expect(badges.length).toBe(3);
    });

    it('applies green badge styling to deployed envs in compact mode', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={true} deployed_staging={false} compact={true} />
      );
      const badges = [...container.querySelectorAll('span.inline-flex')];
      const devBadge = badges.find((el) => el.textContent === 'DEV');
      expect(devBadge?.className).toContain('bg-green-100');
      expect(devBadge?.className).toContain('text-green-800');
    });

    it('applies neutral badge styling to non-deployed envs in compact mode', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} compact={true} />
      );
      const badges = [...container.querySelectorAll('span.inline-flex')];
      const devBadge = badges.find((el) => el.textContent === 'DEV');
      expect(devBadge?.className).toContain('bg-neutral-100');
      expect(devBadge?.className).toContain('text-neutral-400');
    });

    it('does not render full card layout in compact mode', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} compact={true} />
      );
      // Full mode uses rounded-lg cards with min-w-[80px]; compact does not
      const cards = container.querySelectorAll('.min-w-\\[80px\\]');
      expect(cards).toHaveLength(0);
    });
  });

  // ── Edge cases ────────────────────────────────────────────────────────────

  describe('edge cases', () => {
    it('renders correctly when only STG is deployed', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={true} deployed_prod={false} />
      );
      const labels = [...container.querySelectorAll('span')];
      const devLabel = labels.find((el) => el.textContent === 'DEV');
      const stgLabel = labels.find((el) => el.textContent === 'STG');
      expect(devLabel?.className).toContain('text-neutral-400');
      expect(stgLabel?.className).toContain('text-green-700');
    });

    it('renders correctly when only PROD is deployed', () => {
      const { container } = render(
        <EnvironmentPipeline deployed_dev={false} deployed_staging={false} deployed_prod={true} />
      );
      const labels = [...container.querySelectorAll('span')];
      const prodLabel = labels.find((el) => el.textContent === 'PROD');
      expect(prodLabel?.className).toContain('text-green-700');
    });
  });
});
