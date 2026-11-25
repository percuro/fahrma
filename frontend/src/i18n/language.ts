import { de, type Messages } from './de';
import { en } from './en';
import type { Language } from '../lib/format';

export const MESSAGES: Record<Language, Messages> = { de, en };

/** First supported browser language; English for everything that is not German. */
export function browserLanguage(): Language {
  const preferred = typeof navigator !== 'undefined' ? navigator.languages ?? [navigator.language] : [];
  for (const tag of preferred) {
    const base = tag?.slice(0, 2).toLowerCase();
    if (base === 'de' || base === 'en') return base;
  }
  return 'en';
}

export function resolveLanguage(setting: string | null | undefined): Language {
  return setting === 'de' || setting === 'en' ? setting : browserLanguage();
}

// The language of the rendered interface, for code outside React (error texts in api.ts)
let activeLanguage: Language = browserLanguage();
export const currentLanguage = () => activeLanguage;
export const activeMessages = () => MESSAGES[activeLanguage];
export function setActiveLanguage(language: Language) {
  activeLanguage = language;
}
