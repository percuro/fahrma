import { activeMessages } from '../i18n';
import { describeError, isErrorDetail } from './errors';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail?: unknown;
  readonly code?: string;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.code = isErrorDetail(detail) ? detail.code : undefined;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set('X-Carshare-CSRF', '1');
  if (init?.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
    headers,
  });

  if (response.status === 401) {
    window.dispatchEvent(new Event('carshare:unauthorized'));
  }

  if (!response.ok) {
    const body = await response.text();
    let detail: unknown;
    try {
      detail = (JSON.parse(body) as { detail?: unknown }).detail;
    } catch {
      // Non-JSON answers (e.g. an HTML error page from a proxy) are never shown verbatim
    }
    throw new ApiError(typeof detail === 'string' ? detail : `HTTP ${response.status}`, response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/** Text for an error in the current interface language (translated when shown, not when thrown). */
export function errorText(error: unknown): string {
  const generic = activeMessages().generic;
  if (error instanceof ApiError) {
    if (isErrorDetail(error.detail)) return describeError(error.detail);
    if (Array.isArray(error.detail)) return generic.invalidInput;
    if (typeof error.detail === 'string') return error.detail;
    return generic.serverError(error.status);
  }
  if (error instanceof TypeError) return generic.offline;
  return generic.unknown;
}
