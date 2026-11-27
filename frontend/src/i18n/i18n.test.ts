/// <reference types="node" />
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { de } from './de';
import { en } from './en';

const BACKEND = join(import.meta.dirname, '..', '..', '..', 'backend', 'app');

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return name.endsWith('.py') ? [path] : [];
  });
}

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

  it('covers every error code of the login through a provider', () => {
    // Callback errors travel in the URL fragment (/login#error=<code>), so they need a text too
    const codes = new Set<string>();
    for (const file of files(BACKEND).filter((path) => /oidc|account|auth|setup|invitation/.test(path))) {
      const source = readFileSync(file, 'utf8');
      for (const match of source.matchAll(/AppError\(\s*(?:status\.\w+|\d+),\s*"([a-z_]+)"/g)) codes.add(match[1]);
      for (const match of source.matchAll(/(?:OidcFlowError|OidcError)\(\s*"([a-z_]+)"/g)) codes.add(match[1]);
    }
    expect(codes.size).toBeGreaterThan(20);
    for (const messages of [de, en]) {
      expect([...codes].filter((code) => !messages.errors[code])).toEqual([]);
    }
  });
});
