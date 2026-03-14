from django.http import JsonResponse
from django.shortcuts import redirect

from .guest_access import add_guest_read_only_message, get_guest_account_for_request


class GuestReadOnlyMiddleware:
    """Force guest sessions into read-only mode at server level."""

    RESTRICTED_PATH_PREFIXES = ('/admin/',)
    RESTRICTED_EXACT_PATHS = (
        '/delete-account/',
        '/manage-guest-account/',
    )
    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS', 'TRACE'}
    GUEST_READ_ONLY_TITLE = 'View-only guest account'
    GUEST_READ_ONLY_MESSAGE = 'Guest accounts are view-only and cannot perform this action.'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guest_account = get_guest_account_for_request(request)
        request.guest_account = guest_account

        if guest_account:
            path = request.path

            if path.startswith(self.RESTRICTED_PATH_PREFIXES) or path in self.RESTRICTED_EXACT_PATHS:
                if self._wants_json_response(request):
                    return JsonResponse(
                        {
                            'success': False,
                            'title': self.GUEST_READ_ONLY_TITLE,
                            'message': self.GUEST_READ_ONLY_MESSAGE,
                            # Backward-compatible field used by some existing handlers
                            'error': self.GUEST_READ_ONLY_MESSAGE,
                        },
                        status=403,
                    )
                add_guest_read_only_message(request)
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                referer = request.META.get('HTTP_REFERER')
                if referer:
                    return redirect(referer)
                return redirect('dashboard')

            if request.method not in self.SAFE_METHODS and path != '/logout/':
                if self._wants_json_response(request):
                    return JsonResponse(
                        {
                            'success': False,
                            'title': self.GUEST_READ_ONLY_TITLE,
                            'message': self.GUEST_READ_ONLY_MESSAGE,
                            # Backward-compatible field used by some existing handlers
                            'error': self.GUEST_READ_ONLY_MESSAGE,
                        },
                        status=403,
                    )
                add_guest_read_only_message(request)
                return redirect(request.META.get('HTTP_REFERER') or 'dashboard')

        return self.get_response(request)

    @staticmethod
    def _wants_json_response(request):
        """Return True when the client expects JSON (fetch/AJAX/API style requests)."""
        if request.path.startswith('/api/'):
            return True

        content_type = (request.content_type or '').lower()
        if 'application/json' in content_type:
            return True

        accept = (request.headers.get('Accept') or '').lower()
        if 'application/json' in accept:
            return True

        xrw = (request.headers.get('X-Requested-With') or '').lower()
        if xrw == 'xmlhttprequest':
            return True

        return False
