"""
Management command to send scheduled exam push notifications.

Run this command periodically (e.g. every minute via cron or Render cron job):
    python manage.py send_exam_reminders

It checks all active ExamCenterExams and sends timed notifications:
  - 5 minutes before exam starts
  - When exam starts
  - 3 minutes before exam writing period ends
  - When exam ends (+ submission window open for online exams)
  - 3 minutes before submission window closes (online exams only)

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
    notify_submission_closing_soon,
)


class Command(BaseCommand):
    help = 'Send scheduled push notifications for upcoming / running exams.'

    def handle(self, *args, **options):
        now = timezone.now()
        # Only consider exams that haven't fully finished yet
        # (plus a small buffer so the final notification can still fire)
        buffer = now - _dt.timedelta(minutes=5)
        exams = ExamCenterExam.objects.all()

        sent_total = 0

        for exam in exams:
            # Skip exams that finished more than 5 minutes ago
            if exam.final_end_datetime < buffer:
                continue

            sent_total += self._check_and_send(exam, now)

        if sent_total:
            self.stdout.write(self.style.SUCCESS(f'Sent {sent_total} notification(s).'))
        else:
            self.stdout.write('No notifications to send right now.')

    # ------------------------------------------------------------------

    def _already_sent(self, exam, ntype):
        return ExamNotificationLog.objects.filter(exam=exam, notification_type=ntype).exists()

    def _mark_sent(self, exam, ntype):
        ExamNotificationLog.objects.get_or_create(exam=exam, notification_type=ntype)

    def _check_and_send(self, exam, now):
        """Evaluate all scheduled notification windows for one exam."""
        sent = 0

        # 1. 5 minutes before start
        five_before = exam.start_datetime - _dt.timedelta(minutes=5)
        if five_before <= now < exam.start_datetime:
            if not self._already_sent(exam, 'reminder_5min'):
                try:
                    notify_exam_reminder_5min(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending 5-min reminder for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_5min')
                sent += 1

        # 2. Exam started
        if exam.start_datetime <= now < exam.exam_end_datetime:
            if not self._already_sent(exam, 'reminder_start'):
                try:
                    notify_exam_started(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending start notification for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_start')
                sent += 1

        # 3. 3 minutes before exam writing period ends
        three_before_end = exam.exam_end_datetime - _dt.timedelta(minutes=3)
        if three_before_end <= now < exam.exam_end_datetime:
            if not self._already_sent(exam, 'reminder_3min_end'):
                try:
                    notify_exam_ending_soon(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending 3-min-end warning for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'reminder_3min_end')
                sent += 1

        # 4. Exam ended (+ submission window open for online exams)
        if now >= exam.exam_end_datetime:
            if not self._already_sent(exam, 'exam_ended'):
                try:
                    notify_exam_ended(exam)
                except Exception as e:
                    self.stderr.write(f'Error sending exam-ended notification for exam {exam.pk}: {e}')
                self._mark_sent(exam, 'exam_ended')
                sent += 1

        # 5. 3 minutes before submission window closes (online exams only)
        if exam.exam_mode == 'online':
            three_before_submission_end = exam.final_end_datetime - _dt.timedelta(minutes=3)
            if three_before_submission_end <= now < exam.final_end_datetime:
                if not self._already_sent(exam, 'submission_3min'):
                    try:
                        notify_submission_closing_soon(exam)
                    except Exception as e:
                        self.stderr.write(f'Error sending submission-closing warning for exam {exam.pk}: {e}')
                    self._mark_sent(exam, 'submission_3min')
                    sent += 1

        return sent
