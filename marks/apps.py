from django.apps import AppConfig


class MarksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marks'

    def ready(self):
        import marks.signals
