/**
 * Regression: legacy call-flow deep links must land in the Live Calls model.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { LegacyCallFlowTraceRedirect } from '../../pages/CallFlow/LegacyCallFlowTraceRedirect';

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

describe('regression/live-calls-consolidation', () => {
  it('redirects legacy call-flow trace links to Live Calls trace details', async () => {
    render(
      <MemoryRouter initialEntries={['/call-flow/trace/abc123']}>
        <Routes>
          <Route path="/call-flow/trace/:traceId" element={<LegacyCallFlowTraceRedirect />} />
          <Route path="/observability/live-calls/trace/:traceId" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId('location')).toHaveTextContent(
        '/observability/live-calls/trace/abc123'
      );
    });
  });
});
