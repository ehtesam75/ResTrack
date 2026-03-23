from django.db import migrations


def force_rotate_exposed_passwords(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    StudentProfile = apps.get_model('marks', 'StudentProfile')
    GuestTeacherAccount = apps.get_model('marks', 'GuestTeacherAccount')

    impacted_user_ids = set(
        StudentProfile.objects.exclude(raw_password__isnull=True)
        .exclude(raw_password='')
        .values_list('user_id', flat=True)
    )
    impacted_user_ids.update(
        GuestTeacherAccount.objects.exclude(raw_password__isnull=True)
        .exclude(raw_password='')
        .values_list('guest_user_id', flat=True)
    )

    for user in User.objects.filter(id__in=impacted_user_ids):
        user.set_unusable_password()
        user.save(update_fields=['password'])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('marks', '0028_add_guest_teacher_account'),
    ]

    operations = [
        migrations.RunPython(force_rotate_exposed_passwords, noop_reverse),
        migrations.RemoveField(
            model_name='studentprofile',
            name='raw_password',
        ),
        migrations.RemoveField(
            model_name='guestteacheraccount',
            name='raw_password',
        ),
    ]
