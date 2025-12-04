from django.core.management.base import BaseCommand
from marks.models import Student, Subject, ExamType, Exam, GradeScale
from datetime import date, timedelta
import random


class Command(BaseCommand):
    help = 'Load sample data for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample data...')
        
        # Create Students
        students = [
            Student.objects.create(name='Ahmed Ali', roll='101', class_name='Class 10'),
            Student.objects.create(name='Fatima Rahman', roll='102', class_name='Class 10'),
            Student.objects.create(name='Mohammad Hassan', roll='103', class_name='Class 10'),
            Student.objects.create(name='Ayesha Khan', roll='104', class_name='Class 10'),
            Student.objects.create(name='Omar Faruk', roll='105', class_name='Class 10'),
        ]
        self.stdout.write(self.style.SUCCESS(f'Created {len(students)} students'))
        
        # Create Subjects
        subjects = [
            Subject.objects.create(name='Mathematics'),
            Subject.objects.create(name='Physics'),
            Subject.objects.create(name='Chemistry'),
            Subject.objects.create(name='Biology'),
            Subject.objects.create(name='English'),
        ]
        self.stdout.write(self.style.SUCCESS(f'Created {len(subjects)} subjects'))
        
        # Create Exam Types
        exam_types = [
            ExamType.objects.create(name='MCQ'),
            ExamType.objects.create(name='Creative'),
            ExamType.objects.create(name='Direct'),
            ExamType.objects.create(name='CQ'),
        ]
        self.stdout.write(self.style.SUCCESS(f'Created {len(exam_types)} exam types'))
        
        # Create Sample Exams
        exam_count = 0
        base_date = date.today() - timedelta(days=90)
        
        for student in students:
            for subject in subjects:
                # Create 3-5 exams per student per subject
                num_exams = random.randint(3, 5)
                for i in range(num_exams):
                    exam_type = random.choice(exam_types)
                    total_marks = random.choice([50, 75, 100])
                    
                    # Generate realistic marks based on student performance
                    if student.name == 'Ahmed Ali':
                        percentage = random.uniform(85, 100)
                    elif student.name == 'Fatima Rahman':
                        percentage = random.uniform(75, 95)
                    elif student.name == 'Mohammad Hassan':
                        percentage = random.uniform(65, 85)
                    elif student.name == 'Ayesha Khan':
                        percentage = random.uniform(70, 90)
                    else:
                        percentage = random.uniform(60, 80)
                    
                    mark_obtained = (percentage / 100) * total_marks
                    exam_date = base_date + timedelta(days=random.randint(0, 90))
                    
                    Exam.objects.create(
                        student=student,
                        subject=subject,
                        exam_type=exam_type,
                        date=exam_date,
                        chapter=f'Chapter {random.randint(1, 10)}',
                        total_marks=total_marks,
                        mark_obtained=round(mark_obtained, 2)
                    )
                    exam_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Created {exam_count} sample exams'))
        self.stdout.write(self.style.SUCCESS('Sample data loaded successfully!'))
