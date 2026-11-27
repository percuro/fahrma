import { describe, expect, it } from 'vitest';
import { parseHashParams } from './oidc';

describe('parseHashParams', () => {
  it('reads what the OIDC callback puts in the fragment', () => {
    expect(parseHashParams('#error=oidc_no_account')).toEqual({ error: 'oidc_no_account' });
    expect(parseHashParams('reauth=ok')).toEqual({ reauth: 'ok' });
    expect(parseHashParams('')).toEqual({});
  });
});
