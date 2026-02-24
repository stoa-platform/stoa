import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  TableRowSkeleton,
  TableSkeleton,
  FullTableSkeleton,
  SubscriptionTableSkeleton,
} from './TableSkeleton';

describe('TableRowSkeleton', () => {
  it('should render default 5 columns', () => {
    const { container } = render(
      <table>
        <tbody>
          <TableRowSkeleton />
        </tbody>
      </table>
    );
    const cells = container.querySelectorAll('td');
    expect(cells.length).toBe(5);
  });

  it('should render custom column count', () => {
    const { container } = render(
      <table>
        <tbody>
          <TableRowSkeleton columns={3} />
        </tbody>
      </table>
    );
    const cells = container.querySelectorAll('td');
    expect(cells.length).toBe(3);
  });
});

describe('TableSkeleton', () => {
  it('should render default 5 rows', () => {
    const { container } = render(
      <table>
        <TableSkeleton />
      </table>
    );
    const rows = container.querySelectorAll('tr');
    expect(rows.length).toBe(5);
  });

  it('should render custom row and column count', () => {
    const { container } = render(
      <table>
        <TableSkeleton rows={3} columns={4} />
      </table>
    );
    const rows = container.querySelectorAll('tr');
    expect(rows.length).toBe(3);
    // Each row has 4 cells
    const firstRowCells = rows[0].querySelectorAll('td');
    expect(firstRowCells.length).toBe(4);
  });
});

describe('FullTableSkeleton', () => {
  it('should render table with header and body rows', () => {
    const { container } = render(<FullTableSkeleton />);
    const headerCells = container.querySelectorAll('th');
    expect(headerCells.length).toBe(5); // default columns
    const bodyRows = container.querySelectorAll('tbody tr');
    expect(bodyRows.length).toBe(5); // default rows
  });

  it('should render string headers when provided', () => {
    render(<FullTableSkeleton headers={['Name', 'Status', 'Created']} />);
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
  });

  it('should use headers length for column count', () => {
    const { container } = render(<FullTableSkeleton headers={['A', 'B']} rows={2} />);
    const headerCells = container.querySelectorAll('th');
    expect(headerCells.length).toBe(2);
    const bodyCells = container.querySelectorAll('tbody tr:first-child td');
    expect(bodyCells.length).toBe(2);
  });

  it('should render skeleton headers when no strings provided', () => {
    const { container } = render(<FullTableSkeleton columns={3} />);
    const headerCells = container.querySelectorAll('th');
    expect(headerCells.length).toBe(3);
    // Each should have a Skeleton inside
    const skeletons = container.querySelectorAll('th [class*="animate-pulse"]');
    expect(skeletons.length).toBe(3);
  });
});

describe('SubscriptionTableSkeleton', () => {
  it('should render with subscription-specific headers', () => {
    render(<SubscriptionTableSkeleton />);
    expect(screen.getByText('Server')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
    expect(screen.getByText('API Key')).toBeInTheDocument();
    expect(screen.getByText('Created')).toBeInTheDocument();
    expect(screen.getByText('Actions')).toBeInTheDocument();
  });

  it('should render default 5 rows', () => {
    const { container } = render(<SubscriptionTableSkeleton />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(5);
  });

  it('should render custom row count', () => {
    const { container } = render(<SubscriptionTableSkeleton rows={3} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(3);
  });

  it('should render server cell with icon and text skeletons', () => {
    const { container } = render(<SubscriptionTableSkeleton />);
    const firstServerCell = container.querySelector('tbody tr:first-child td');
    const skeletons = firstServerCell?.querySelectorAll('[class*="animate-pulse"]');
    expect(skeletons!.length).toBeGreaterThanOrEqual(2);
  });

  it('should render action buttons placeholder', () => {
    const { container } = render(<SubscriptionTableSkeleton />);
    const actionCells = container.querySelectorAll('tbody tr:first-child td:last-child');
    expect(actionCells.length).toBe(1);
    const actionSkeletons = actionCells[0].querySelectorAll('[class*="animate-pulse"]');
    expect(actionSkeletons.length).toBe(2); // 2 action buttons
  });
});
