import { Skeleton } from '../common/Skeleton';

/**
 * Skeleton for MCP Server card (used in servers listing).
 */
export function ServerCardSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      {/* Icon */}
      <Skeleton className="h-12 w-12 rounded-lg mb-4" />

      {/* Title */}
      <Skeleton className="h-5 w-3/4 mb-2" />

      {/* Description */}
      <Skeleton className="h-4 w-full mb-1" />
      <Skeleton className="h-4 w-2/3 mb-4" />

      {/* Tags */}
      <div className="flex gap-2">
        <Skeleton className="h-6 w-16 rounded-full" />
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>
    </div>
  );
}

/**
 * Grid of server card skeletons.
 */
export function ServerCardSkeletonGrid({ count = 6, columns = 3 }: { count?: number; columns?: 2 | 3 }) {
  const gridClass = columns === 2
    ? 'grid grid-cols-1 md:grid-cols-2 gap-6'
    : 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6';

  return (
    <div className={gridClass}>
      {Array.from({ length: count }).map((_, i) => (
        <ServerCardSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * Skeleton for server detail page.
 */
export function ServerDetailSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Skeleton className="h-16 w-16 rounded-xl" />
        <div className="flex-1">
          <Skeleton className="h-8 w-64 mb-2" />
          <Skeleton className="h-4 w-96 mb-2" />
          <div className="flex gap-2">
            <Skeleton className="h-6 w-20 rounded-full" />
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
        </div>
        <Skeleton className="h-10 w-32 rounded-lg" />
      </div>

      {/* Tools section */}
      <div>
        <Skeleton className="h-6 w-32 mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-3">
                <Skeleton className="h-8 w-8 rounded" />
                <div className="flex-1">
                  <Skeleton className="h-5 w-48 mb-1" />
                  <Skeleton className="h-4 w-full" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
