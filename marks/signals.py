
from django.db.models.signals import pre_save, post_delete, post_save
from django.dispatch import receiver
from django.db.models import Max
from django.contrib.auth.models import User
from .models import Exam
from .notifications import notify_teacher_password_changed

@receiver(post_save, sender=Exam)
def recalculate_points_on_save(sender, instance, **kwargs):
    """Recalculate student's lifetime points after exam save.
    
    Skip if the instance has _skip_recalculate=True (set during bulk operations).
    """
    if getattr(instance, '_skip_recalculate', False):
        return
    if instance.student:
        instance.student.recalculate_lifetime_points()


@receiver(pre_save, sender=Exam)
def assign_exam_id(sender, instance, **kwargs):
    """Automatically assign exam_id before saving"""
    # Only assign exam_id if not provided manually
    if instance.exam_id is None:
        if instance.group_id:
            # Check if other exams with same group_id exist
            existing = Exam.objects.filter(group_id=instance.group_id).exclude(pk=instance.pk).first()
            if existing and existing.exam_id:
                instance.exam_id = existing.exam_id
            else:
                # Get max exam_id for this teacher and increment
                max_id = Exam.objects.filter(teacher=instance.teacher).aggregate(Max('exam_id'))['exam_id__max']
                instance.exam_id = (max_id or 0) + 1
        else:
            # Single entry, get new exam_id for this teacher
            max_id = Exam.objects.filter(teacher=instance.teacher).aggregate(Max('exam_id'))['exam_id__max']
            instance.exam_id = (max_id or 0) + 1


@receiver(post_delete, sender=Exam)
def recalculate_points_on_delete(sender, instance, **kwargs):
    """Recalculate student's lifetime points after exam deletion"""
    if getattr(instance, '_skip_recalculate', False):
        return
    if instance.student:
        instance.student.recalculate_lifetime_points()


@receiver(pre_save, sender=User)
def track_user_password_change(sender, instance, **kwargs):
    """Mark whether a user's password hash changed before saving."""
    instance._password_changed_for_push = False

    if not instance.pk:
        return

    old = sender.objects.filter(pk=instance.pk).values('password').first()
    if not old:
        return

    instance._password_changed_for_push = old['password'] != instance.password


@receiver(post_save, sender=User)
def notify_teacher_on_password_change(sender, instance, created, **kwargs):
    """Send a push alert when an existing teacher account password is changed."""
    if created:
        return

    if not getattr(instance, '_password_changed_for_push', False):
        return

    if not hasattr(instance, 'teacher_profile'):
        return

    notify_teacher_password_changed(instance)
