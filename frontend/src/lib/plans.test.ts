import { describe, expect, it } from 'vitest';
import { planName } from './plans';

describe('planName', () => {
  it('takes the interface language, then English, then any', () => {
    expect(planName('Plus', 'de')).toBe('Plus');
    expect(planName({ de: 'Gratis', en: 'Free' }, 'de')).toBe('Gratis');
    expect(planName({ de: 'Gratis', en: 'Free' }, 'en')).toBe('Free');
    expect(planName({ en: 'Free' }, 'de')).toBe('Free');
    expect(planName({ fr: 'Gratuit' }, 'de')).toBe('Gratuit');
    expect(planName(undefined, 'de')).toBe('');
  });
});
