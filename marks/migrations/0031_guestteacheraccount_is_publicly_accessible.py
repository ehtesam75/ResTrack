from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0030_make_class_fields_flexible_text'),
    ]

    operations = [
        migrations.AddField(
            model_name='guestteacheraccount',
            name='is_publicly_accessible',
            field=models.BooleanField(default=False),
        ),
    ]
