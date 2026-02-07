from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import cloudinary.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('marks', '0018_migrate_points_spent_to_transactions'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExamQuestionPaper',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('exam_id', models.IntegerField(help_text='Unique exam identifier this question paper belongs to')),
                ('question_pdf', cloudinary.models.CloudinaryField(max_length=255, verbose_name='raw')),
                ('uploaded_at', models.DateTimeField(auto_now=True)),
                ('teacher', models.ForeignKey(help_text='Teacher who owns this exam', on_delete=django.db.models.deletion.CASCADE, related_name='exam_question_papers', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Exam Question Paper',
                'verbose_name_plural': 'Exam Question Papers',
                'ordering': ['-exam_id'],
                'unique_together': {('exam_id', 'teacher')},
            },
        ),
    ]
