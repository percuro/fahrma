import { createContext, useContext } from 'react';
import type { Messages } from './de';
import type { Language } from '../lib/format';
import { MESSAGES, browserLanguage } from './language';

export interface I18n {
  lang: Language;
  t: Messages;
}

export const I18nContext = createContext<I18n>({ lang: browserLanguage(), t: MESSAGES[browserLanguage()] });

export const useI18n = (): I18n => useContext(I18nContext);
export const useT = (): Messages => useContext(I18nContext).t;
