from django.core.management.base import BaseCommand
from django.db.models import Max
from marks.models import Exam


class Command(BaseCommand):
    help = 'Fix exam IDs for exams with None values'

    def handle(self, *args, **options):
        # Get exams without exam_id
        exams_without_id = Exam.objects.filter(exam_id__isnull=True).order_by('date', 'id')
        
        if not exams_without_id.exists():
            self.stdout.write(self.style.SUCCESS('All exams already have exam_ids!'))
            return
        
        # Get current max exam_id
        max_id = Exam.objects.aggregate(Max('exam_id'))['exam_id__max'] or 0
        
        fixed_count = 0
        for exam in exams_without_id:
            if exam.group_id:
                # Check if group already has an exam_id
                existing = Exam.objects.filter(
                    group_id=exam.group_id,
                    exam_id__isnull=False
                ).first()
                if existing:
                    exam.exam_id = existing.exam_id
                else:
                    max_id += 1
                    exam.exam_id = max_id
                    # Update all in group
                    Exam.objects.filter(group_id=exam.group_id).update(exam_id=max_id)
            else:
                max_id += 1
                exam.exam_id = max_id
            
            exam.save(update_fields=['exam_id'])
            fixed_count += 1
            self.stdout.write(f'Fixed exam #{exam.id} -> exam_id {exam.exam_id}')
        
        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully fixed {fixed_count} exam(s)!')
        )
