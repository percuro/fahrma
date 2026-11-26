import type { Language } from './format';
import type { PlanName } from './types';

/** A plan's name in the interface language, else in English, else the first one given. */
export function planName(name: PlanName | undefined, lang: Language): string {
  if (name === undefined) return '';
  if (typeof name === 'string') return name;
  return name[lang] ?? name.en ?? Object.values(name)[0] ?? '';
}
