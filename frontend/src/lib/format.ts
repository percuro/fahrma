/**
 * Formatting for display (depends on language and the group's currency) and
 * tolerant parsing of user input (comma or point, with or without thousands separators).
 */

export type Language = 'de' | 'en';

/** Intl locale for a language: the browser's regional variant if it matches (de-AT, en-US …). */
export function intlLocale(lang: Language): string {
  const browser = typeof navigator !== 'undefined' ? navigator.languages ?? [navigator.language] : [];
  return browser.find((l) => l?.toLowerCase().startsWith(lang)) ?? (lang === 'de' ? 'de-DE' : 'en-GB');
}

export interface Format {
  lang: Language;
  currency: string;
  money(cents: number | null | undefined): string;
  /** Money with sign for balances: +12,50 € / −3,00 € */
  signedMoney(cents: number): string;
  km(km: number | null | undefined): string;
  /** Cost per km, e.g. "0,300 €/km" */
  rate(centsPerKm: number | null | undefined): string;
  date(iso: string | null | undefined): string;
  /** Fuel quantity in thousandths of the unit: 42500 + "l" → "42,5 l" */
  quantity(milli: number | null | undefined, unit: string): string;
  /** Price per litre or kWh, e.g. "1,659 €/l" */
  unitPrice(cents: number, milli: number, unit: string): string;
  /** Cents as text for an input field: 1250 → "12,50" */
  moneyInput(cents: number | null | undefined): string;
  quantityInput(milli: number | null | undefined): string;
  currencySymbol: string;
}

const DASH = '–';

export function createFormat(lang: Language, currency = 'EUR'): Format {
  const locale = intlLocale(lang);
  // Plain numbers with a fixed locale per language: de-AT would group with spaces, which reads badly on phones
  const numberLocale = lang === 'de' ? 'de-DE' : 'en-GB';
  const money = new Intl.NumberFormat(locale, { style: 'currency', currency });
  const rate = new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  });
  const integer = new Intl.NumberFormat(numberLocale, { maximumFractionDigits: 0 });
  const decimal = new Intl.NumberFormat(numberLocale, { maximumFractionDigits: 2 });
  const dates = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
  const symbol = money.formatToParts(0).find((p) => p.type === 'currency')?.value ?? currency;
  const decimalSeparator = lang === 'de' ? ',' : '.';

  return {
    lang,
    currency,
    currencySymbol: symbol,
    money: (cents) => (cents === null || cents === undefined ? DASH : money.format(cents / 100)),
    signedMoney: (cents) => `${cents > 0 ? '+' : ''}${money.format(cents / 100)}`,
    km: (km) => (km === null || km === undefined ? DASH : `${integer.format(Math.round(km))} km`),
    rate: (centsPerKm) => (centsPerKm === null || centsPerKm === undefined ? DASH : `${rate.format(centsPerKm / 100)}/km`),
    date: (iso) => {
      if (!iso) return DASH;
      const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
      return dates.format(new Date(Date.UTC(y, m - 1, d)));
    },
    quantity: (milli, unit) => (milli === null || milli === undefined ? DASH : `${decimal.format(milli / 1000)} ${unit}`),
    unitPrice: (cents, milli, unit) => `${rate.format(cents / 100 / (milli / 1000))}/${unit}`,
    moneyInput: (cents) =>
      cents === null || cents === undefined ? '' : (cents / 100).toFixed(2).replace('.', decimalSeparator),
    quantityInput: (milli) =>
      milli === null || milli === undefined ? '' : String(milli / 1000).replace('.', decimalSeparator),
  };
}

/**
 * Normalises a decimal number typed in any common way to "1234.56".
 * The last separator is the decimal mark if it is followed by at most `maxDecimals` digits
 * ("12,50", "12.5", "1.234,56", "1,234.56"); otherwise separators group thousands ("1.234").
 */
function normalizeDecimal(text: string, maxDecimals: number): string | null {
  const cleaned = text.trim().replace(/[\s\u00a0\u202f'\u2019€$£]|EUR|CHF|kWh|l$/gi, '');
  if (!cleaned) return null;
  if (!/^[\d.,]+$/.test(cleaned)) return null;
  const separators = cleaned.match(/[.,]/g) ?? [];
  if (separators.length === 0) return cleaned;
  const last = Math.max(cleaned.lastIndexOf(','), cleaned.lastIndexOf('.'));
  const intDigits = cleaned.slice(0, last).replace(/[.,]/g, '') || '0';
  const decimals = cleaned.slice(last + 1);
  const mixed = new Set(separators).size > 1;
  const onlyGrouping =
    // "1.234.567": the same separator several times
    (!mixed && separators.length > 1) ||
    // "1.234" for money: three digits after a single separator group thousands
    (!mixed && decimals.length === 3 && maxDecimals < 3);
  if (onlyGrouping) return decimals.length === 3 ? `${intDigits}${decimals}` : null;
  if (decimals.length === 0) return intDigits;
  if (decimals.length > maxDecimals) return null;
  return `${intDigits}.${decimals}`;
}

/** "12,50" / "12.5" / "1.234,56" / "1,234.56" / "12" → cents; empty or invalid → null */
export function parseMoney(text: string): number | null {
  const normalized = normalizeDecimal(text, 2);
  if (normalized === null) return null;
  const value = Math.round(Number(normalized) * 100);
  return Number.isFinite(value) ? value : null;
}

/** Litres or kWh with up to three decimals → thousandths ("42,5" → 42500) */
export function parseQuantity(text: string): number | null {
  const normalized = normalizeDecimal(text, 3);
  if (normalized === null) return null;
  const value = Math.round(Number(normalized) * 1000);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** Whole kilometres; thousands separators of any kind are ignored ("12.345", "12,345", "12 345"). */
export function parseKm(text: string): number | null {
  const cleaned = text.trim().replace(/[\s\u00a0\u202f.,'\u2019]|km$/gi, '');
  if (!cleaned || !/^\d+$/.test(cleaned)) return null;
  return Number(cleaned);
}
