/*
 * Web Push in the service worker (loaded by the generated sw.js through importScripts,
 * see vite.config.ts). A message is JSON from the server: title, body, url (a path of
 * this app) and tag (messages with the same tag replace each other).
 */
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || 'fahrma', {
      body: data.body || '',
      tag: data.tag || undefined,
      icon: '/icon-192.png',
      data: { url: typeof data.url === 'string' && data.url.startsWith('/') ? data.url : '/' },
    }),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || '/', self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (windows) => {
      const open = windows.find((client) => new URL(client.url).origin === self.location.origin);
      if (open) {
        const focused = await open.focus();
        return 'navigate' in focused ? focused.navigate(url) : focused;
      }
      return self.clients.openWindow(url);
    }),
  );
});
