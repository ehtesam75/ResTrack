from django.core.management.base import BaseCommand
from marks.models import Exam


class Command(BaseCommand):
    help = 'Reset and assign exam IDs starting from 1'

    def handle(self, *args, **options):
        # Get all exams ordered by date and id
        exams = Exam.objects.all().order_by('date', 'id')
        
        exam_id_counter = 1
        processed_groups = set()
        
        for exam in exams:
            if exam.group_id:
                # Bulk entry - check if group already processed
                if exam.group_id not in processed_groups:
                    # Assign same exam_id to all exams in this group
                    Exam.objects.filter(group_id=exam.group_id).update(exam_id=exam_id_counter)
                    processed_groups.add(exam.group_id)
                    exam_id_counter += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Assigned Exam ID {exam_id_counter-1} to group {exam.group_id}')
                    )
            else:
                # Single entry
                exam.exam_id = exam_id_counter
                exam.save(update_fields=['exam_id'])
                exam_id_counter += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Assigned Exam ID {exam_id_counter-1} to exam #{exam.id}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully reset exam IDs! Total exams: {exam_id_counter-1}')
        )
