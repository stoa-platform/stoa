// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
interface SkeletonProps {
  className?: string;
}

/**
 * Base skeleton component for loading states.
 * Shows an animated pulse placeholder while content loads.
 *
 * Usage:
 * ```tsx
 * <Skeleton className="h-4 w-32" />
 * <Skeleton className="h-12 w-12 rounded-full" />
 * ```
 */
export function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse rounded bg-gray-200 ${className}`}
      aria-hidden="true"
    />
  );
}

/**
 * Text skeleton with multiple lines.
 */
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

/**
 * Avatar skeleton (circular).
 */
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

/**
 * Button skeleton.
 */
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
