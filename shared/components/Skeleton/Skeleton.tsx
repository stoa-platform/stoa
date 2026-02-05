// ============================================================================
// Base Skeleton
// ============================================================================

interface SkeletonProps {
  className?: string;
}

/**
 * Base skeleton component for loading states.
 * Shows an animated pulse placeholder while content loads.
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded bg-neutral-200 ${className}`}
      aria-hidden="true"
    />
  );
}

// ============================================================================
// Text Skeleton
// ============================================================================

export function TextSkeleton({
  lines = 3,
  className = '',
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={`h-4 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Avatar Skeleton
// ============================================================================

export function AvatarSkeleton({
  size = 'md',
}: {
  size?: 'sm' | 'md' | 'lg';
}) {
  const sizeClasses = {
    sm: 'h-8 w-8',
    md: 'h-10 w-10',
    lg: 'h-12 w-12',
  };

  return <Skeleton className={`${sizeClasses[size]} rounded-full`} />;
}

// ============================================================================
// Button Skeleton
// ============================================================================

export function ButtonSkeleton({
  size = 'md',
}: {
  size?: 'sm' | 'md' | 'lg';
}) {
  const sizeClasses = {
    sm: 'h-8 w-20',
    md: 'h-10 w-24',
    lg: 'h-12 w-32',
  };

  return <Skeleton className={`${sizeClasses[size]} rounded-lg`} />;
}

// ============================================================================
// Card Skeleton
// ============================================================================

export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`bg-white rounded-lg border border-neutral-200 p-6 ${className}`}>
      <div className="flex items-center gap-3 mb-4">
        <Skeleton className="h-10 w-10 rounded-lg" />
        <div className="flex-1">
          <Skeleton className="h-4 w-32 mb-2" />
          <Skeleton className="h-3 w-48" />
        </div>
      </div>
      <TextSkeleton lines={2} />
    </div>
  );
}

// ============================================================================
// Table Skeleton
// ============================================================================

interface TableRowSkeletonProps {
  columns?: number;
}

export function TableRowSkeleton({ columns = 5 }: TableRowSkeletonProps) {
  return (
    <tr>
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <Skeleton className="h-4 w-full" />
        </td>
      ))}
    </tr>
  );
}

export function TableBodySkeleton({
  rows = 5,
  columns = 5,
}: {
  rows?: number;
  columns?: number;
}) {
  return (
    <tbody className="divide-y divide-neutral-200">
      {Array.from({ length: rows }).map((_, i) => (
        <TableRowSkeleton key={i} columns={columns} />
      ))}
    </tbody>
  );
}

export function TableSkeleton({
  rows = 5,
  columns = 5,
  headers,
}: {
  rows?: number;
  columns?: number;
  headers?: string[];
}) {
  const headerCount = headers?.length || columns;

  return (
    <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
      <table className="min-w-full divide-y divide-neutral-200">
        <thead className="bg-neutral-50">
          <tr>
            {Array.from({ length: headerCount }).map((_, i) => (
              <th key={i} className="px-4 py-3 text-left">
                {headers ? (
                  <span className="text-xs font-medium text-neutral-500 uppercase">
                    {headers[i]}
                  </span>
                ) : (
                  <Skeleton className="h-4 w-20" />
                )}
              </th>
            ))}
          </tr>
        </thead>
        <TableBodySkeleton rows={rows} columns={headerCount} />
      </table>
    </div>
  );
}

// ============================================================================
// Stat Card Skeleton
// ============================================================================

export function StatCardSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-6">
      <Skeleton className="h-4 w-24 mb-2" />
      <Skeleton className="h-8 w-16 mb-1" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

export function StatCardSkeletonRow({ count = 3 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ============================================================================
// Page Skeleton (full page loading)
// ============================================================================

export function PageSkeleton() {
  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
        </div>
        <ButtonSkeleton size="md" />
      </div>

      {/* Stats */}
      <StatCardSkeletonRow count={4} />

      {/* Table */}
      <TableSkeleton rows={5} columns={5} />
    </div>
  );
}

export default Skeleton;
