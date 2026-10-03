// Service Worker for ResTrack PWA
const CACHE_NAME = 'restrack-v2.1.0';
const STATIC_CACHE_NAME = 'restrack-static-v2.1.0';

// ---------------------------------------------------------------------------
// Local development mode
// ---------------------------------------------------------------------------
// In production, /static/ URLs are content-hashed by WhiteNoise's
// ManifestStaticFilesStorage (e.g. custom.a1b2c3.css), so a cache-first
// strategy is safe: changing a file changes its URL, which misses the cache.
//
// During local development there are no hashes — it is always
// /static/css/custom.css — so cache-first pins the very first copy the browser
// ever saw and no amount of refreshing will replace it. That is what makes
// edits appear to "not show up" on localhost.
//
// So on localhost we disable caching entirely and let the browser talk to the
// dev server directly. Production behaviour is completely unchanged.
const DEV_HOSTNAMES = ['localhost', '127.0.0.1', '[::1]', '::1', '0.0.0.0'];
const IS_DEV = DEV_HOSTNAMES.includes(self.location.hostname);


// Static assets to cache - same-origin ONLY, no CDN/external URLs
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/css/custom.css',
  // Cache favicon for instant loading
  '/static/icons/favicon.ico',
  '/static/icons/ResTrack-16x16.png',
  '/static/icons/ResTrack-32x32.png',
  // Cache icons for faster loading but allow updates
  '/static/icons/ResTrack-72x72.png',
  '/static/icons/ResTrack-96x96.png',
  '/static/icons/ResTrack-128x128.png',
  '/static/icons/ResTrack-144x144.png',
  '/static/icons/ResTrack-192x192.png',
  '/static/icons/ResTrack-512x512.png',
  '/static/icons/ResTrack-maskable-192x192.png',
  '/static/icons/ResTrack-maskable-512x512.png',
  '/static/icons/ResTrack-monochrome-192x192.png',
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('Service Worker installing.');

  if (IS_DEV) {
    // Don't pre-cache anything locally, and activate immediately so a stale
    // worker from an earlier session is replaced on the very next load.
    console.log('[dev] Skipping static asset pre-cache.');
    event.waitUntil(self.skipWaiting());
    return;
  }

  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then(async cache => {
        console.log('Caching static assets...');

        const results = await Promise.allSettled(
          STATIC_ASSETS.map(asset => cache.add(asset))
        );
        const failed = results.filter(r => r.status === 'rejected');
        if (failed.length) {
          console.warn(`Failed to cache ${failed.length} asset(s):`, failed.map(r => r.reason));
        }
      })
      .then(() => {
        console.log('Service Worker installed.');
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches and take control
self.addEventListener('activate', event => {
  console.log('Service Worker activating.');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          // Locally, drop every cache — including the current one, which may
          // hold stale entries written by a previous (pre-fix) worker.
          if (IS_DEV) {
            console.log('[dev] Deleting cache:', cacheName);
            return caches.delete(cacheName);
          }
          // Delete all old caches to ensure fresh icons and manifest
          if (cacheName !== STATIC_CACHE_NAME) {

            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('Service Worker activated and old caches cleaned up.');
      // Force refresh all clients to get updated icons
      return self.clients.matchAll().then(clients => {
        clients.forEach(client => client.navigate(client.url));
      }).then(() => self.clients.claim());
    })
  );
});

// Fetch event - only handle same-origin /static/ assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Cross-origin requests (CDN, Cloudinary, PDF.js worker, etc.) — don't intercept at all
  // Let the browser handle them natively with proper CORS headers
  if (url.origin !== self.location.origin) {
    return;
  }

  // Locally, never serve anything from the cache. Going straight to the
  // network means an edited CSS/JS/icon shows up on a plain refresh.
  if (IS_DEV) {
    return;
  }

  // Only cache same-origin assets under /static/ — nothing else
  // Avoids catching PDF.js blob workers, inline scripts, or dynamic API routes
  if (url.pathname.startsWith('/static/')) {

    event.respondWith(
      caches.match(event.request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(event.request)
            .then(response => {
              if (response.status === 200) {
                const responseClone = response.clone();
                caches.open(STATIC_CACHE_NAME)
                  .then(cache => cache.put(event.request, responseClone));
              }
              return response;
            })
            .catch(() => {
              console.log('Failed to fetch static asset:', event.request.url);
              return new Response('', { status: 404 });
            });
        })
    );
    return;
  }

  // All other same-origin requests (navigation, API calls, etc.) — network only
  event.respondWith(fetch(event.request));
});

// Message event - handle updates from the main thread
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  if (event.data && event.data.type === 'CLEAR_ICON_CACHE') {
    // Clear all caches and force refresh
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => caches.delete(cacheName))
      );
    }).then(() => {
      console.log('Icon cache cleared, refreshing clients...');
      return self.clients.matchAll();
    }).then(clients => {
      clients.forEach(client => client.navigate(client.url));
    });
  }
});

// ---------------------------------------------------------------------------
// Push Notification handling
// ---------------------------------------------------------------------------

// Receive push messages from the server
self.addEventListener('push', event => {
  console.log('Push notification received.');

  let data = { title: 'ResTrack', body: 'You have a new notification.', url: '/' };
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const origin = self.location.origin;
  const defaultIcon = origin + '/static/icons/ResTrack-192x192.png';
  const defaultBadge = origin + '/static/icons/ResTrack-monochrome-192x192.png';
  const icon = data.icon
    ? (data.icon.startsWith('http') ? data.icon : origin + data.icon)
    : defaultIcon;
  const badge = data.badge
    ? (data.badge.startsWith('http') ? data.badge : origin + data.badge)
    : defaultBadge;
  const options = {
    body: data.body || '',
    icon: icon,
    badge: badge,
    tag: data.tag || 'restrack-notification',
    renotify: true,
    requireInteraction: true,
    silent: false,
    data: { url: data.url || '/' },
    vibrate: [300, 100, 300, 100, 300],
    actions: [
      { action: 'open', title: 'Open' },
      { action: 'dismiss', title: 'Dismiss' },
    ],
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'ResTrack', options)
  );
});

// Handle notification click — navigate to the target URL
self.addEventListener('notificationclick', event => {
  console.log('Notification clicked:', event.notification.tag);
  event.notification.close();

  if (event.action === 'dismiss') {
    return;
  }

  const targetUrl = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(windowClients => {
      // If a ResTrack tab is already open, focus it and navigate
      for (const client of windowClients) {
        if (client.url.includes(self.location.origin)) {
          client.focus();
          return client.navigate(targetUrl);
        }
      }
      // Otherwise open a new window
      return clients.openWindow(targetUrl);
    })
  );
});