from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0029_remove_plaintext_password_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exam',
            name='class_number',
            field=models.CharField(default='1', help_text='Class name', max_length=50),
        ),
        migrations.AlterField(
            model_name='examcenterexam',
            name='class_number',
            field=models.CharField(help_text='Class name', max_length=50),
        ),
    ]
