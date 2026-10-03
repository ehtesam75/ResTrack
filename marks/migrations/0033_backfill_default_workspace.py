"""
0033_backfill_default_workspace
===============================

Idempotent data migration that creates one ``Workspace`` per teacher (slug_number=1)
and assigns every existing teacher-scoped row to it.

Safe to re-run: ``get_or_create`` + the ``workspace__isnull=True`` filter together
mean a second invocation is a no-op.

Rows whose ``teacher`` is NULL are swept up at the end and logged; they remain
orphaned after this migration, which means they are also invisible to the app
once 0034 flips the FK to NOT NULL. That is the desired behaviour — better
than guessing an owner.
"""

from django.db import migrations
from django.db.models import Q


def forwards(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    Workspace = apps.get_model('marks', 'Workspace')
    TeacherProfile = apps.get_model('marks', 'TeacherProfile')
    GuestTeacherAccount = apps.get_model('marks', 'GuestTeacherAccount')

    models_to_backfill = [
        'Student',
        'Subject',
        'ExamType',
        'Exam',
        'ExamQuestionPaper',
        'PointsSpent',
        'PointTransaction',
        'ExamCenterExam',
    ]
    historical_models = {name: apps.get_model('marks', name) for name in models_to_backfill}

    # Every user who owns any teacher-scoped row, or has a TeacherProfile.
    teacher_ids = set(
        TeacherProfile.objects.values_list('user_id', flat=True)
    )
    for name, model in historical_models.items():
        teacher_ids |= set(
            model.objects
            .exclude(teacher__isnull=True)
            .values_list('teacher_id', flat=True)
            .distinct()
        )

    # Also include teachers that already have a Workspace but no rows yet (no-op for them).
    teacher_ids |= set(Workspace.objects.values_list('teacher_id', flat=True).distinct())

    orphaned_logs = []
    for tid in teacher_ids:
        ws, created = Workspace.objects.get_or_create(
            teacher_id=tid,
            slug_number=1,
            defaults={
                'name': 'Default Workspace',
                'description': 'Your original ResTrack data.',
            },
        )

        for name, model in historical_models.items():
            updated = model.objects.filter(
                teacher_id=tid,
                workspace__isnull=True,
            ).update(workspace=ws)
            if updated and created:
                # Only log on first creation to avoid duplicate noise on re-runs.
                pass

    # Pin guest accounts to their teacher's default workspace (if the teacher has one).
    for ga in GuestTeacherAccount.objects.filter(workspace__isnull=True):
        default_ws = Workspace.objects.filter(teacher_id=ga.teacher_id, slug_number=1).first()
        if default_ws:
            ga.workspace = default_ws
            ga.save(update_fields=['workspace'])

    # Sweep orphaned rows (teacher IS NULL) — leave them with workspace=NULL
    # so 0034 will hard-fail loudly rather than silently misassigning.
    for name, model in historical_models.items():
        qs = model.objects.filter(teacher__isnull=True, workspace__isnull=True)
        count = qs.count()
        if count:
            orphaned_logs.append(f"{name}: {count} orphaned rows left untouched")


def backwards(apps, schema_editor):
    Workspace = apps.get_model('marks', 'Workspace')
    GuestTeacherAccount = apps.get_model('marks', 'GuestTeacherAccount')

    models_to_null = [
        'Student', 'Subject', 'ExamType', 'Exam', 'ExamQuestionPaper',
        'PointsSpent', 'PointTransaction', 'ExamCenterExam',
    ]
    for name in models_to_null:
        apps.get_model('marks', name).objects.all().update(workspace=None)

    GuestTeacherAccount.objects.all().update(workspace=None)
    Workspace.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0032_add_workspace_model'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards, atomic=True),
    ]