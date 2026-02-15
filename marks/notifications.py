"""
Web Push notification utilities for ResTrack.
Sends push notifications to subscribed users via the Web Push API.
"""

import json
import logging

from django.conf import settings
from pywebpush import webpush, WebPushException

from .models import PushSubscription

logger = logging.getLogger(__name__)


def _send_push(subscription, payload):
    """
    Send a single push notification.
    Returns True on success, False on failure.
    Automatically removes subscriptions that are no longer valid (410 Gone).
    """
    if not settings.VAPID_PRIVATE_KEY or not settings.VAPID_PUBLIC_KEY:
        logger.warning("VAPID keys not configured — skipping push notification.")
        return False

    try:
        webpush(
            subscription_info=subscription.subscription_info,
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.VAPID_ADMIN_EMAIL}"},
            ttl=604800,  # 7 days — push service queues if device is offline
            headers={"Urgency": "high"},  # High priority — triggers heads-up/banner on Android
        )
        return True
    except WebPushException as e:
        status_code = e.response.status_code if e.response is not None else None
        if status_code in (404, 410):
            # Subscription expired or unsubscribed — remove it
            logger.info("Removing expired push subscription %s", subscription.endpoint[:60])
            subscription.delete()
        else:
            logger.error("WebPush error (status=%s): %s", status_code, e)
        return False
    except Exception as e:
        logger.error("Unexpected push error: %s", e)
        return False


def _send_to_users(user_ids, payload):
    """Send a push notification to all subscriptions belonging to the given user IDs."""
    subscriptions = PushSubscription.objects.filter(user_id__in=user_ids)
    sent = 0
    for sub in subscriptions:
        if _send_push(sub, payload):
            sent += 1
    logger.info("Push sent to %d/%d subscriptions for %d users.", sent, subscriptions.count(), len(user_ids))
    return sent


# ------------------------------------------------------------------
# Public helpers called from views
# ------------------------------------------------------------------

def notify_exam_created(exam_center_exam):
    """
    Notify all enrolled students of a teacher when a new Exam Center exam
    is created.

    Args:
        exam_center_exam: ExamCenterExam instance (just created).
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher

    # All students enrolled under this teacher who have a user account
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    # Build short date/time string (platform-safe)
    start_dt = exam_center_exam.start_datetime
    day = start_dt.day
    month = start_dt.strftime("%b")
    hour = start_dt.strftime("%I").lstrip("0") or "12"
    minute = start_dt.strftime("%M")
    ampm = start_dt.strftime("%p")
    short_dt = f"{day} {month}, {hour}:{minute} {ampm}"  # e.g. "5 Feb, 3:30 PM"

    payload = {
        "title": "📝 New Exam Scheduled",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} | {short_dt}",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-created-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_result_published(exam_id, student_ids, teacher):
    """
    Notify students when their exam results are published.

    Args:
        exam_id: The Exam.exam_id value (shared across bulk entries).
        student_ids: List of Student model IDs who got results.
        teacher: The teacher User who published the results.
    """
    from .models import StudentProfile, Exam

    # Get User IDs for the participating students
    student_profiles = StudentProfile.objects.filter(
        student_id__in=student_ids,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    # Get exam metadata for the notification body
    exam_record = Exam.objects.filter(exam_id=exam_id, teacher=teacher).first()
    subject_name = exam_record.subject.name if exam_record else "Exam"

    payload = {
        "title": "📊 Results Published",
        "body": f"Exam #{exam_id} — {subject_name} results are out! Check your score.",
        "url": f"/exams/detail/{exam_id}/",
        "tag": f"result-published-{exam_id}",
    }

    return _send_to_users(user_ids, payload)


def notify_exam_edited(exam_center_exam):
    """
    Notify all enrolled students of a teacher when an Exam Center exam
    is edited (e.g. time, subject, or chapter changed).

    Args:
        exam_center_exam: ExamCenterExam instance (just saved after edit).
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher

    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    # Build short date/time string
    start_dt = exam_center_exam.start_datetime
    day = start_dt.day
    month = start_dt.strftime("%b")
    hour = start_dt.strftime("%I").lstrip("0") or "12"
    minute = start_dt.strftime("%M")
    ampm = start_dt.strftime("%p")
    short_dt = f"{day} {month}, {hour}:{minute} {ampm}"

    payload = {
        "title": "✏️ Exam Updated",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} | {short_dt} has been updated.",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-edited-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_result_edited(exam):
    """
    Notify a specific student when their exam result is edited by the teacher.

    Args:
        exam: Exam model instance (just updated).
    """
    from .models import StudentProfile

    if not exam.student:
        return 0

    try:
        sp = StudentProfile.objects.select_related('user').get(
            student=exam.student,
            user__isnull=False,
        )
    except StudentProfile.DoesNotExist:
        return 0

    subject_name = exam.subject.name if exam.subject else "Exam"

    payload = {
        "title": "📝 Result Updated",
        "body": f"Exam #{exam.exam_id} — Your {subject_name} result has been updated.",
        "url": f"/exams/detail/{exam.exam_id}/",
        "tag": f"result-edited-{exam.exam_id}-{exam.student_id}",
    }

    return _send_to_users([sp.user_id], payload)


# ------------------------------------------------------------------
# Scheduled notification helpers (called by management command)
# ------------------------------------------------------------------

def notify_exam_reminder_5min(exam_center_exam):
    """
    Notify enrolled students 5 minutes before an exam starts.
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    payload = {
        "title": "⏰ Exam in 5 Minutes",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} starts in 5 minutes!",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-reminder-5min-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_exam_started(exam_center_exam):
    """
    Notify enrolled students that an exam has just started.
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    payload = {
        "title": "🚀 Exam Started",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} has started. Good luck!",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-started-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_exam_ending_soon(exam_center_exam):
    """
    Notify enrolled students 3 minutes before the exam writing period ends.
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    payload = {
        "title": "⚠️ 3 Minutes Left",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} ends in 3 minutes!",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-ending-soon-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_exam_ended(exam_center_exam):
    """
    Notify enrolled students that the exam has ended.
    For online exams, also inform that the submission window is now open.
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    if exam_center_exam.exam_mode == 'online':
        body = (
            f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} has ended. "
            f"Submission window is now open!"
        )
    else:
        body = f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject} has ended."

    payload = {
        "title": "🏁 Exam Ended",
        "body": body,
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"exam-ended-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_submission_closing_soon(exam_center_exam):
    """
    Notify enrolled students 3 minutes before the submission window closes
    (online exams only).
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    payload = {
        "title": "⏳ Submission Closing Soon",
        "body": f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject}: submission closes in 3 minutes!",
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"submission-closing-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)


def notify_bonus_time_granted(exam_center_exam, minutes, phase):
    """
    Notify enrolled students when the teacher grants bonus time.

    Args:
        exam_center_exam: ExamCenterExam instance.
        minutes: Number of bonus minutes just added.
        phase: 'running' or 'submission' — which period the bonus extends.
    """
    from .models import StudentProfile

    teacher = exam_center_exam.teacher
    student_profiles = StudentProfile.objects.filter(
        created_by=teacher,
        user__isnull=False,
    ).select_related('user')

    user_ids = [sp.user_id for sp in student_profiles]
    if not user_ids:
        return 0

    if phase == 'submission':
        body = (
            f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject}: "
            f"+{minutes} min added to the submission window!"
        )
    else:
        body = (
            f"Exam #{exam_center_exam.exam_display_id} — {exam_center_exam.subject}: "
            f"+{minutes} min bonus time added!"
        )

    payload = {
        "title": "🕐 Bonus Time Added",
        "body": body,
        "url": f"/exam-center/{exam_center_exam.pk}/",
        "tag": f"bonus-time-{exam_center_exam.pk}",
    }

    return _send_to_users(user_ids, payload)
