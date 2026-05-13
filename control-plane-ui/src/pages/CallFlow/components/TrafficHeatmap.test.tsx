import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TrafficHeatmap } from './TrafficHeatmap';
import { HEATMAP_EMPTY_MESSAGE } from '../metrics';

describe('TrafficHeatmap', () => {
  it('renders the neutral empty state when no route traffic exists', () => {
    render(<TrafficHeatmap cells={[]} routes={[]} />);

    expect(screen.getByText(HEATMAP_EMPTY_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(/unavailable/i)).not.toBeInTheDocument();
  });
});
