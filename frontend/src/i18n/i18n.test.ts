import { describe, expect, it } from 'vitest';
import { de } from './de';
import { en } from './en';

/** Keys at every level, so a missing nested text is reported even where types are loose (Record<string, …>). */
function keys(value: unknown, prefix = ''): string[] {
  if (typeof value !== 'object' || value === null) return [prefix];
  return Object.entries(value).flatMap(([key, child]) => keys(child, prefix ? `${prefix}.${key}` : key));
}

describe('translations', () => {
  it('English has exactly the German keys', () => {
    expect(keys(en).sort()).toEqual(keys(de).sort());
  });

  it('covers every expense category and allocation in both languages', () => {
    for (const messages of [de, en]) {
      expect(Object.keys(messages.expense.categories)).toHaveLength(11);
      expect(Object.keys(messages.expense.allocations)).toEqual(['by_km', 'equal', 'single', 'trip']);
    }
  });
});
