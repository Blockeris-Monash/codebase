// Service worker — present so Chrome and Android will offer "Install", and so
// the page still opens with no network. iOS needs none of this, but Chrome's
// installability criteria require a registered worker with a fetch handler.
//
// Strategy is deliberately NETWORK FIRST, not cache first. The obvious PWA
// pattern would serve the cached shell instantly, but results.js is a 1 MB
// build artefact that changes on every deploy — and a phone that installed the
// app once and then showed yesterday's verdicts through judging is a far worse
// failure than a page that loads a little slower. Network wins whenever it can,
// the cache is only a fallback for offline.
//
// Bump CACHE_VERSION on any deploy that changes the shell.
const CACHE_VERSION = 'ship-happens-v7';
const SHELL = ['./', './index.html', './config.js', './results.js', './manifest.json'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => Promise.all(
        // Individually, so one missing file cannot fail the whole install.
        SHELL.map((url) => cache.add(url).catch((err) => console.warn('sw: skip', url, err)))
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// A hung network must not hang the page: after this long the cache answers instead.
const NETWORK_TIMEOUT_MS = 5000;

// A timeout, not an AbortSignal: fetch(request, {signal}) throws for a navigation request.
function withinTimeout(promise) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('sw: no answer in time')), NETWORK_TIMEOUT_MS);
    promise.then(resolve, reject).finally(() => clearTimeout(timer));
  });
}

// Only a whole, same-origin success is worth keeping: a cached 404 or 500 would be
// served offline as if it were the page (#147 B2).
function isCacheable(response) {
  return response.ok && response.type === 'basic';
}

// The same request from the cache; the shell only for a page navigation, never for a
// script or a stylesheet, which the browser would try to run as HTML.
function fromCache(request) {
  return caches.match(request)
    .then((hit) => hit || (request.mode === 'navigate' ? caches.match('./index.html') : undefined))
    .then((hit) => hit || Response.error());
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  // Never touch anything but our own GETs: the mailbox and reply calls are
  // cross-origin requests to the backend and must always go straight to the network.
  if (request.method !== 'GET' || new URL(request.url).origin !== self.location.origin) return;

  event.respondWith(
    withinTimeout(fetch(request))
      .then((response) => {
        if (isCacheable(response)) {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy)).catch(() => {});
        }
        return response;
      })
      .catch(() => fromCache(request))
  );
});
