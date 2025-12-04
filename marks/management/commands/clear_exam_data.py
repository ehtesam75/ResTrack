from django.core.management.base import BaseCommand
from marks.models import Student, Subject, ExamType, Exam, GradeScale, LifetimePoints


class Command(BaseCommand):
    help = 'Clear all exam data from database'

    def handle(self, *args, **options):
        self.stdout.write('='*80)
        self.stdout.write('CLEARING EXAM DATA')
        self.stdout.write('='*80)
        
        # Count before deletion
        exam_count = Exam.objects.count()
        student_count = Student.objects.count()
        subject_count = Subject.objects.count()
        exam_type_count = ExamType.objects.count()
        lifetime_points_count = LifetimePoints.objects.count()
        
        self.stdout.write(f'\nData to be deleted:')
        self.stdout.write(f'  - {exam_count} Exam records')
        self.stdout.write(f'  - {student_count} Students')
        self.stdout.write(f'  - {subject_count} Subjects')
        self.stdout.write(f'  - {exam_type_count} Exam Types')
        self.stdout.write(f'  - {lifetime_points_count} Lifetime Points records')
        
        # Delete exam data
        Exam.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'\n✓ Deleted {exam_count} exam records'))
        
        # Delete lifetime points
        LifetimePoints.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {lifetime_points_count} lifetime points records'))
        
        # Delete students
        Student.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {student_count} students'))
        
        # Delete subjects
        Subject.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {subject_count} subjects'))
        
        # Delete exam types
        ExamType.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'✓ Deleted {exam_type_count} exam types'))
        
        # Keep grade scales (these are configuration, not data)
        self.stdout.write(self.style.WARNING(f'\nℹ Grade scales kept intact (configuration data)'))
        
        self.stdout.write('\n' + '='*80)
        self.stdout.write(self.style.SUCCESS('DATABASE CLEARED SUCCESSFULLY!'))
        self.stdout.write('='*80)
        self.stdout.write('\nYou can now add your own exam data through:')
        self.stdout.write('  - The admin panel: http://127.0.0.1:8000/admin/')
        self.stdout.write('  - The "Add Exam" page: http://127.0.0.1:8000/exams/add/')
        self.stdout.write('')
