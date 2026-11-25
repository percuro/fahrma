/**
 * Web Push on this device: whether it can, and subscribing through the service worker.
 * The server keeps one subscription per login; logging out removes it there, and
 * unsubscribeLocally() removes it from the browser as well.
 */
import { apiFetch } from './api';
import type { NotificationsState } from './types';

export type PushSupport =
  | 'supported'
  // iPhone/iPad: only an app added to the home screen may receive notifications
  | 'install-first'
  | 'unsupported';

export function isIos(): boolean {
  if (typeof navigator === 'undefined') return false;
  // iPadOS reports itself as a Mac with touch
  return /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export function isStandalone(): boolean {
  return (
    window.matchMedia?.('(display-mode: standalone)').matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function pushSupport(): PushSupport {
  const capable = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (capable) return 'supported';
  return isIos() && !isStandalone() ? 'install-first' : 'unsupported';
}

/** The applicationServerKey as bytes (from the base64url text in /v1/meta). */
export function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const base64 = (base64url + '='.repeat((4 - (base64url.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

/** The service worker, if it is (or becomes) active within a few seconds; not in development. */
async function registration(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) return null;
  const timeout = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 5000));
  return Promise.race([navigator.serviceWorker.ready, timeout]);
}

export async function browserSubscription(): Promise<PushSubscription | null> {
  const reg = await registration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export class PushError extends Error {
  readonly reason: 'denied' | 'no-worker';

  constructor(reason: 'denied' | 'no-worker') {
    super(reason);
    this.reason = reason;
  }
}

/** Ask for permission, subscribe the browser and tell the server. */
export async function subscribe(vapidKey: string, locale: string): Promise<NotificationsState> {
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new PushError('denied');
  const reg = await registration();
  if (!reg) throw new PushError('no-worker');
  let subscription = await reg.pushManager.getSubscription();
  const key = keyBytes(vapidKey);
  const sameKey = (s: PushSubscription) => {
    const current = s.options.applicationServerKey;
    return !!current && new Uint8Array(current).every((byte, i) => byte === key[i]);
  };
  // A subscription made for another key (another instance or a new key) cannot be reused
  if (subscription && !sameKey(subscription)) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  return apiFetch<NotificationsState>('/v1/account/push-subscription', {
    method: 'POST',
    body: JSON.stringify({ ...subscription.toJSON(), locale }),
  });
}

/** Stop notifications on this device, on the server and in the browser. */
export async function unsubscribe(): Promise<void> {
  const subscription = await browserSubscription();
  if (!subscription) return;
  await apiFetch<void>('/v1/account/push-subscription', {
    method: 'DELETE',
    body: JSON.stringify({ endpoint: subscription.endpoint }),
  });
  await subscription.unsubscribe();
}

/** After logging out: the server dropped the subscription with the login; drop it here too. */
export async function unsubscribeLocally(): Promise<void> {
  try {
    const subscription = await browserSubscription();
    await subscription?.unsubscribe();
  } catch {
    // Nothing to clean up
  }
}
