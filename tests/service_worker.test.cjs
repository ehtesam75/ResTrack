const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const workerSource = fs.readFileSync(path.join(__dirname, '../static/sw.js'), 'utf8');
const currentCache = 'restrack-static-v3-build123';

function worker({ origin = 'https://restrack.example', version = 'build123' } = {}) {
  const listeners = new Map();
  const stores = new Map();
  const calls = { fetch: [], claim: 0, navigate: 0, skipWaiting: 0, notifications: [] };
  const key = request => new URL(typeof request === 'string' ? request : request.url, origin).href;
  const state = {
    network: async () => new Response('network asset'),
    openError: null,
    putError: null,
    keysError: null,
    deleteError: null,
    beforePut: null,
  };
  const caches = {
    async open(name) {
      if (state.openError) throw state.openError;
      if (!stores.has(name)) stores.set(name, new Map());
      const entries = stores.get(name);
      return {
        async match(request) { return entries.get(key(request))?.clone(); },
        async put(request, response) {
          if (state.beforePut) await state.beforePut();
          if (state.putError) throw state.putError;
          entries.set(key(request), response.clone());
        },
        async delete(request) { return entries.delete(key(request)); },
      };
    },
    async keys() {
      if (state.keysError) throw state.keysError;
      return [...stores.keys()];
    },
    async delete(name) {
      if (state.deleteError) throw state.deleteError;
      return stores.delete(name);
    },
    async match() { throw new Error('Global caches.match may resurrect legacy assets'); },
  };
  const clients = {
    async claim() { calls.claim++; },
    async matchAll() { return [{ url: origin, async navigate() { calls.navigate++; } }]; },
  };
  const self = {
    location: new URL(origin),
    RESTRACK_ASSET_VERSION: version,
    clients,
    registration: {
      async showNotification(title, options) { calls.notifications.push({ title, options }); },
    },
    async skipWaiting() { calls.skipWaiting++; },
    addEventListener(type, handler) { listeners.set(type, handler); },
  };
  vm.runInNewContext(workerSource, {
    self, caches, clients, URL, Request, Response,
    console: { log() {}, warn() {} },
    async fetch(request, options) {
      calls.fetch.push({ url: key(request), options });
      return state.network(request, options);
    },
  }, { filename: 'static/sw.js' });

  function dispatch(type, properties = {}) {
    const lifetimes = [];
    let response;
    listeners.get(type)({
      ...properties,
      waitUntil(promise) { lifetimes.push(Promise.resolve(promise)); },
      respondWith(promise) { response = Promise.resolve(promise); },
    });
    return { response, lifetimes, done: () => Promise.all(lifetimes) };
  }

  return {
    state, calls, caches, stores, dispatch,
    request(url, options) {
      return dispatch('fetch', { request: new Request(new URL(url, origin), options) });
    },
    async seed(url, body, name = currentCache) {
      await (await caches.open(name)).put(url, new Response(body));
    },
    async cached(url, name = currentCache) {
      return (await (await caches.open(name)).match(url))?.text();
    },
  };
}

test('mutable CSS revalidates on every request and replaces cached content', async () => {
  const app = worker();
  await app.seed('/static/css/custom.css', 'old css');
  app.state.network = async () => new Response('new css');
  const first = app.request('/static/css/custom.css');
  assert.equal(await (await first.response).text(), 'new css');
  await first.done();
  assert.equal(await app.cached('/static/css/custom.css'), 'new css');
  app.state.network = async () => new Response('next deployment');
  assert.equal(await (await app.request('/static/css/custom.css').response).text(), 'next deployment');
  assert.equal(app.calls.fetch.length, 2);
  assert.ok(app.calls.fetch.every(call => call.options.cache === 'no-cache'));
});

test('Django content-hashed assets are cache-first and a new hash fetches new content', async () => {
  const app = worker();
  const oldUrl = '/static/css/custom.012345abcdef.css';
  const newUrl = '/static/css/custom.abcdef012345.css';
  assert.equal(await (await app.request(oldUrl).response).text(), 'network asset');
  app.state.network = async () => { throw new TypeError('offline'); };
  assert.equal(await (await app.request(oldUrl).response).text(), 'network asset');
  assert.equal(app.calls.fetch.length, 1);
  assert.equal(app.calls.fetch[0].options, undefined);
  app.state.network = async () => new Response('new version');
  assert.equal(await (await app.request(newUrl).response).text(), 'new version');
  assert.equal(app.calls.fetch.length, 2);
});

test('a filename with a short hash remains mutable', async () => {
  const app = worker();
  await app.seed('/static/app.abc123.js', 'stale');
  assert.equal(await (await app.request('/static/app.abc123.js').response).text(), 'network asset');
  assert.equal(app.calls.fetch[0].options.cache, 'no-cache');
});

test('legacy cache entries never override new network content', async () => {
  const app = worker();
  const url = '/static/app.012345abcdef.js';
  await app.seed(url, 'legacy stale asset', 'restrack-static-v2.1.0');
  await app.seed(url, 'unrelated cache asset', 'another-application');
  assert.equal(await (await app.request(url).response).text(), 'network asset');
});

test('mutable assets remain available offline without masking online errors', async () => {
  const app = worker();
  await app.seed('/static/manifest.json', 'offline manifest');
  app.state.network = async () => { throw new TypeError('offline'); };
  assert.equal(await (await app.request('/static/manifest.json').response).text(), 'offline manifest');
  await assert.rejects(app.request('/static/missing.js').response, /offline/);
  app.state.network = async () => new Response('removed', { status: 404 });
  assert.equal((await app.request('/static/manifest.json').response).status, 404);
  assert.equal(await app.cached('/static/manifest.json'), undefined);
});

test('no-store responses are served but never retained for offline fallback', async () => {
  const app = worker();
  await app.seed('/static/private.json', 'previously cached');
  app.state.network = async () => new Response('fresh', { headers: { 'Cache-Control': 'no-store' } });
  assert.equal(await (await app.request('/static/private.json').response).text(), 'fresh');
  assert.equal(await app.cached('/static/private.json'), undefined);
});

test('navigation, API, cross-origin, non-GET and local requests pass through', () => {
  const app = worker();
  for (const [url, options] of [
    ['/', undefined],
    ['/api/results/', undefined],
    ['https://cdn.example/static/app.js', undefined],
    ['/static/app.js', { method: 'POST', body: 'payload' }],
    ['/static/app.js', { method: 'HEAD' }],
  ]) {
    const event = app.request(url, options);
    assert.equal(event.response, undefined);
    assert.equal(event.lifetimes.length, 0);
  }
  for (const origin of ['http://localhost:8000', 'http://127.0.0.1:8000', 'http://[::1]:8000']) {
    assert.equal(worker({ origin }).request('/static/app.js').response, undefined);
  }
  assert.equal(app.calls.fetch.length, 0);
});

test('cache storage failures do not hide successful network responses', async () => {
  for (const fault of ['openError', 'putError']) {
    const app = worker();
    app.state[fault] = new Error('storage unavailable');
    assert.equal(await (await app.request('/static/app.js').response).text(), 'network asset');
  }
});

test('fetch event lifetime covers the cache write', async () => {
  const app = worker();
  let finishWrite;
  let startedWrite;
  const started = new Promise(resolve => { startedWrite = resolve; });
  app.state.beforePut = () => {
    startedWrite();
    return new Promise(resolve => { finishWrite = resolve; });
  };
  const event = app.request('/static/app.js');
  assert.equal(event.lifetimes.length, 1);
  let finished = false;
  const completion = event.done().then(() => { finished = true; });
  await started;
  assert.equal(finished, false);
  finishWrite();
  await completion;
  assert.equal(await app.cached('/static/app.js'), 'network asset');
});

test('installation revalidates precached assets and can activate while offline', async () => {
  const app = worker();
  const event = app.dispatch('install');
  await event.done();
  assert.ok(app.calls.fetch.length > 0);
  assert.ok(app.calls.fetch.every(call => call.url.startsWith('https://restrack.example/static/')));
  assert.ok(app.calls.fetch.every(call => call.options.cache === 'no-cache'));
  assert.equal(app.calls.skipWaiting, 1);
  assert.equal(await app.cached('/static/css/custom.css'), 'network asset');

  const offline = worker();
  offline.state.network = async () => { throw new TypeError('offline'); };
  await offline.dispatch('install').done();
  assert.equal(offline.calls.skipWaiting, 1);
});

test('activation retires only old ResTrack caches and never reloads open pages', async () => {
  const app = worker();
  for (const name of ['restrack-v2.1.0', 'restrack-static-v2.1.0', 'restrack-static-v3-oldbuild', currentCache, 'other-app']) {
    await app.caches.open(name);
  }
  await app.dispatch('activate').done();
  assert.deepEqual(await app.caches.keys(), [currentCache, 'other-app']);
  assert.equal(app.calls.claim, 1);
  assert.equal(app.calls.navigate, 0);
});

test('development activation clears all owned caches and leaves other caches intact', async () => {
  const app = worker({ origin: 'http://localhost:8000' });
  await app.caches.open(currentCache);
  await app.caches.open('restrack-static-v2.1.0');
  await app.caches.open('other-app');
  await app.dispatch('install').done();
  assert.equal(app.calls.fetch.length, 0);
  await app.dispatch('activate').done();
  assert.deepEqual(await app.caches.keys(), ['other-app']);
  assert.equal(app.calls.navigate, 0);
});

test('activation claims clients even when old cache cleanup fails', async () => {
  for (const fault of ['keysError', 'deleteError']) {
    const app = worker();
    await app.caches.open('restrack-static-v2.1.0');
    app.state[fault] = new Error('storage unavailable');
    await app.dispatch('activate').done();
    assert.equal(app.calls.claim, 1);
    assert.equal(app.calls.navigate, 0);
  }
});

test('legacy update messages extend lifetime and never clear unrelated caches or reload tabs', async () => {
  const app = worker();
  await app.caches.open(currentCache);
  await app.caches.open('other-app');
  const skip = app.dispatch('message', { data: { type: 'SKIP_WAITING' } });
  assert.equal(skip.lifetimes.length, 1);
  await skip.done();
  assert.equal(app.calls.skipWaiting, 1);
  const clear = app.dispatch('message', { data: { type: 'CLEAR_ICON_CACHE' } });
  assert.equal(clear.lifetimes.length, 1);
  await clear.done();
  assert.deepEqual(await app.caches.keys(), ['other-app']);
  assert.equal(app.calls.navigate, 0);
});

test('build version supplied by Django selects a new cache namespace', async () => {
  const app = worker({ version: 'next-build' });
  await app.request('/static/app.js').response;
  assert.deepEqual(await app.caches.keys(), ['restrack-static-v3-next-build']);
});

test('push notifications retain their existing payload and lifetime', async () => {
  const app = worker();
  const event = app.dispatch('push', {
    data: { json: () => ({ title: 'Exam results', body: 'Ready', url: '/results/' }) },
  });
  await event.done();
  assert.equal(app.calls.notifications.length, 1);
  assert.equal(app.calls.notifications[0].title, 'Exam results');
  assert.equal(app.calls.notifications[0].options.body, 'Ready');
  assert.equal(app.calls.notifications[0].options.data.url, '/results/');
  assert.equal(app.calls.notifications[0].options.icon, 'https://restrack.example/static/icons/ResTrack-192x192.png');
});
