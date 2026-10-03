"""Real Chromium deployment regression: .venv/Scripts/python browser_cache_ui.py.

Requires Playwright and its Chromium browser. Uses only a local HTTP server;
127.0.0.2 is a trustworthy loopback origin outside the worker's development list.
"""

from collections import Counter
from contextlib import ExitStack
from hashlib import md5
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread
import unittest
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


# The historical worker's relevant behavior: a fixed cache name, mutable URLs
# precached and cache-first, and immediate activation. Keep this small fixture
# independent of git history so the migration remains reproducible after merge.
LEGACY_WORKER = """
const NAME = 'restrack-static-v2.1.0';
self.addEventListener('install', event => event.waitUntil(
  caches.open(NAME).then(cache => cache.add('/static/css/custom.css'))
    .then(() => self.skipWaiting())
));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (!new URL(event.request.url).pathname.startsWith('/static/')) return;
  event.respondWith(caches.match(event.request).then(cached => cached ||
    fetch(event.request).then(async response => {
      if (response.ok) await (await caches.open(NAME)).put(event.request, response.clone());
      return response;
    })
  ));
});
"""
WORKER = (Path(__file__).parent / 'static' / 'sw.js').read_text(encoding='utf-8')
COLORS = ('red', 'blue', 'green')
STYLES = [f'#sample {{ color: {color}; }}' for color in COLORS]
ASSET_URLS = [
    f'/static/css/custom.{md5(css.encode()).hexdigest()[:12]}.css'
    for css in STYLES
]


class DeploymentServer(ThreadingHTTPServer):
    daemon_threads = True
    release = 0

    def __init__(self):
        self.requests = Counter()
        super().__init__(('127.0.0.2', 0), DeploymentHandler)


class DeploymentHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        self.server.requests[path] += 1
        release = self.server.release
        status, content_type, policy = 200, 'text/html', 'private, no-cache'
        if path == '/sw.js':
            content_type = 'application/javascript'
            body = LEGACY_WORKER if release == 0 else (
                f'self.RESTRACK_ASSET_VERSION = "browser-test-{release}";\n' + WORKER
            )
        elif path == '/static/css/custom.css' or path in ASSET_URLS:
            content_type = 'text/css'
            version = release if path.endswith('/custom.css') else ASSET_URLS.index(path)
            body = STYLES[version]
            policy = 'public, max-age=0' if path.endswith('/custom.css') else (
                'public, max-age=31536000, immutable'
            )
        elif path == '/static/manifest.json':
            content_type, body, policy = 'application/json', '{}', 'public, max-age=0'
        elif path == '/':
            asset = '/static/css/custom.css' if release == 0 else ASSET_URLS[release]
            script = '/sw.js?v=2.1.0' if release == 0 else '/sw.js'
            body = f"""<!doctype html><link rel="stylesheet" href="{asset}">
                <p id="sample">Current deployment</p><input id="answer">
                <script>
                window.changes = 0;
                navigator.serviceWorker.addEventListener('controllerchange', () => window.changes++);
                navigator.serviceWorker.register({json.dumps(script)}, {{scope: '/', updateViaCache: 'none'}});
                </script>"""
        else:
            status, body = 404, 'Missing'
        payload = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', policy)
        self.send_header('Content-Length', str(len(payload)))
        if path == '/sw.js':
            self.send_header('Service-Worker-Allowed', '/')
        self.end_headers()
        self.wfile.write(payload)


class WorkerDeploymentBrowserTests(unittest.TestCase):
    def test_old_cache_migrates_and_new_deployments_preserve_open_forms(self):
        with DeploymentServer() as server, sync_playwright() as playwright, ExitStack() as cleanup:
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            cleanup.callback(server.shutdown)
            browser = playwright.chromium.launch()
            cleanup.callback(browser.close)
            context = browser.new_context()
            cleanup.callback(context.close)
            origin = f'http://127.0.0.2:{server.server_port}'
            editor = context.new_page()
            editor.goto(origin)
            editor.wait_for_function('navigator.serviceWorker.controller !== null')
            editor.fill('#answer', 'An unsaved exam answer')
            editor.evaluate("window.documentToken = 'original'; caches.open('another-app-cache')")
            self.assertEqual(editor.locator('#sample').evaluate('el => getComputedStyle(el).color'), 'rgb(255, 0, 0)')

            server.release = 1
            # The old worker reproduces the production defect despite new bytes.
            self.assertIn('red', editor.evaluate("fetch('/static/css/custom.css').then(r => r.text())"))
            page = context.new_page()
            page.goto(origin)
            editor.wait_for_function("navigator.serviceWorker.controller.scriptURL.endsWith('/sw.js')")
            editor.wait_for_function("caches.keys().then(keys => keys.includes('restrack-static-v3-browser-test-1') && !keys.includes('restrack-static-v2.1.0'))")
            self.assertEqual(page.locator('#sample').evaluate('el => getComputedStyle(el).color'), 'rgb(0, 0, 255)')
            self.assertEqual(editor.input_value('#answer'), 'An unsaved exam answer')
            self.assertEqual(editor.evaluate('window.documentToken'), 'original')
            self.assertIn('another-app-cache', editor.evaluate('caches.keys()'))
            registrations = editor.evaluate('navigator.serviceWorker.getRegistrations().then(rs => rs.map(r => ({scope:r.scope, cache:r.updateViaCache})))')
            self.assertEqual(registrations, [{'scope': origin + '/', 'cache': 'none'}])

            # Force HTTP revalidation requests: Cache Storage must still satisfy
            # immutable assets without another server request.
            fetch_style = '(url) => fetch(url, {cache: "reload"}).then(r => r.text())'
            self.assertIn('blue', page.evaluate(fetch_style, ASSET_URLS[1]))
            requests_before = server.requests[ASSET_URLS[1]]
            self.assertIn('blue', page.evaluate(fetch_style, ASSET_URLS[1]))
            self.assertEqual(server.requests[ASSET_URLS[1]], requests_before)
            self.assertIn('blue', page.evaluate(fetch_style, '/static/css/custom.css'))

            # Updating a mutable URL works online even before a worker update.
            server.release = 2
            self.assertIn('green', page.evaluate(fetch_style, '/static/css/custom.css'))
            page.fill('#answer', 'Keep this answer too')
            page.evaluate("window.documentToken = 'second'")
            changes_before = editor.evaluate('window.changes')
            page.evaluate('navigator.serviceWorker.getRegistration().then(r => r.update())')
            editor.wait_for_function('(before) => window.changes > before', arg=changes_before)
            editor.wait_for_function("caches.keys().then(keys => keys.includes('restrack-static-v3-browser-test-2') && !keys.includes('restrack-static-v3-browser-test-1'))")
            self.assertEqual(editor.input_value('#answer'), 'An unsaved exam answer')
            self.assertEqual(page.input_value('#answer'), 'Keep this answer too')
            self.assertEqual(page.evaluate('window.documentToken'), 'second')
            self.assertIn('another-app-cache', editor.evaluate('caches.keys()'))
            latest = context.new_page()
            latest.goto(origin)
            self.assertEqual(latest.locator('#sample').evaluate('el => getComputedStyle(el).color'), 'rgb(0, 128, 0)')

            # Preserve useful offline behavior for both mutable and hashed assets.
            self.assertIn('green', latest.evaluate(fetch_style, ASSET_URLS[2]))
            self.assertIn('green', latest.evaluate(fetch_style, '/static/css/custom.css'))
            context.set_offline(True)
            self.assertIn('green', latest.evaluate(fetch_style, ASSET_URLS[2]))
            self.assertIn('green', latest.evaluate(fetch_style, '/static/css/custom.css'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
