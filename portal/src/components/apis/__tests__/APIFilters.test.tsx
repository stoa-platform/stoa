/**
 * Tests for APIFilters component — Audience filter (CAB-1323)
 *
 * Verifies audience dropdown visibility, selection, badge display, and clear behavior.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { APIFilters } from '../APIFilters';

const defaultProps = {
  search: '',
  onSearchChange: vi.fn(),
  category: '',
  onCategoryChange: vi.fn(),
  categories: ['Finance', 'Logistics'],
  universe: '',
  onUniverseChange: vi.fn(),
  universes: [
    { id: 'prod', label: 'Production' },
    { id: 'staging', label: 'Staging' },
  ],
  audience: '',
  onAudienceChange: vi.fn(),
  audienceOptions: [
    { id: 'public', label: 'Public' },
    { id: 'internal', label: 'Internal' },
    { id: 'partner', label: 'Partner' },
  ],
  isLoading: false,
};

describe('APIFilters — Audience (CAB-1323)', () => {
  it('should show audience dropdown when 2+ options', () => {
    render(
      <APIFilters
        {...defaultProps}
        audienceOptions={[
          { id: 'public', label: 'Public' },
          { id: 'internal', label: 'Internal' },
        ]}
      />
    );

    const selects = screen.getAllByRole('combobox');
    const audienceSelect = selects.find((s) => {
      const options = s.querySelectorAll('option');
      return Array.from(options).some((o) => o.textContent === 'All Audiences');
    });
    expect(audienceSelect).toBeInTheDocument();
  });

  it('should hide audience dropdown when 0-1 options', () => {
    render(<APIFilters {...defaultProps} audienceOptions={[{ id: 'public', label: 'Public' }]} />);

    const selects = screen.getAllByRole('combobox');
    const audienceSelect = selects.find((s) => {
      const options = s.querySelectorAll('option');
      return Array.from(options).some((o) => o.textContent === 'All Audiences');
    });
    expect(audienceSelect).toBeUndefined();
  });

  it('should call onAudienceChange when selection changes', () => {
    const onAudienceChange = vi.fn();
    render(<APIFilters {...defaultProps} onAudienceChange={onAudienceChange} />);

    const selects = screen.getAllByRole('combobox');
    const audienceSelect = selects.find((s) => {
      const options = s.querySelectorAll('option');
      return Array.from(options).some((o) => o.textContent === 'All Audiences');
    })!;

    fireEvent.change(audienceSelect, { target: { value: 'internal' } });
    expect(onAudienceChange).toHaveBeenCalledWith('internal');
  });

  it('should show audience badge in active filters when audience is selected', () => {
    render(<APIFilters {...defaultProps} audience="partner" />);

    // "Partner" appears in both dropdown option and active filter badge
    const partnerElements = screen.getAllByText('Partner');
    expect(partnerElements.length).toBeGreaterThanOrEqual(2); // option + badge
    expect(screen.getByText('Active filters:')).toBeInTheDocument();
  });

  it('should clear audience when clear filters button is clicked', () => {
    const onAudienceChange = vi.fn();
    const onSearchChange = vi.fn();
    const onCategoryChange = vi.fn();
    const onUniverseChange = vi.fn();

    render(
      <APIFilters
        {...defaultProps}
        audience="internal"
        onAudienceChange={onAudienceChange}
        onSearchChange={onSearchChange}
        onCategoryChange={onCategoryChange}
        onUniverseChange={onUniverseChange}
      />
    );

    const clearButton = screen.getByText('Clear');
    fireEvent.click(clearButton);

    expect(onAudienceChange).toHaveBeenCalledWith('');
    expect(onSearchChange).toHaveBeenCalledWith('');
    expect(onCategoryChange).toHaveBeenCalledWith('');
    expect(onUniverseChange).toHaveBeenCalledWith('');
  });
});
