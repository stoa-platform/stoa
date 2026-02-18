import { describe, it, expect } from 'vitest';
import {
  TableRowSkeleton,
  TableSkeleton,
  FullTableSkeleton,
  SubscriptionTableSkeleton,
} from '../TableSkeleton';
import { renderWithProviders } from '../../../test/helpers';

describe('TableRowSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(
      <table>
        <tbody>
          <TableRowSkeleton />
        </tbody>
      </table>
    );
    expect(container.querySelector('tr')).toBeInTheDocument();
  });

  it('renders default 5 columns', () => {
    const { container } = renderWithProviders(
      <table>
        <tbody>
          <TableRowSkeleton />
        </tbody>
      </table>
    );
    const cells = container.querySelectorAll('td');
    expect(cells.length).toBe(5);
  });

  it('renders custom column count', () => {
    const { container } = renderWithProviders(
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
  it('renders without crashing', () => {
    const { container } = renderWithProviders(
      <table>
        <TableSkeleton />
      </table>
    );
    expect(container.querySelector('tbody')).toBeInTheDocument();
  });

  it('renders default 5 rows', () => {
    const { container } = renderWithProviders(
      <table>
        <TableSkeleton />
      </table>
    );
    const rows = container.querySelectorAll('tr');
    expect(rows.length).toBe(5);
  });

  it('renders custom row count', () => {
    const { container } = renderWithProviders(
      <table>
        <TableSkeleton rows={3} />
      </table>
    );
    const rows = container.querySelectorAll('tr');
    expect(rows.length).toBe(3);
  });
});

describe('FullTableSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<FullTableSkeleton />);
    expect(container.querySelector('table')).toBeInTheDocument();
  });

  it('renders header row when headers provided', () => {
    renderWithProviders(<FullTableSkeleton headers={['Name', 'Status', 'Created']} />);

    // Header text should appear
    expect(document.querySelector('th')).toBeInTheDocument();
  });
});

describe('SubscriptionTableSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = renderWithProviders(<SubscriptionTableSkeleton />);
    expect(container.querySelector('table')).toBeInTheDocument();
  });

  it('renders subscription column headers', () => {
    renderWithProviders(<SubscriptionTableSkeleton />);

    expect(document.querySelector('th[class*="uppercase"]')).toBeInTheDocument();
  });

  it('renders default 5 rows', () => {
    const { container } = renderWithProviders(<SubscriptionTableSkeleton />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(5);
  });

  it('renders custom row count', () => {
    const { container } = renderWithProviders(<SubscriptionTableSkeleton rows={3} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows.length).toBe(3);
  });
});
