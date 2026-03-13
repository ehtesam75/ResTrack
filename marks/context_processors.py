from .guest_access import get_guest_account_for_request


def guest_session_context(request):
    guest_account = get_guest_account_for_request(request)
    return {
        'is_guest_session': guest_account is not None,
        'guest_session_username': guest_account.guest_user.username if guest_account else '',
    }
