from django.contrib.auth import get_user_model

from .models import GuestTeacherAccount


GUEST_ACCOUNT_SESSION_KEY = 'guest_account_id'
GUEST_USERNAME_SESSION_KEY = 'guest_username'


def get_guest_account_for_request(request):
    """Return active GuestTeacherAccount for this request or None."""
    cached = getattr(request, '_cached_guest_account', None)
    if cached is not None:
        return cached

    if not request.user.is_authenticated:
        request._cached_guest_account = None
        return None

    guest_account_id = request.session.get(GUEST_ACCOUNT_SESSION_KEY)
    if not guest_account_id:
        request._cached_guest_account = None
        return None

    try:
        guest_account = GuestTeacherAccount.objects.select_related('teacher', 'guest_user').get(
            id=guest_account_id,
            teacher=request.user,
        )
    except GuestTeacherAccount.DoesNotExist:
        clear_guest_session(request)
        request._cached_guest_account = None
        return None

    request._cached_guest_account = guest_account
    return guest_account


def is_guest_session(request):
    return get_guest_account_for_request(request) is not None


def start_guest_session(request, guest_account):
    request.session[GUEST_ACCOUNT_SESSION_KEY] = guest_account.id
    request.session[GUEST_USERNAME_SESSION_KEY] = guest_account.guest_user.username
    request._cached_guest_account = guest_account


def clear_guest_session(request):
    request.session.pop(GUEST_ACCOUNT_SESSION_KEY, None)
    request.session.pop(GUEST_USERNAME_SESSION_KEY, None)
    request._cached_guest_account = None


def delete_guest_user_account(guest_account):
    """Delete guest auth user and linked guest-account record safely."""
    User = get_user_model()
    guest_user_id = guest_account.guest_user_id
    guest_account.delete()
    if guest_user_id:
        User.objects.filter(id=guest_user_id).delete()
