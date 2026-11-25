import { useEffect, useMemo, type ReactNode } from 'react';
import type { Language } from '../lib/format';
import { I18nContext } from './context';
import { MESSAGES, setActiveLanguage } from './language';

export function I18nProvider({ language, children }: { language: Language; children: ReactNode }) {
  const value = useMemo(() => ({ lang: language, t: MESSAGES[language] }), [language]);
  // Idempotent: keeps error texts produced outside React in the language being rendered
  setActiveLanguage(language);
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
