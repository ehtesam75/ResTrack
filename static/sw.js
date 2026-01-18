// Service Worker for ResTrack PWA
const CACHE_NAME = 'restrack-v1.0.0';
const STATIC_CACHE_NAME = 'restrack-static-v1.0.0';

// Static assets to cache - ONLY static files, no authenticated pages
const STATIC_ASSETS = [
  '/static/manifest.json',
  '/static/css/custom.css',
  'https://cdn.tailwindcss.com',
  'https://cdn.jsdelivr.net/npm/chart.js'
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
          // Only keep current static cache, remove all others
          if (cacheName !== STATIC_CACHE_NAME) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('Service Worker activated and old caches cleaned up.');
      return self.clients.claim();
    })
  );
});

// Fetch event - serve from cache when possible
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Handle static assets (CSS, JS, images, fonts)
  if (event.request.destination === 'style' ||
      event.request.destination === 'script' ||
      event.request.destination === 'image' ||
      event.request.destination === 'font' ||
      url.pathname.startsWith('/static/') ||
      url.hostname === 'cdn.tailwindcss.com' ||
      url.hostname === 'cdn.jsdelivr.net') {

    event.respondWith(
      caches.match(event.request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          return fetch(event.request)
            .then(response => {
              // Cache successful static asset responses
              if (response.status === 200) {
                const responseClone = response.clone();
                caches.open(STATIC_CACHE_NAME)
                  .then(cache => cache.put(event.request, responseClone));
              }
              return response;
            })
            .catch(() => {
              // Return a basic fallback response for failed static assets
              console.log('Failed to fetch static asset:', event.request.url);
              // Don't return undefined - browsers handle undefined poorly
              return new Response('', { status: 404 });
            });
        })
    );
    return;
  }

  // For all other requests (navigation, API calls, etc.) - network only
  // No caching of authenticated pages or dynamic content
  event.respondWith(fetch(event.request));
});

// Message event - handle updates from the main thread
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});