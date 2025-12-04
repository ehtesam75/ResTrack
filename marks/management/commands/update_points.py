from django.core.management.base import BaseCommand
from django.db.models import Sum
from marks.models import LifetimePoints, PointsSpent


class Command(BaseCommand):
    help = 'Recalculate points_spent for all students'

    def handle(self, *args, **options):
        for lifetime_points in LifetimePoints.objects.all():
            total_spent = PointsSpent.objects.filter(
                student=lifetime_points.student
            ).aggregate(total=Sum('points_spent'))['total'] or 0
            
            lifetime_points.points_spent = total_spent
            lifetime_points.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated {lifetime_points.student.name}: {total_spent} points spent'
                )
            )
        
        self.stdout.write(self.style.SUCCESS('All points updated successfully!'))
