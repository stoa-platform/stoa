import { Navigate, useParams } from 'react-router-dom';

export function LegacyCallFlowTraceRedirect() {
  const { traceId } = useParams<{ traceId?: string }>();

  if (!traceId) {
    return <Navigate to="/observability/live-calls" replace />;
  }

  return <Navigate to={`/observability/live-calls/trace/${encodeURIComponent(traceId)}`} replace />;
}

export default LegacyCallFlowTraceRedirect;
