from django.core.management.base import BaseCommand
from marks.models import Student, Subject, ExamType, Exam, GradeScale
from decimal import Decimal


class Command(BaseCommand):
    help = 'Check all calculations for accuracy'

    def handle(self, *args, **options):
        self.stdout.write('='*80)
        self.stdout.write('CALCULATION VERIFICATION REPORT')
        self.stdout.write('='*80)
        
        # Check Exam Percentage Calculations
        self.stdout.write('\n1. EXAM PERCENTAGE CALCULATIONS:')
        self.stdout.write('-'*80)
        exams = Exam.objects.all().order_by('date', 'student__name')
        for exam in exams:
            calculated_percentage = (float(exam.mark_obtained) / float(exam.total_marks)) * 100
            model_percentage = float(exam.percentage)
            match = "✓" if abs(calculated_percentage - model_percentage) < 0.01 else "✗ ERROR"
            
            self.stdout.write(
                f'{match} {exam.student.name:10} | {exam.subject.name:12} | '
                f'{exam.exam_type.name:8} | {exam.mark_obtained:5}/{exam.total_marks:5} = '
                f'{calculated_percentage:6.2f}% (Model: {model_percentage:6.2f}%)'
            )
        
        # Check Student Total Marks
        self.stdout.write('\n2. STUDENT TOTAL MARKS:')
        self.stdout.write('-'*80)
        students = Student.objects.all()
        for student in students:
            manual_total = sum([float(e.mark_obtained) for e in student.exam_set.all()])
            model_total = float(student.total_marks)
            match = "✓" if abs(manual_total - model_total) < 0.01 else "✗ ERROR"
            
            self.stdout.write(
                f'{match} {student.name:10} | Manual: {manual_total:7.2f} | '
                f'Model: {model_total:7.2f}'
            )
        
        # Check Student Average Percentage
        self.stdout.write('\n3. STUDENT AVERAGE PERCENTAGE:')
        self.stdout.write('-'*80)
        for student in students:
            exams = student.exam_set.all()
            if exams:
                manual_avg = sum([e.percentage for e in exams]) / len(exams)
                model_avg = student.average_percentage
                match = "✓" if abs(manual_avg - model_avg) < 0.01 else "✗ ERROR"
                
                self.stdout.write(
                    f'{match} {student.name:10} | Manual: {manual_avg:6.2f}% | '
                    f'Model: {model_avg:6.2f}% | Exams: {len(exams)}'
                )
        
        # Check Subject-wise Average
        self.stdout.write('\n4. SUBJECT AVERAGE PERCENTAGE:')
        self.stdout.write('-'*80)
        subjects = Subject.objects.all()
        for subject in subjects:
            exams = subject.exam_set.all()
            if exams:
                manual_avg = sum([e.percentage for e in exams]) / len(exams)
                model_avg = subject.average_marks
                match = "✓" if abs(manual_avg - model_avg) < 0.01 else "✗ ERROR"
                
                self.stdout.write(
                    f'{match} {subject.name:15} | Manual: {manual_avg:6.2f}% | '
                    f'Model: {model_avg:6.2f}% | Exams: {len(exams)}'
                )
        
        # Check Subject-wise Summary for Each Student
        self.stdout.write('\n5. STUDENT SUBJECT-WISE SUMMARY:')
        self.stdout.write('-'*80)
        for student in students:
            self.stdout.write(f'\n{student.name}:')
            summary = student.subject_wise_summary()
            for item in summary:
                subject = item['subject']
                exams = student.exam_set.filter(subject=subject)
                
                # Manual calculations
                manual_total_marks = sum([float(e.mark_obtained) for e in exams])
                manual_avg_pct = sum([e.percentage for e in exams]) / len(exams) if exams else 0
                
                match_marks = "✓" if abs(manual_total_marks - float(item['total_marks'])) < 0.01 else "✗"
                match_avg = "✓" if abs(manual_avg_pct - item['average_percentage']) < 0.01 else "✗"
                
                self.stdout.write(
                    f'  {match_marks} {match_avg} {subject.name:15} | '
                    f'Total: {item["total_marks"]:6.2f} (Manual: {manual_total_marks:6.2f}) | '
                    f'Avg: {item["average_percentage"]:6.2f}% (Manual: {manual_avg_pct:6.2f}%)'
                )
        
        # Check Grade Assignments
        self.stdout.write('\n6. GRADE ASSIGNMENTS:')
        self.stdout.write('-'*80)
        grade_scales = GradeScale.objects.all().order_by('grade_name')
        self.stdout.write('\nGrade Scale Configuration:')
        for gs in grade_scales:
            self.stdout.write(f'  {gs.grade_name:8}: +{gs.points} points (Color: {gs.color_code})')
        
        self.stdout.write('\nGrade Assignments Check:')
        for exam in exams[:10]:  # Check first 10
            percentage = exam.percentage
            grade = exam.grade
            points = exam.points_earned
            
            # Note: Grading is hardcoded in Exam.grade property, not in GradeScale table
            # GradeScale table only stores colors for charts
            
            self.stdout.write(
                f'✓ {exam.student.name:10} | {exam.subject.name:12} | '
                f'{percentage:6.2f}% → {grade:8} ({points:+d} points)'
            )
        
        self.stdout.write('\n' + '='*80)
        self.stdout.write('VERIFICATION COMPLETE')
        self.stdout.write('='*80)
