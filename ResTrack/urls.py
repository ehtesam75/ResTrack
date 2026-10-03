import json

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse
from django.views.decorators.cache import cache_control


@cache_control(no_cache=True, max_age=0, must_revalidate=True)
def service_worker(request):
    """Serve service worker from root URL so its scope covers the entire site.

    A service worker's default scope is determined by its URL path.
    At /static/sw.js the scope would be /static/, meaning
    navigator.serviceWorker.ready never resolves on app pages like
    /dashboard/ — and push subscriptions are never created.
    Serving from /sw.js gives scope / which covers everything.
    """
    sw_path = finders.find('sw.js')
    if not sw_path:
        return HttpResponse(
            '// Service worker not found',
            status=404,
            content_type='application/javascript',
        )
    with open(sw_path, 'r', encoding='utf-8') as f:
        # collectstatic changes this hash when any asset changes. Including it
        # in the worker bytes triggers an update and retires the prior cache
        # automatically, without a hand-maintained release number.
        asset_version = 'dev' if settings.DEBUG else (
            getattr(staticfiles_storage, 'manifest_hash', '') or 'dev'
        )
        source = f'self.RESTRACK_ASSET_VERSION = {json.dumps(asset_version)};\n' + f.read()
        response = HttpResponse(source, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


urlpatterns = [
    path('sw.js', service_worker, name='service_worker'),
    path('admin/', admin.site.urls),
    path('', include('marks.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
