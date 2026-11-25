import { describe, expect, it } from 'vitest';
import { keyBytes } from './push';

describe('keyBytes', () => {
  it('reads base64url without padding', () => {
    expect(Array.from(keyBytes('AQID'))).toEqual([1, 2, 3]);
    expect(Array.from(keyBytes('-_8'))).toEqual([251, 255]);
    expect(keyBytes('B'.repeat(87)).length).toBe(65); // a P-256 public key
  });
});
