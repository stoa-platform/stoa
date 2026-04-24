import { describe, expect, it } from 'vitest';

import { extractList } from './payload';

describe('extractList (P1-8 — shape guard)', () => {
  it('returns a bare array as-is', () => {
    const data = [{ id: '1' }, { id: '2' }];
    expect(extractList<{ id: string }>(data, 'apis')).toEqual(data);
  });

  it('unwraps data.items from a paginated envelope', () => {
    const data = { items: [{ id: '1' }], total: 1, page: 1 };
    expect(extractList<{ id: string }>(data, 'apis')).toEqual([{ id: '1' }]);
  });

  it('handles empty array', () => {
    expect(extractList([], 'apis')).toEqual([]);
  });

  it('handles empty items', () => {
    expect(extractList({ items: [], total: 0 }, 'apis')).toEqual([]);
  });

  it('throws with label on an unexpected object shape (no items, not array)', () => {
    expect(() => extractList({ total: 5, page: 1 }, 'apis')).toThrowError(
      /Unexpected apis response shape/
    );
  });

  it('throws on null', () => {
    expect(() => extractList(null, 'apis')).toThrowError(/Unexpected apis/);
  });

  it('throws when items is not an array', () => {
    expect(() => extractList({ items: 'oops' }, 'apis')).toThrowError(/Unexpected apis/);
  });
});
