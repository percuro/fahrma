import { activeMessages, currentLanguage } from '../i18n';
import { createFormat, type Format } from './format';

export interface ErrorDetail {
  code: string;
  params: Record<string, unknown>;
  message: string;
}

export function isErrorDetail(value: unknown): value is ErrorDetail {
  return typeof value === 'object' && value !== null && typeof (value as ErrorDetail).code === 'string';
}

const KM_PARAMS = new Set(['km', 'start_km', 'end_km', 'from_km', 'to_km']);
const DATE_PARAMS = new Set(['date', 'previous']);
const DATE_TIME_PARAMS = new Set(['starts_at', 'ends_at', 'time']);

/** The server sends raw values; texts get them formatted (km with separators, dates in local style). */
function formatParams(params: Record<string, unknown>, format: Format): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(params).map(([key, value]) => {
      if (KM_PARAMS.has(key) && typeof value === 'number') return [key, format.km(value)];
      if (DATE_PARAMS.has(key) && typeof value === 'string') return [key, format.date(value)];
      if (DATE_TIME_PARAMS.has(key) && typeof value === 'string') return [key, format.dateTime(value)];
      return [key, value];
    }),
  );
}

/** Text for a coded server error; the English server message if the code is unknown. */
export function describeError(detail: ErrorDetail, format: Format = createFormat(currentLanguage())): string {
  const text = activeMessages().errors[detail.code];
  return text ? text(formatParams(detail.params ?? {}, format)) : detail.message;
}

/**
 * Text for a settlement warning. Snapshots of settlements made before 0.2 have no
 * params (the API returns an empty object) and a German message; those are shown as stored.
 */
export function describeWarning(
  warning: { code: string; message: string; params?: Record<string, unknown> },
  format: Format = createFormat(currentLanguage()),
): string {
  const text = activeMessages().warnings[warning.code];
  const params = warning.params ?? {};
  const needsParams = warning.code !== 'carried_expense';
  if (!text || (needsParams && Object.keys(params).length === 0)) return warning.message;
  return text(formatParams(params, format));
}
