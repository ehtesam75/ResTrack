
from django.db.models.signals import pre_save, post_delete, post_save
from django.dispatch import receiver
from django.db.models import Max
from .models import Exam

@receiver(post_save, sender=Exam)
def recalculate_points_on_save(sender, instance, **kwargs):
    """Recalculate student's lifetime points after exam save."""
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
                # Get max exam_id and increment
                max_id = Exam.objects.aggregate(Max('exam_id'))['exam_id__max']
                instance.exam_id = (max_id or 0) + 1
        else:
            # Single entry, get new exam_id
            max_id = Exam.objects.aggregate(Max('exam_id'))['exam_id__max']
            instance.exam_id = (max_id or 0) + 1


@receiver(post_delete, sender=Exam)
def recalculate_points_on_delete(sender, instance, **kwargs):
    """Recalculate student's lifetime points after exam deletion"""
    if instance.student:
        instance.student.recalculate_lifetime_points()
