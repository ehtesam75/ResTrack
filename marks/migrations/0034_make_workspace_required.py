"""
0034_make_workspace_required
============================

Flips the ``workspace`` FK on the 8 teacher-scoped models from ``null=True`` to
``null=False``. Will hard-fail the deploy if ``0033_backfill_default_workspace``
missed any rows — which is exactly what we want, rather than silently shipping
orphaned rows.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0033_backfill_default_workspace'),
    ]

    operations = [
        migrations.AlterField(
            model_name='student',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this student belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='students',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='subject',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this subject belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='subjects',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='examtype',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this exam type belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exam_types',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='exam',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this exam belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exams',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='examquestionpaper',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this question paper belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exam_question_papers',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='pointsspent',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this points-spent entry belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='points_spent_records',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='pointtransaction',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this point transaction belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='point_transactions',
                to='marks.workspace',
            ),
        ),
        migrations.AlterField(
            model_name='examcenterexam',
            name='workspace',
            field=models.ForeignKey(
                help_text='Workspace this exam belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='exam_center_exams',
                to='marks.workspace',
            ),
        ),
    ]