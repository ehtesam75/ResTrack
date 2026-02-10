// Service Worker for ResTrack PWA
const CACHE_NAME = 'restrack-v1.3.0';
const STATIC_CACHE_NAME = 'restrack-static-v1.3.0';

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
      .then(cache => {
        console.log('Caching static assets...');
        return cache.addAll(STATIC_ASSETS);
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

// Fetch event - only handle same-origin static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // NEVER intercept cross-origin requests (CDN, Cloudinary, external APIs, PDF.js worker, etc.)
  // Let the browser handle them natively to avoid CORS issues (e.g. Chrome blocking PDF.js)
  if (url.origin !== self.location.origin) {
    return;
  }

  // Only cache same-origin static assets (/static/*, CSS, JS, images, fonts)
  if (url.pathname.startsWith('/static/') ||
      event.request.destination === 'style' ||
      event.request.destination === 'script' ||
      event.request.destination === 'image' ||
      event.request.destination === 'font') {

    event.respondWith(
      caches.match(event.request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(event.request)
            .then(response => {
              // Cache successful same-origin static asset responses
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

  // For all other same-origin requests (navigation, API calls, etc.) - network only
  // No caching of authenticated pages or dynamic content
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