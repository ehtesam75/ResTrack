"""
0035_workspace_unique_constraints
==================================

Swaps the ``ExamQuestionPaper`` uniqueness from per-teacher to per-workspace.
Two workspaces may now each have their own ``exam_id=1`` question paper without
collision.

Sequenced last so it runs against already-backfilled data (0033 must have
populated ``workspace`` on every row by the time this fires).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0034_make_workspace_required'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='examquestionpaper',
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name='examquestionpaper',
            constraint=models.UniqueConstraint(
                fields=('exam_id', 'workspace'),
                name='unique_exam_question_paper_per_workspace',
            ),
        ),
    ]