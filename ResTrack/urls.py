from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles import finders
from django.http import HttpResponse


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
        response = HttpResponse(f.read(), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
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
