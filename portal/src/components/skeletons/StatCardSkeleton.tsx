import { Skeleton } from '../common/Skeleton';

/**
 * Single stat card skeleton.
 */
export function StatCardSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <Skeleton className="h-4 w-24 mb-2" />
      <Skeleton className="h-8 w-16 mb-1" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

/**
 * Row of stat card skeletons.
 */
export function StatCardSkeletonRow({ count = 3 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {Array.from({ length: count }).map((_, i) => (
        <StatCardSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * Stat card with icon skeleton.
 */
export function StatCardWithIconSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-10 w-10 rounded-lg" />
      </div>
      <Skeleton className="h-8 w-20 mb-1" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

/**
 * Usage stat skeleton (for usage page).
 */
export function UsageStatSkeleton() {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-6">
      <div className="flex items-center gap-3 mb-4">
        <Skeleton className="h-12 w-12 rounded-lg" />
        <div>
          <Skeleton className="h-5 w-32 mb-1" />
          <Skeleton className="h-4 w-48" />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div>
          <Skeleton className="h-3 w-16 mb-1" />
          <Skeleton className="h-6 w-12" />
        </div>
        <div>
          <Skeleton className="h-3 w-16 mb-1" />
          <Skeleton className="h-6 w-12" />
        </div>
        <div>
          <Skeleton className="h-3 w-16 mb-1" />
          <Skeleton className="h-6 w-12" />
        </div>
      </div>
    </div>
  );
}
