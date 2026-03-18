interface RouteLatency {
  route: string;
  p95Ms: number;
  calls: number;
}

interface TopRoutesProps {
  routes: RouteLatency[];
}

function latencyColor(ms: number): string {
  if (ms < 50) return 'bg-green-500';
  if (ms < 200) return 'bg-yellow-500';
  if (ms < 500) return 'bg-orange-500';
  return 'bg-red-500';
}

function latencyTextColor(ms: number): string {
  if (ms < 50) return 'text-green-600 dark:text-green-400';
  if (ms < 200) return 'text-yellow-600 dark:text-yellow-400';
  if (ms < 500) return 'text-orange-600 dark:text-orange-400';
  return 'text-red-600 dark:text-red-400';
}

export function TopRoutes({ routes }: TopRoutesProps) {
  if (routes.length === 0) {
    return (
      <div className="h-[250px] flex items-center justify-center text-sm text-neutral-400 dark:text-neutral-500">
        No route data available
      </div>
    );
  }

  const maxP95 = Math.max(...routes.map((r) => r.p95Ms), 1);

  return (
    <div className="space-y-3">
      {routes.slice(0, 8).map((r) => (
        <div key={r.route}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-mono text-neutral-700 dark:text-neutral-300 truncate max-w-[60%]">
              {r.route}
            </span>
            <div className="flex items-center gap-3">
              <span className="text-xs text-neutral-400">{r.calls} req</span>
              <span className={`text-sm font-semibold tabular-nums ${latencyTextColor(r.p95Ms)}`}>
                {r.p95Ms < 1 ? '<1' : Math.round(r.p95Ms)}ms
              </span>
            </div>
          </div>
          <div className="w-full bg-neutral-100 dark:bg-neutral-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all ${latencyColor(r.p95Ms)}`}
              style={{ width: `${Math.min((r.p95Ms / maxP95) * 100, 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
