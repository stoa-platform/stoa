/**
 * Tests for QuotaBar (CAB-1907)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { QuotaBar } from './QuotaBar';
import { renderWithProviders } from '../../test/helpers';

describe('QuotaBar', () => {
  // ── Rendering ──────────────────────────────────────────────────────────────

  it('renders used and limit values', () => {
    renderWithProviders(<QuotaBar used={300} limit={1000} />);
    expect(screen.getByText(/300.*\/.*1,000/)).toBeInTheDocument();
  });

  it('renders the label when provided', () => {
    renderWithProviders(<QuotaBar used={50} limit={100} label="basic" />);
    expect(screen.getByText('basic')).toBeInTheDocument();
  });

  it('does not render a label element when label is omitted', () => {
    renderWithProviders(<QuotaBar used={50} limit={100} />);
    // No label span — only the percentage/value text
    expect(screen.queryByText('basic')).not.toBeInTheDocument();
  });

  it('shows percentage by default', () => {
    renderWithProviders(<QuotaBar used={50} limit={100} />);
    expect(screen.getByText(/50%/)).toBeInTheDocument();
  });

  it('hides percentage when showPercent is false', () => {
    renderWithProviders(<QuotaBar used={50} limit={100} showPercent={false} />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    // Values still visible
    expect(screen.getByText(/50.*\/.*100/)).toBeInTheDocument();
  });

  // ── Percentage calculation ─────────────────────────────────────────────────

  it('calculates 0% when used is 0', () => {
    renderWithProviders(<QuotaBar used={0} limit={100} />);
    expect(screen.getByText(/0%/)).toBeInTheDocument();
  });

  it('calculates 100% when used equals limit', () => {
    renderWithProviders(<QuotaBar used={100} limit={100} />);
    expect(screen.getByText(/100%/)).toBeInTheDocument();
  });

  it('caps percentage at 100% when used exceeds limit', () => {
    renderWithProviders(<QuotaBar used={150} limit={100} />);
    expect(screen.getByText(/100%/)).toBeInTheDocument();
  });

  it('shows 0% when limit is 0 (guards against division by zero)', () => {
    renderWithProviders(<QuotaBar used={0} limit={0} />);
    expect(screen.getByText(/0%/)).toBeInTheDocument();
  });

  it('rounds percentage to nearest integer', () => {
    // 1/3 = 33.33% → rounds to 33%
    renderWithProviders(<QuotaBar used={1} limit={3} />);
    expect(screen.getByText(/33%/)).toBeInTheDocument();
  });

  // ── Color coding ───────────────────────────────────────────────────────────

  it('applies green bar class when usage is below 60%', () => {
    const { container } = renderWithProviders(<QuotaBar used={59} limit={100} />);
    expect(container.querySelector('.bg-emerald-500')).toBeInTheDocument();
  });

  it('applies amber bar class when usage is exactly 60%', () => {
    const { container } = renderWithProviders(<QuotaBar used={60} limit={100} />);
    expect(container.querySelector('.bg-amber-500')).toBeInTheDocument();
  });

  it('applies amber bar class when usage is between 60 and 80%', () => {
    const { container } = renderWithProviders(<QuotaBar used={75} limit={100} />);
    expect(container.querySelector('.bg-amber-500')).toBeInTheDocument();
  });

  it('applies red bar class when usage is exactly 80%', () => {
    const { container } = renderWithProviders(<QuotaBar used={80} limit={100} />);
    expect(container.querySelector('.bg-red-500')).toBeInTheDocument();
  });

  it('applies red bar class when usage exceeds 80%', () => {
    const { container } = renderWithProviders(<QuotaBar used={99} limit={100} />);
    expect(container.querySelector('.bg-red-500')).toBeInTheDocument();
  });

  // ── Bar width ─────────────────────────────────────────────────────────────

  it('sets bar width style proportional to usage percentage', () => {
    const { container } = renderWithProviders(<QuotaBar used={40} limit={100} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar?.style.width).toBe('40%');
  });

  it('sets bar width to 100% when usage is at limit', () => {
    const { container } = renderWithProviders(<QuotaBar used={100} limit={100} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar?.style.width).toBe('100%');
  });

  it('sets bar width to 0% when used is 0', () => {
    const { container } = renderWithProviders(<QuotaBar used={0} limit={100} />);
    const bar = container.querySelector('[style]') as HTMLElement;
    expect(bar?.style.width).toBe('0%');
  });

  // ── Number formatting ─────────────────────────────────────────────────────

  it('formats large numbers with locale separators', () => {
    renderWithProviders(<QuotaBar used={1500} limit={10000} />);
    expect(screen.getByText(/1,500.*\/.*10,000/)).toBeInTheDocument();
  });
});
