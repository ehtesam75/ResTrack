"""
API views for Web Push notification subscription management.
"""

import json

from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET

from .models import PushSubscription


@login_required
@require_GET
def vapid_public_key(request):
    """Return the VAPID public key so JS can subscribe to push."""
    return JsonResponse({"publicKey": settings.VAPID_PUBLIC_KEY})


@login_required
@require_POST
def push_subscribe(request):
    """
    Save a push subscription for the logged-in user.
    Expects JSON body: { endpoint, keys: { p256dh, auth } }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not all([endpoint, p256dh, auth]):
        return JsonResponse({"error": "Missing subscription fields"}, status=400)

    # Upsert: if the endpoint already exists, update it (could be a re-subscribe)
    sub, created = PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
        },
    )

    return JsonResponse({"ok": True, "created": created})


@login_required
@require_POST
def push_unsubscribe(request):
    """
    Remove a push subscription for the logged-in user.
    Expects JSON body: { endpoint }
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    endpoint = data.get("endpoint")
    if not endpoint:
        return JsonResponse({"error": "Missing endpoint"}, status=400)

    deleted, _ = PushSubscription.objects.filter(
        user=request.user, endpoint=endpoint
    ).delete()

    return JsonResponse({"ok": True, "deleted": deleted})
