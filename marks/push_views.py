"""
API views for Web Push notification subscription management.
"""

import json

from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt

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


# ---------------------------------------------------------------------------
# Cron endpoint — called externally by cron-job.org every minute
# ---------------------------------------------------------------------------

import logging
import hmac

logger = logging.getLogger(__name__)


@csrf_exempt
@require_GET
def cron_send_exam_reminders(request):
    """
    External cron endpoint that triggers the send_exam_reminders command.
    Secured with a secret token passed as ?token=<CRON_SECRET_TOKEN>.
    """
    expected_token = getattr(settings, "CRON_SECRET_TOKEN", "")
    provided_token = request.GET.get("token", "")

    # Reject if no token is configured on the server
    if not expected_token:
        logger.warning("Cron endpoint called but CRON_SECRET_TOKEN is not configured.")
        return JsonResponse({"error": "Cron endpoint is not configured."}, status=503)

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(provided_token, expected_token):
        logger.warning("Cron endpoint called with invalid token.")
        return JsonResponse({"error": "Forbidden"}, status=403)

    # Run the management command
    from django.core.management import call_command
    from io import StringIO

    stdout = StringIO()
    stderr = StringIO()

    try:
        call_command("send_exam_reminders", stdout=stdout, stderr=stderr)
        output = stdout.getvalue().strip()
        errors = stderr.getvalue().strip()
        logger.info("Cron send_exam_reminders completed: %s", output)
        return JsonResponse({
            "ok": True,
            "message": output or "No notifications to send right now.",
            "errors": errors or None,
        })
    except Exception as e:
        logger.error("Cron send_exam_reminders failed: %s", e)
        return JsonResponse({"ok": False, "error": str(e)}, status=500)
