import { describe, expect, expectTypeOf, it } from 'vitest';
import type { Schemas } from '@stoa/shared/api-types';
import type { Application } from '../../types';

/**
 * Regression for CAB-2159 — the UI Application alias must track the canonical
 * OpenAPI schema key after type regeneration.
 */
describe('regression/CAB-2159', () => {
  it('keeps Application aligned with the canonical generated schema', () => {
    expectTypeOf<Application>().toMatchTypeOf<Schemas['ApplicationResponse']>();
    expectTypeOf<Application['api_subscriptions']>().toEqualTypeOf<
      Schemas['ApplicationResponse']['api_subscriptions']
    >();
    expect(true).toBe(true);
  });
});
