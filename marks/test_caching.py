"""Exercise deployment cache policy with real collected files, without a database."""

import gzip
import json
import os
import runpy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from cloudinary_storage.storage import MediaCloudinaryStorage
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.template.loader import render_to_string
from django.template import Context, Template
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from whitenoise.middleware import WhiteNoiseMiddleware
from whitenoise.storage import CompressedManifestStaticFilesStorage

from .middleware import PageCacheControlMiddleware


class LocalDevelopmentStaticTests(SimpleTestCase):
    def test_runserver_defaults_to_debug_and_preserves_explicit_settings(self):
        for command, configured, expected in (
            ('runserver', None, True),
            ('gunicorn', None, False),
            ('collectstatic', None, False),
            ('runserver', 'False', False),
        ):
            with self.subTest(command=command, configured=configured):
                with patch.dict(os.environ, {'SECRET_KEY': 'test-only', 'DATABASE_URL': ''}):
                    os.environ.pop('DEBUG', None)
                    if configured is not None:
                        os.environ['DEBUG'] = configured
                    with patch('dotenv.load_dotenv'), patch.object(sys, 'argv', ['manage.py', command]):
                        config = runpy.run_path(str(settings.BASE_DIR / 'ResTrack' / 'settings.py'))
                    self.assertIs(config['DEBUG'], expected)

    @override_settings(DEBUG=True)
    def test_development_favicon_renders_without_a_collected_manifest(self):
        with TemporaryDirectory() as directory, override_settings(STATIC_ROOT=directory):
            html = Template("{% load static %}{% static 'icons/favicon.ico' %}").render(Context())
            self.assertEqual(html, '/static/icons/favicon.ico')


@override_settings(DEBUG=False)
class ProductionStaticCachingTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.static_root = Path(cls.enterClassContext(TemporaryDirectory()))
        cls.enterClassContext(override_settings(STATIC_ROOT=cls.static_root))
        call_command('collectstatic', interactive=False, verbosity=0)

    def setUp(self):
        self.factory = RequestFactory()

    def test_active_storage_backends_preserve_media_and_hash_static_files(self):
        # These are the actual configured backends, not test-only replacements.
        self.assertIsInstance(default_storage, MediaCloudinaryStorage)
        self.assertIsInstance(staticfiles_storage, CompressedManifestStaticFilesStorage)
        manifest = json.loads((self.static_root / 'staticfiles.json').read_text())
        css_name = manifest['paths']['css/custom.css']
        self.assertRegex(css_name, r'^css/custom\.[0-9a-f]{12}\.css$')
        self.assertEqual(staticfiles_storage.url('css/custom.css'), '/static/' + css_name)
        css_path = self.static_root / css_name
        self.assertTrue(css_path.is_file())
        self.assertEqual(
            gzip.decompress(Path(str(css_path) + '.gz').read_bytes()),
            css_path.read_bytes(),
        )

    def test_base_template_uses_the_collected_asset_urls(self):
        request = self.factory.get('/')
        request.user = AnonymousUser()
        html = render_to_string(
            'marks/base.html', {'request': request, 'user': request.user}
        )
        for asset in (
            'css/custom.css',
            'manifest.json',
            'icons/favicon.ico',
            'icons/ResTrack-32x32.png',
            'icons/ResTrack-maskable-192x192.png',
        ):
            with self.subTest(asset=asset):
                self.assertIn(staticfiles_storage.url(asset), html)
                self.assertNotIn('href="/static/' + asset, html)

    def test_production_page_gets_revalidation_policy_through_middleware(self):
        response = self.client.get('/about/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertNotIn('no-store', response['Cache-Control'])
        self.assertContains(response, staticfiles_storage.url('css/custom.css'))

    def test_hashed_assets_keep_immutable_caching_and_compression(self):
        app = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
        response = app(self.factory.get(
            staticfiles_storage.url('css/custom.css'),
            HTTP_ACCEPT_ENCODING='gzip',
        ))
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn('immutable', response['Cache-Control'])
        self.assertIn('public', response['Cache-Control'])
        max_age = next(
            item.split('=', 1)[1]
            for item in response['Cache-Control'].split(', ')
            if item.startswith('max-age=')
        )
        self.assertGreaterEqual(int(max_age), 365 * 24 * 60 * 60)
        self.assertEqual(response['Content-Encoding'], 'gzip')
        self.assertTrue(gzip.decompress(b''.join(response.streaming_content)))

    def test_mutable_asset_urls_revalidate_and_support_conditional_requests(self):
        app = WhiteNoiseMiddleware(lambda request: HttpResponse(status=404))
        response = app(self.factory.get('/static/css/custom.css'))
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertIn('max-age=0', response['Cache-Control'])
        self.assertNotIn('immutable', response['Cache-Control'])
        self.assertNotIn('no-store', response['Cache-Control'])
        self.assertIn('ETag', response)
        conditional = app(self.factory.get(
            '/static/css/custom.css', HTTP_IF_NONE_MATCH=response['ETag']
        ))
        self.addCleanup(conditional.close)
        self.assertEqual(conditional.status_code, 304)

    def test_root_service_worker_revalidates_and_has_site_wide_scope(self):
        response = self.client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Service-Worker-Allowed'], '/')
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertIn('javascript', response['Content-Type'])
        self.assertIn(staticfiles_storage.manifest_hash, response.content.decode())


@override_settings(DEBUG=False)
class DeploymentIdentityTests(SimpleTestCase):
    def test_changed_asset_gets_new_url_and_changes_worker_without_manual_version(self):
        worker_view = resolve('/sw.js').func
        request = RequestFactory().get('/sw.js')
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            source.mkdir()
            asset = source / 'app.js'
            asset.write_text('window.release = "first";\n' * 30)
            (source / 'sw.js').write_text(
                (settings.BASE_DIR / 'static' / 'sw.js').read_text(encoding='utf-8'),
                encoding='utf-8',
            )
            builds = []
            for version in ('first', 'second'):
                asset.write_text(f'window.release = "{version}";\n' * 30)
                destination = root / version
                destination.mkdir()
                with override_settings(
                    STATIC_ROOT=destination,
                    STATICFILES_DIRS=[source],
                    STATICFILES_FINDERS=[
                        'django.contrib.staticfiles.finders.FileSystemFinder'
                    ],
                ):
                    call_command('collectstatic', interactive=False, verbosity=0)
                    response = worker_view(request)
                    self.assertEqual(response.status_code, 200)
                    builds.append((
                        staticfiles_storage.url('app.js'),
                        staticfiles_storage.manifest_hash,
                        response.content,
                    ))
            self.assertNotEqual(builds[0][0], builds[1][0])
            self.assertNotEqual(builds[0][1], builds[1][1])
            self.assertNotEqual(builds[0][2], builds[1][2])
            for asset_url, manifest_hash, worker in builds:
                with self.subTest(asset_url=asset_url):
                    self.assertIn(manifest_hash.encode(), worker)

    @override_settings(DEBUG=True)
    def test_worker_remains_available_before_development_collectstatic(self):
        with TemporaryDirectory() as directory:
            with override_settings(STATIC_ROOT=directory):
                response = resolve('/sw.js').func(RequestFactory().get('/sw.js'))
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-cache', response['Cache-Control'])
                self.assertIn(b"addEventListener('push'", response.content)


@override_settings(DEBUG=False)
class PageCacheControlTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get('/dashboard/')

    def apply_policy(self, response):
        return PageCacheControlMiddleware(lambda request: response)(self.request)

    def test_html_is_private_and_revalidated_while_remaining_cacheable(self):
        response = self.apply_policy(HttpResponse('<p>Current deployment</p>'))
        directives = {item.strip() for item in response['Cache-Control'].split(',')}
        self.assertIn('private', directives)
        self.assertIn('no-cache', directives)
        self.assertNotIn('no-store', directives)

    def test_existing_html_cache_policy_cannot_serve_stale_public_pages(self):
        response = HttpResponse('<p>Personalized page</p>')
        response['Cache-Control'] = 'public, max-age=600'
        response = self.apply_policy(response)
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('no-cache', response['Cache-Control'])
        self.assertNotIn('public', response['Cache-Control'])

    def test_stricter_html_policy_is_preserved(self):
        response = HttpResponse('<p>Private page</p>')
        response['Cache-Control'] = 'no-store'
        response = self.apply_policy(response)
        self.assertIn('no-store', response['Cache-Control'])

    def test_json_and_streaming_response_policies_are_unchanged(self):
        for response in (
            JsonResponse({'result': 'current'}),
            StreamingHttpResponse(iter([b'file content']), content_type='text/html'),
        ):
            with self.subTest(response_type=type(response).__name__):
                self.addCleanup(response.close)
                response['Cache-Control'] = 'private, max-age=120'
                self.assertEqual(
                    self.apply_policy(response)['Cache-Control'],
                    'private, max-age=120',
                )
