from django.core.management.base import BaseCommand
from marks.models import Student


class Command(BaseCommand):
    help = 'Recalculate lifetime points for all students'

    def handle(self, *args, **options):
        students = Student.objects.all()
        count = students.count()
        
        self.stdout.write(f'Recalculating points for {count} students...')
        
        for student in students:
            student.recalculate_lifetime_points()
            self.stdout.write(f'  ✓ {student.name}')
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully recalculated points for {count} students!'))
