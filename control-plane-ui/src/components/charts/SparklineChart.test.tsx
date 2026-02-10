import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SparklineChart } from './SparklineChart';
import type { TimeSeriesPoint } from '../../hooks/usePrometheus';

describe('SparklineChart', () => {
  it('renders "No data" when data has less than 2 points', () => {
    render(<SparklineChart data={[]} />);
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders "No data" when data has exactly 1 point', () => {
    const data: TimeSeriesPoint[] = [{ timestamp: 123, value: 10 }];
    render(<SparklineChart data={data} />);
    expect(screen.getByText('No data')).toBeInTheDocument();
  });

  it('renders SVG when data has 2 or more points', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('renders polyline for line chart', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
      { timestamp: 300, value: 15 },
    ];
    const { container } = render(<SparklineChart data={data} />);
    const polyline = container.querySelector('polyline');
    expect(polyline).toBeInTheDocument();
    expect(polyline).toHaveAttribute('fill', 'none');
    expect(polyline).toHaveAttribute('stroke', '#3b82f6');
  });

  it('renders polygon for area when showArea is true', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} showArea />);
    const polygon = container.querySelector('polygon');
    expect(polygon).toBeInTheDocument();
  });

  it('does not render polygon when showArea is false', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} showArea={false} />);
    const polygon = container.querySelector('polygon');
    expect(polygon).not.toBeInTheDocument();
  });

  it('uses custom color prop', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} color="#ff0000" />);
    const polyline = container.querySelector('polyline');
    expect(polyline).toHaveAttribute('stroke', '#ff0000');
  });

  it('uses custom height and width', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} height={100} width={400} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveAttribute('height', '100');
    expect(svg).toHaveAttribute('width', '400');
  });

  it('applies custom className', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} className="custom-class" />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveClass('custom-class');
  });

  it('renders gradient definition', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: 20 },
    ];
    const { container } = render(<SparklineChart data={data} color="#3b82f6" />);
    const gradient = container.querySelector('linearGradient');
    expect(gradient).toBeInTheDocument();
    expect(gradient).toHaveAttribute('id', 'sparkline-3b82f6');
  });

  it('handles all zero values', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 0 },
      { timestamp: 200, value: 0 },
      { timestamp: 300, value: 0 },
    ];
    const { container } = render(<SparklineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('handles negative values', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: -10 },
      { timestamp: 200, value: -20 },
      { timestamp: 300, value: -5 },
    ];
    const { container } = render(<SparklineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('handles mixed positive and negative values', () => {
    const data: TimeSeriesPoint[] = [
      { timestamp: 100, value: 10 },
      { timestamp: 200, value: -5 },
      { timestamp: 300, value: 15 },
    ];
    const { container } = render(<SparklineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('handles large datasets', () => {
    const data: TimeSeriesPoint[] = Array.from({ length: 100 }, (_, i) => ({
      timestamp: 1000 + i * 60,
      value: Math.sin(i * 0.1) * 50 + 50,
    }));
    const { container } = render(<SparklineChart data={data} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('no data message uses correct dimensions for placeholder', () => {
    const { container } = render(<SparklineChart data={[]} height={80} width={300} />);
    const placeholder = container.querySelector('div');
    expect(placeholder).toHaveStyle({ height: '80px', width: '300px' });
  });
});
