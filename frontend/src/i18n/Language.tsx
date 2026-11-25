import type { ReactNode } from 'react';
import { useMe } from '../hooks/useMe';
import { resolveLanguage } from './language';
import { I18nProvider } from './I18nProvider';

/** Interface language: the profile setting once logged in, otherwise the browser's. */
export function Language({ children }: { children: ReactNode }) {
  const me = useMe();
  return <I18nProvider language={resolveLanguage(me.data?.locale)}>{children}</I18nProvider>;
}
