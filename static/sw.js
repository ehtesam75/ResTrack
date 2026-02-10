// Service Worker for ResTrack PWA
const CACHE_NAME = 'restrack-v1.4.1';
const STATIC_CACHE_NAME = 'restrack-static-v1.4.1';

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
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('Service Worker installing.');
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