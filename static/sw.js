// Service Worker for ResTrack PWA
// /sw.js receives the collected static manifest's version from Django. A new
// build therefore installs a new worker and retires this app's previous cache.
const STATIC_CACHE_NAME = `restrack-static-v3-${self.RESTRACK_ASSET_VERSION || 'dev'}`;
const OWNED_CACHE_PREFIX = 'restrack-';
const HASHED_ASSET = /\.[a-f0-9]{12}\.[^/]+$/i;

// ---------------------------------------------------------------------------
// Local development mode
// ---------------------------------------------------------------------------
// Local development bypasses the worker cache entirely. Production still has
// some mutable URLs (manifest icons, for example); only content-hashed URLs
// can safely use cache-first, regardless of the hostname.
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

function cacheable(response) {
  return response.status === 200 &&
    !/\bno-store\b/i.test(response.headers.get('Cache-Control') || '');
}

// Install event - best-effort offline copies of mutable assets. Revalidate
// against the server so installation cannot seed a new cache with old HTTP data.
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    if (!IS_DEV) {
      try {
        const cache = await caches.open(STATIC_CACHE_NAME);
        await Promise.allSettled(STATIC_ASSETS.map(async asset => {
          const response = await fetch(asset, { cache: 'no-cache' });
          if (cacheable(response)) await cache.put(asset, response);
        }));
      } catch (error) {
        // Storage may be unavailable or full; that must not block updates.
        console.warn('Static asset precache unavailable:', error);
      }
    }
    await self.skipWaiting();
  })());
});

// Activate event - clean up old caches and take control
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(name => name.startsWith(OWNED_CACHE_PREFIX) &&
            (IS_DEV || name !== STATIC_CACHE_NAME))
          .map(name => caches.delete(name))
      );
    }).catch(error => {
      // Storage can be disabled or temporarily unavailable. Still replace the
      // previous worker: asset lookups only use this build's cache namespace.
      console.warn('Could not clean up old static asset caches:', error);
    // Claim without reloading tabs: deployments must not interrupt exams or
    // discard unsaved forms. New navigations receive the latest HTML/assets.
    }).then(() => self.clients.claim())
  );
});

async function staticResponse(request, immutable) {
  // Cache Storage is an optimization; a storage failure must not break assets.
  let cache;
  try {
    cache = await caches.open(STATIC_CACHE_NAME);
    if (immutable) {
      const cachedResponse = await cache.match(request);
      if (cachedResponse) return cachedResponse;
    }
  } catch (error) {
    console.warn('Static asset cache unavailable:', error);
  }

  let response;
  try {
    response = await fetch(request, immutable ? undefined : { cache: 'no-cache' });
  } catch (error) {
    // Mutable URLs are only served from Cache Storage when the network is
    // unavailable. Online responses, including 404s, are never hidden by it.
    if (cache && !immutable) {
      const cachedResponse = await cache.match(request);
      if (cachedResponse) return cachedResponse;
    }
    throw error;
  }

  if (cache) {
    try {
      if (cacheable(response)) {
        await cache.put(request, response.clone());
      } else {
        await cache.delete(request);
      }
    } catch (error) {
      console.warn('Could not update static asset cache:', error);
    }
  }
  return response;
}

// Fetch event - only handle same-origin /static/ assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Let navigation, API, POST, CDN and local-development requests pass through
  // untouched. Only same-origin GET requests for static assets belong here.
  if (IS_DEV || event.request.method !== 'GET' ||
      url.origin !== self.location.origin || !url.pathname.startsWith('/static/')) {
    return;
  }
  const response = staticResponse(event.request, HASHED_ASSET.test(url.pathname));
  event.respondWith(response);
  // Keep the worker alive through cache writes, including on slow devices.
  event.waitUntil(response.then(() => undefined, () => undefined));
});

// Message event - handle updates from the main thread
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    event.waitUntil(self.skipWaiting());
  }
  if (event.data && event.data.type === 'CLEAR_ICON_CACHE') {
    // Compatibility with existing clients, without deleting other apps' data
    // or forcibly navigating a page that may contain unsaved work.
    event.waitUntil(caches.keys().then(cacheNames => Promise.all(
      cacheNames.filter(name => name.startsWith(OWNED_CACHE_PREFIX))
        .map(name => caches.delete(name))
    )));
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
