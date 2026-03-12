"""
Management command to send scheduled exam push notifications.

Run this command periodically (e.g. every 10 minutes via cron or Render cron job):
    python manage.py send_exam_reminders

It checks all active ExamCenterExams and sends timed notifications:
  - 10 minutes before exam starts
  - When exam starts
  - 10 minutes before exam writing period ends
  - When exam ends (+ submission window open for online exams)

Each notification is sent at most once per exam, tracked via ExamNotificationLog.
"""

import datetime as _dt

from django.core.management.base import BaseCommand
from django.utils import timezone

from marks.models import ExamCenterExam, ExamNotificationLog
from marks.notifications import (
    notify_exam_reminder_5min,
    notify_exam_started,
    notify_exam_ending_soon,
    notify_exam_ended,
)


class Command(BaseCommand):
    help = 'Send scheduled push notifications for upcoming / running exams.'

    # Distinct output prefix so the cron view can detect "no exams at all"
    NO_ACTIVE_EXAMS_MSG = '[SKIP] No active exams.'

    def handle(self, *args, **options):
        now = timezone.now()
        # Only consider exams that haven't fully finished yet
        # (plus a buffer so the final notification can still fire)
        buffer = now - _dt.timedelta(minutes=10)

        # --- OPTIMISATION: filter at the DB level instead of loading ALL exams ---
        # We only need exams whose final_end is in the future (with 5-min buffer).
        # Since final_end_datetime is computed from exam_date + start_time +
        # duration + bonus + submission, we apply a conservative lower-bound
        # filter: only exams with exam_date >= today - 2 days.
        # This avoids loading old/finished exams from the database entirely.
        cutoff_date = (now - _dt.timedelta(days=2)).date()

        # SHORT-CIRCUIT: lightweight EXISTS check — avoids the heavier
        # select_related JOIN and notification-log query when there are
        # simply no exams in the relevant date window.
        if not ExamCenterExam.objects.filter(exam_date__gte=cutoff_date).exists():
            self.stdout.write(self.NO_ACTIVE_EXAMS_MSG)
            from django import db
            db.connections.close_all()
            return

        exams = (
            ExamCenterExam.objects
            .filter(exam_date__gte=cutoff_date)
            .select_related('teacher')
        )

        # Pre-fetch all existing notification logs for these exams in one query
        # instead of hitting the DB per-exam per-notification-type.
        from marks.models import ExamNotificationLog
        existing_logs = set(
            ExamNotificationLog.objects
            .filter(exam__in=exams)
            .values_list('exam_id', 'notification_type')
        )

        sent_total = 0

        for exam in exams:
            # Skip exams that finished more than 5 minutes ago
            if exam.final_end_datetime < buffer:
                continue

            sent_total += self._check_and_send(exam, now, existing_logs)

        if sent_total:
            self.stdout.write(self.style.SUCCESS(f'Sent {sent_total} notification(s).'))
        else:
            self.stdout.write('No notifications to send right now.')

        # Close DB connections explicitly after the cron job finishes
        from django import db
        db.connections.close_all()

    # ------------------------------------------------------------------

    def _already_sent(self, exam, ntype, existing_logs):
        return (exam.pk, ntype) in existing_logs

    def _mark_sent(self, exam, ntype, existing_logs):
        ExamNotificationLog.objects.get_or_create(exam=exam, notification_type=ntype)
        existing_logs.add((exam.pk, ntype))

    def _check_and_send(self, exam, now, existing_logs):
        """Evaluate all scheduled notification windows for one exam."""
        sent = 0

        # 1. 10 minutes before start
        ten_before = exam.start_datetime - _dt.timedelta(minutes=10)
        if ten_before <= now < exam.start_datetime:
            if not self._already_sent(exam, 'reminder_5min', existing_logs):
                try:
                    notify_exam_reminder_5min(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending 10-min reminder for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_5min', existing_logs)
                sent += 1

        # 2. Exam started
        if exam.start_datetime <= now < exam.exam_end_datetime:
            if not self._already_sent(exam, 'reminder_start', existing_logs):
                try:
                    notify_exam_started(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending start notification for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_start', existing_logs)
                sent += 1

        # 3. 10 minutes before exam writing period ends
        ten_before_end = exam.exam_end_datetime - _dt.timedelta(minutes=10)
        if ten_before_end <= now < exam.exam_end_datetime:
            if not self._already_sent(exam, 'reminder_3min_end', existing_logs):
                try:
                    notify_exam_ending_soon(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending 10-min-end warning for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_3min_end', existing_logs)
                sent += 1

        # 4. Exam ended (+ submission window open for online exams)
        if now >= exam.exam_end_datetime:
            if not self._already_sent(exam, 'exam_ended', existing_logs):
                try:
                    notify_exam_ended(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending exam-ended notification for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'exam_ended', existing_logs)
                sent += 1

        return sent
