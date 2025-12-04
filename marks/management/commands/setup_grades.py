from django.core.management.base import BaseCommand
from marks.models import GradeScale


class Command(BaseCommand):
    help = 'Setup default grade scales'

    def handle(self, *args, **options):
        # Clear existing grade scales
        GradeScale.objects.all().delete()
        
        # Create default grade scales
        # Note: These are for display/chart colors only. Actual grading logic
        # is hardcoded in Exam model with different thresholds for CQ vs MCQ.
        grade_scales = [
            {
                'grade_name': 'Superb',
                'color_code': '#A7F3D0',  # Emerald-200 (darker green)
                'points': 20
            },
            {
                'grade_name': 'Good',
                'color_code': '#D1FAE5',  # Green-100 (lighter green)
                'points': 15
            },
            {
                'grade_name': 'Average',
                'color_code': '#FEF08A',  # Yellow-200 (very light yellow)
                'points': 0
            },
            {
                'grade_name': 'Poor',
                'color_code': '#FDE68A',  # Amber-200 (very light amber)
                'points': -10
            },
            {
                'grade_name': 'Fail',
                'color_code': '#FECACA',  # Red-200 (very light red)
                'points': -15
            },
            {
                'grade_name': 'Horrible',
                'color_code': '#FCA5A5',  # Red-300 (light red)
                'points': -20
            },
        ]
        
        for grade_data in grade_scales:
            GradeScale.objects.create(**grade_data)
            self.stdout.write(
                self.style.SUCCESS(f'Created grade scale: {grade_data["grade_name"]}')
            )
        
        self.stdout.write(self.style.SUCCESS('Successfully setup grade scales!'))
