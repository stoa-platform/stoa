import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TrafficHeatmap } from './TrafficHeatmap';
import { HEATMAP_UNAVAILABLE_MESSAGE } from '../metrics';

describe('TrafficHeatmap', () => {
  it('renders the real-heatmap-not-wired state when no range-query heatmap data exists', () => {
    render(<TrafficHeatmap cells={[]} routes={[]} />);

    expect(screen.getByText(HEATMAP_UNAVAILABLE_MESSAGE)).toBeInTheDocument();
  });
});
