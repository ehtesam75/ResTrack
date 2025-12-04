from django.core.management.base import BaseCommand
from marks.models import Student


class Command(BaseCommand):
    help = 'Recalculate lifetime points for all students based on current exam results'

    def handle(self, *args, **options):
        students = Student.objects.all()
        
        for student in students:
            student.recalculate_lifetime_points()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Recalculated points for {student.name}: {student.lifetimepoints.total_points if hasattr(student, "lifetimepoints") else 0} points'
                )
            )
        
        self.stdout.write(self.style.SUCCESS(f'\nSuccessfully recalculated lifetime points for {students.count()} students!'))
