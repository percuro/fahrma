import { describe, expect, it } from 'vitest';
import { niceTicks } from './ticks';

describe('niceTicks', () => {
  it('uses round steps up to at least the maximum', () => {
    expect(niceTicks(0)).toEqual([0]);
    expect(niceTicks(830)).toEqual([0, 500, 1000]);
    expect(niceTicks(1000)).toEqual([0, 500, 1000]);
    expect(niceTicks(1234)).toEqual([0, 500, 1000, 1500]);
    expect(niceTicks(7)).toEqual([0, 2, 4, 6, 8]);
  });
});
