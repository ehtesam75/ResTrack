from django.core.management.base import BaseCommand
from marks.models import Student, PointTransaction


class Command(BaseCommand):
    help = 'Backfill monthly winner transactions: replace grouped entries with individual per-month entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without making any modifications',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — no changes will be made\n'))

        # Show current grouped monthly_win transactions
        old_txns = PointTransaction.objects.filter(transaction_type='monthly_win')
        self.stdout.write(f'Found {old_txns.count()} existing monthly_win transaction(s):')
        for t in old_txns:
            self.stdout.write(f'  {t.date}  {t.student.name:<20}  {t.points_change:>+4} pts  "{t.description}"')

        if not dry_run:
            self.stdout.write('\nRecalculating all students...\n')

        students = Student.objects.all()
        for student in students:
            if not dry_run:
                student.recalculate_lifetime_points()

            winning_months = student.get_monthly_win_months()
            if winning_months:
                self.stdout.write(f'  {student.name}: {len(winning_months)} monthly win(s)')
                for y, m in sorted(winning_months):
                    import calendar
                    self.stdout.write(f'    → {calendar.month_name[m]} {y}')

        if not dry_run:
            new_txns = PointTransaction.objects.filter(transaction_type='monthly_win')
            self.stdout.write(f'\nAfter backfill: {new_txns.count()} monthly_win transaction(s):')
            for t in new_txns.order_by('student__first_name', 'date'):
                self.stdout.write(f'  {t.date}  {t.student.name:<20}  {t.points_change:>+4} pts  "{t.description}"')

            self.stdout.write(self.style.SUCCESS('\nBackfill complete!'))
        else:
            self.stdout.write(self.style.WARNING('\nDry run finished. Use without --dry-run to apply changes.'))
