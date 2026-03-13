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

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        guest_account = get_guest_account_for_request(request)
        request.guest_account = guest_account

        if guest_account:
            path = request.path

            if path.startswith(self.RESTRICTED_PATH_PREFIXES) or path in self.RESTRICTED_EXACT_PATHS:
                add_guest_read_only_message(request)
                return redirect('dashboard')

            if request.method not in self.SAFE_METHODS and path != '/logout/':
                if path.startswith('/api/'):
                    return JsonResponse(
                        {
                            'success': False,
                            'error': 'Guest accounts are view-only and cannot perform this action.',
                        },
                        status=403,
                    )
                add_guest_read_only_message(request)
                return redirect(request.META.get('HTTP_REFERER') or 'dashboard')

        return self.get_response(request)
