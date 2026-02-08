from django.db import models
from django.db.models import Avg, Sum, Count, Q
from django.contrib.auth.models import User
from cloudinary.models import CloudinaryField


class TeacherProfile(models.Model):
    """Profile for teacher accounts"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    institution = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Teacher: {self.user.get_full_name() or self.user.username}"

    class Meta:
        verbose_name = "Teacher Profile"
        verbose_name_plural = "Teacher Profiles"


class StudentProfile(models.Model):
    """Profile linking a user account to a student record"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    student = models.OneToOneField('Student', on_delete=models.CASCADE, related_name='user_profile')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_students')
    raw_password = models.CharField(max_length=128, blank=True, null=True, help_text="Plain-text password for teacher reference")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Student Account: {self.student.name}"

    class Meta:
        verbose_name = "Student Profile"
        verbose_name_plural = "Student Profiles"


class Student(models.Model):
    """Model representing a student in the tracking system"""
    first_name = models.CharField(max_length=10, help_text="First name (max 10 characters)")
    last_name = models.CharField(max_length=10, blank=True, null=True, help_text="Last name (max 10 characters)")
    roll = models.CharField(max_length=50, blank=True, null=True)
    class_name = models.CharField(max_length=100, blank=True, null=True)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='students',
        null=True,
        blank=True,
        help_text="Teacher who owns this student"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def name(self):
        """Full name property for backward compatibility"""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name

    @property
    def display_name(self):
        """Display name in format: First name (username)"""
        username = ""
        try:
            if hasattr(self, 'user_profile') and self.user_profile.user:
                username = self.user_profile.user.username
        except:
            # Fallback if user_profile doesn't exist or user is None
            pass
        return f"{self.first_name} ({username})"

    def __str__(self):
        return self.name

    @staticmethod
    def _count_unique_exams(queryset):
        """
        Helper method to count unique exams in a queryset.
        Returns total unique exam_id only.
        """
        return queryset.values('exam_id').distinct().count()

    def get_monthly_win_months(self):
        """
        Get the list of (year, month) tuples where this student ranked #1 (excluding current month).
        Handles ties: if multiple students have same average score AND same total marks,
        all of them get credit for the monthly win.
        
        Returns:
            list of (year, month) tuples where student ranked first
        """
        from datetime import date
        current_year = date.today().year
        current_month = date.today().month
        
        winning_months = []
        exam_dates = Exam.objects.values_list('date', flat=True).distinct()
        months_set = set()
        
        for exam_date in exam_dates:
            if exam_date:
                # Only count months that have fully passed
                if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                    months_set.add((exam_date.year, exam_date.month))
        
        for year, month in months_set:
            # Get total unique exams conducted in this month
            total_month_exams = Exam.objects.filter(
                date__year=year,
                date__month=month
            ).values('exam_id').distinct().count()
            
            # Get all students who had exams in this month
            students_in_month = Student.objects.filter(
                exam__date__year=year,
                exam__date__month=month
            ).distinct()
            
            month_rankings = []
            for s in students_in_month:
                month_exams = s.exam_set.filter(date__year=year, date__month=month)
                student_exams_count = month_exams.values('exam_id').distinct().count()
                
                # Check eligibility: ≥40% attendance AND ≥3 exams
                attendance_percentage = (student_exams_count / total_month_exams * 100) if total_month_exams > 0 else 0
                is_eligible = (attendance_percentage >= 40) and (student_exams_count >= 3)
                
                if is_eligible:
                    total_marks = sum(float(e.mark_obtained) for e in month_exams)
                    total_possible = sum(float(e.total_marks) for e in month_exams)
                    avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
                    
                    month_rankings.append({
                        'student_id': s.id,
                        'average_percentage': avg_percentage,
                        'total_marks': total_marks,
                    })
            
            # Sort by average score (primary), then total marks (tie-breaker)
            month_rankings.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
            
            # Check if this student is in the top position (could be tied)
            if month_rankings:
                top_avg = month_rankings[0]['average_percentage']
                top_total = month_rankings[0]['total_marks']
                
                # Find this student in rankings
                for ranking in month_rankings:
                    if ranking['student_id'] == self.id:
                        # If this student has same avg AND same total marks as top, count it as a win
                        if (abs(ranking['average_percentage'] - top_avg) < 0.01 and
                            ranking['total_marks'] == top_total):
                            winning_months.append((year, month))
                        break
        
        return winning_months

    def calculate_monthly_wins(self):
        """
        Calculate how many months this student ranked #1 (excluding current month).
        Handles ties: if multiple students have same average score AND same total marks,
        all of them get credit for the monthly win.
        
        Returns:
            int: Number of months where student ranked first
        """
        return len(self.get_monthly_win_months())

    @property
    def total_marks(self):
        """Calculate total marks obtained by the student across all exams"""
        return self.exam_set.aggregate(total=Sum('mark_obtained'))['total'] or 0

    @property
    def total_exams(self):
        """Count total unique exams (grouped bulk entries count as 1)"""
        return self._count_unique_exams(self.exam_set.all())

    @property
    def average_percentage(self):
        """Calculate weighted average percentage across all exams"""
        exams = self.exam_set.all()
        if not exams.exists():
            return 0
            
        total_marks_obtained = sum(float(exam.mark_obtained) for exam in exams)
        total_possible_marks = sum(float(exam.total_marks) for exam in exams)
        
        if total_possible_marks == 0:
            return 0
            
        return (total_marks_obtained * 100) / total_possible_marks

    @property
    def rank(self):
        """
        Calculate student's rank among students belonging to the same teacher.
        
        Ranking Rules:
        1. Primary: Ranked by average score (average_percentage)
        2. Tie-breaker: If average scores are equal, rank by total_marks
        3. If both are equal, students share the same rank
        """
        # Only rank among students of the same teacher
        students = Student.objects.filter(teacher=self.teacher)
        
        # Sort by average score (primary), then total marks (tie-breaker), both descending
        ranked_students = sorted(
            students,
            key=lambda s: (s.average_percentage, s.total_marks),
            reverse=True
        )
        
        # Assign ranks with tie handling
        current_rank = 1
        previous_score = None
        previous_marks = None
        
        for idx, student in enumerate(ranked_students):
            # If this student has the same score AND marks as previous, give same rank
            if (previous_score is not None and 
                abs(student.average_percentage - previous_score) < 0.01 and  # Same score
                student.total_marks == previous_marks):  # Same marks
                # Keep current_rank (shared rank)
                pass
            else:
                # Different score or marks, update rank to current position
                current_rank = idx + 1
            
            if student.id == self.id:
                return current_rank
            
            previous_score = student.average_percentage
            previous_marks = student.total_marks
        
        return None

    def subject_wise_summary(self):
        """
        Get performance summary for each subject the student has taken.
        
        Returns:
            list: List of dicts containing subject performance data
        """
        summary = []
        subjects = Subject.objects.filter(exam__student=self).distinct()
        
        for subject in subjects:
            exams = self.exam_set.filter(subject=subject)
            
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (
                (total_marks_obtained * 100 / total_possible_marks) 
                if total_possible_marks > 0 else 0
            )
            
            summary.append({
                'subject': subject,
                'total_marks': total_marks_obtained,
                'exam_count': self._count_unique_exams(exams),
                'average_percentage': avg_percentage,
                'rank': self.get_subject_rank(subject)
            })
        
        return summary
    def exam_type_summary(self):
        """
        Get performance summary for each exam type the student has taken.
        
        Returns:
            list: List of dicts containing exam type performance data
        """
        summary = []
        exam_types = ExamType.objects.filter(exam__student=self).distinct()
        
        for exam_type in exam_types:
            exams = self.exam_set.filter(exam_type=exam_type)
            
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (
                (total_marks_obtained * 100 / total_possible_marks) 
                if total_possible_marks > 0 else 0
            )
            
            summary.append({
                'exam_type': exam_type,
                'total_marks': total_marks_obtained,
                'exam_count': self._count_unique_exams(exams),
                'average_percentage': avg_percentage
            })
        
        return summary

    def grade_frequency(self):
        """
        Count occurrences of each grade achieved by the student.
        
        Returns:
            dict: Grade names mapped to their frequency counts
        """
        from collections import Counter
        grades = [exam.grade for exam in self.exam_set.all()]
        return dict(Counter(grades))

    def get_subject_rank(self, subject):
        """
        Calculate student's rank in a specific subject.
        
        Args:
            subject: Subject instance to calculate rank for
            
        Returns:
            int or None: Rank position (1-indexed) or None if not applicable
        """
        students_in_subject = Student.objects.filter(exam__subject=subject).distinct()
        
        student_averages = []
        for student in students_in_subject:
            exams = student.exam_set.filter(subject=subject)
            if exams.exists():
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (
                    (total_marks_obtained * 100 / total_possible_marks) 
                    if total_possible_marks > 0 else 0
                )
                student_averages.append({
                    'student_id': student.id,
                    'avg_percentage': avg_percentage
                })
        
        student_averages.sort(key=lambda x: x['avg_percentage'], reverse=True)
        
        for idx, item in enumerate(student_averages, 1):
            if item['student_id'] == self.id:
                return idx
        
        return None

    def recalculate_lifetime_points(self):
        """
        Recalculate and update lifetime points based on all exam results.
        Includes 40-point bonus for each monthly win.
        Also creates/updates PointTransaction records for exam performance.
        Called automatically when an exam is saved.
        """
        from django.db.models import Sum

        # Clear existing exam-related transactions to avoid duplicates
        PointTransaction.objects.filter(
            student=self,
            transaction_type__in=['exam_bonus', 'exam_penalty', 'monthly_win']
        ).delete()

        # Calculate points from individual exams and create transactions
        exam_points = 0
        for exam in self.exam_set.select_related('exam_type', 'teacher').all():
            points_earned = exam.points_earned
            exam_points += points_earned

            # Create transaction for exam performance
            if points_earned != 0:
                transaction_type = 'exam_bonus' if points_earned > 0 else 'exam_penalty'
                description = f"{exam.exam_type.name} - {exam.subject.name}: {exam.percentage:.1f}% ({exam.grade})"

                PointTransaction.objects.create(
                    student=self,
                    teacher=exam.teacher,
                    transaction_type=transaction_type,
                    points_change=points_earned,
                    description=description,
                    date=exam.date,
                    exam=exam
                )

        # Calculate monthly wins bonus and create individual transactions per winning month
        import calendar
        from datetime import date
        winning_months = self.get_monthly_win_months()
        bonus_points = len(winning_months) * 40

        # Create one transaction per winning month
        for win_year, win_month in winning_months:
            month_name = calendar.month_name[win_month]
            # Date the transaction on the 1st of the following month
            if win_month == 12:
                transaction_date = date(win_year + 1, 1, 1)
            else:
                transaction_date = date(win_year, win_month + 1, 1)

            PointTransaction.objects.create(
                student=self,
                teacher=self.teacher,
                transaction_type='monthly_win',
                points_change=40,
                description=f"Monthly winner \u2013 {month_name} {win_year}",
                date=transaction_date,
                exam=None
            )

        # Total points = exam points + monthly wins bonus
        total_points = exam_points + bonus_points

        # Get or create LifetimePoints record
        lifetime_points, created = LifetimePoints.objects.get_or_create(
            student=self,
            defaults={'points_earned': total_points, 'points_spent': 0}
        )

        # Update points if record already exists
        if not created:
            lifetime_points.points_earned = total_points
            lifetime_points.save()
        
class Subject(models.Model):
    """Model representing a subject/course"""
    name = models.CharField(max_length=200)
    short_name = models.CharField(max_length=10, blank=True, null=True, help_text="Short name/abbreviation (max 10 characters)")
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subjects',
        null=True,
        blank=True,
        help_text="Teacher who owns this subject"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def average_marks(self):
        """
        Calculate weighted average percentage for this subject across all students.
        
        Returns:
            float: Average percentage rounded to 2 decimal places
        """
        exams = self.exam_set.all()
        if not exams.exists():
            return 0
            
        total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
        total_possible_marks = sum(float(e.total_marks) for e in exams)
        
        if total_possible_marks == 0:
            return 0
            
        return (total_marks_obtained * 100 / total_possible_marks)

    def best_student(self):
        """
        Get the best performing student in this subject based on average percentage.
        
        Returns:
            Student or None: Student with highest average percentage
        """
        students = Student.objects.filter(exam__subject=self).distinct()
        
        if not students.exists():
            return None
        
        student_averages = []
        for student in students:
            student_exams = student.exam_set.filter(subject=self)
            if student_exams.exists():
                total_marks_obtained = sum(float(e.mark_obtained) for e in student_exams)
                total_possible_marks = sum(float(e.total_marks) for e in student_exams)
                
                if total_possible_marks > 0:
                    avg_percentage = (total_marks_obtained * 100 / total_possible_marks)
                    student_averages.append({
                        'student': student,
                        'avg_percentage': avg_percentage
                    })
        
        if not student_averages:
            return None
        
        student_averages.sort(key=lambda x: x['avg_percentage'], reverse=True)
        return student_averages[0]['student']


class ExamType(models.Model):
    """Model representing a type/category of exam (e.g., MCQ, CQ, Midterm)"""
    name = models.CharField(max_length=100)
    teacher = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='exam_types',
        null=True,
        blank=True,
        help_text="Teacher who owns this exam type"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
class GradeScale(models.Model):
    """Model defining grading scale and point system"""
    grade_name = models.CharField(max_length=50)
    color_code = models.CharField(max_length=7, default='#000000')
    points = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['grade_name']

    def __str__(self):
        return f"{self.grade_name} ({self.points:+d} points)"


class ExamQuestionPaper(models.Model):
    """
    Model linking a Question Paper PDF to an Exam ID (one per exam).
    The question paper is shared across all student records for the same exam_id.
    """
    exam_id = models.IntegerField(
        help_text="Unique exam identifier this question paper belongs to"
    )
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='exam_question_papers',
        help_text="Teacher who owns this exam"
    )

    def question_pdf_folder_path(instance):
        username = instance.teacher.username if instance.teacher else 'unknown_teacher'
        return f"ResTrack/{username}/Exam Questions"

    question_pdf = CloudinaryField(
        resource_type='raw',
        folder=question_pdf_folder_path,
        help_text="PDF file containing exam questions"
    )
    uploaded_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Exam Question Paper"
        verbose_name_plural = "Exam Question Papers"
        ordering = ['-exam_id']
        unique_together = ['exam_id', 'teacher']

    def __str__(self):
        return f"Question Paper for Exam #{self.exam_id}"

    @property
    def question_pdf_public_id(self):
        """Extract Cloudinary public ID from question_pdf URL"""
        if not self.question_pdf:
            return None
        try:
            url = str(self.question_pdf)
            if 'cloudinary.com' in url:
                parts = url.split('/upload/')
                if len(parts) > 1:
                    path_part = parts[1]
                    if '.' in path_part:
                        return path_part.rsplit('.', 1)[0]
                    return path_part
        except:
            pass
        return None


class Exam(models.Model):
    """
    Model representing a single exam result entry.
    
    Note: group_id is used to link multiple student results from the same exam
    (when entered via bulk entry). Exams with the same group_id are counted as
    one exam in statistics.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    exam_type = models.ForeignKey(ExamType, on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='exams',
        null=True,
        blank=True,
        help_text="Teacher who created this exam"
    )
    date = models.DateField()
    chapter = models.CharField(max_length=200, blank=True, null=True)
    class_number = models.IntegerField(default=1)
    total_marks = models.IntegerField()
    mark_obtained = models.IntegerField()
    group_id = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="Groups multiple student results for the same exam (bulk entry)"
    )
    exam_id = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Unique exam identifier (same for bulk entries)"
    )
    # Legacy field - kept for backward compatibility, new uploads go to ExamQuestionPaper
    def exam_pdf_folder_path(instance):
        """
        Returns folder path for exam question PDF in the format:
        ResTrack/<teacher username>/Exam Questions
        """
        username = instance.teacher.username if instance.teacher else 'unknown_teacher'
        return f"ResTrack/{username}/Exam Questions"

    question_pdf = CloudinaryField(
        resource_type='raw',
        folder=exam_pdf_folder_path,
        blank=True,
        null=True,
        help_text="Legacy field - question papers now stored in ExamQuestionPaper model"
    )

    @property
    def question_pdf_public_id(self):
        """Extract Cloudinary public ID from question_pdf URL (legacy or new model)"""
        # First check the new ExamQuestionPaper model
        qp = self.get_question_paper()
        if qp:
            return qp.question_pdf_public_id
        # Fallback to legacy field
        if not self.question_pdf:
            return None
        try:
            url = str(self.question_pdf)
            if 'cloudinary.com' in url:
                parts = url.split('/upload/')
                if len(parts) > 1:
                    path_part = parts[1]
                    if '.' in path_part:
                        return path_part.rsplit('.', 1)[0]
                    return path_part
        except:
            pass
        return None

    def get_question_paper(self):
        """Get the ExamQuestionPaper for this exam's exam_id, if it exists"""
        if self.exam_id and self.teacher:
            try:
                return ExamQuestionPaper.objects.get(exam_id=self.exam_id, teacher=self.teacher)
            except ExamQuestionPaper.DoesNotExist:
                pass
        return None

    @property
    def has_question_pdf(self):
        """Check if this exam has a question paper (new model or legacy)"""
        qp = self.get_question_paper()
        if qp and qp.question_pdf:
            return True
        return bool(self.question_pdf)
    
    def marked_answer_folder_path(instance):
        """
        Returns folder path for marked answer paper in the format:
        ResTrack/<teacher username>/Marked Answer Papers
        """
        username = instance.teacher.username if instance.teacher else 'unknown_teacher'
        return f"ResTrack/{username}/Marked Answer Papers"

    marked_answer_paper = CloudinaryField(
        resource_type='raw',
        folder=marked_answer_folder_path,
        blank=True,
        null=True,
        help_text="Marked/examined answer paper (PDF/ZIP/RAR, max 10MB)"
    )

    @property
    def marked_answer_paper_public_id(self):
        """Extract Cloudinary public ID from marked_answer_paper URL"""
        if not self.marked_answer_paper:
            return None
        try:
            # CloudinaryField stores the full URL, extract public ID
            url = str(self.marked_answer_paper)
            if 'cloudinary.com' in url:
                # URL format: https://res.cloudinary.com/{cloud_name}/raw/upload/{folder}/{public_id}
                parts = url.split('/upload/')
                if len(parts) > 1:
                    path_part = parts[1]
                    # Remove file extension to get public ID
                    if '.' in path_part:
                        return path_part.rsplit('.', 1)[0]
                    return path_part
        except:
            pass
        return None
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']

    def __str__(self):
        return f"{self.student.name} - {self.subject.name} - {self.exam_type.name}"

    @property
    def percentage(self):
        """
        Calculate exam percentage score.
        
        Returns:
            float: Percentage score rounded to 2 decimal places
        """
        if self.total_marks > 0:
            return (self.mark_obtained / self.total_marks) * 100
        return 0

    @property
    def grade(self):
        """
        Get letter grade based on percentage and exam type.
        
        Returns:
            str: Grade name (e.g., "Superb", "Good") or "N/A"
        """
        percentage = self.percentage
        exam_type_name = self.exam_type.name.upper().strip() if self.exam_type else ""
        
        # Determine grade based on exam type
        if exam_type_name == "MCQ":
            if percentage >= 93:
                return "Superb"
            elif percentage >= 77:
                return "Good"
            elif percentage >= 55:
                return "Average"
            elif percentage >= 40:
                return "Poor"
            elif percentage >= 30:
                return "Fail"
            else:
                return "Horrible"
        else:  # CQ or default
            if percentage >= 85:
                return "Superb"
            elif percentage >= 70:
                return "Good"
            elif percentage >= 50:
                return "Average"
            elif percentage >= 33:
                return "Poor"
            elif percentage >= 20:
                return "Fail"
            else:
                return "Horrible"

    @property
    def grade_color(self):
        """
        Get display color for the grade based on the grade name.

        Returns:
            str: Hex color code (e.g., "#4CAF50")
        """
        grade_name = self.grade

        # Map grade names to colors
        color_map = {
            "Superb": "#A7F3D0",  # Emerald-200 (darker green)
            "Good": "#D1FAE5",       # Green-100 (lighter green)
            "Average": "#FEF08A",    # Yellow-200 (very light yellow)
            "Poor": "#FDE68A",       # Amber-200 (very light amber)
            "Fail": "#FECACA",       # Red-200 (very light red)
            "Horrible": "#FCA5A5",   # Red-300 (light red)
        }

        return color_map.get(grade_name, "#000000")


    @property
    def points_earned(self):
        """
        Calculate lifetime points earned from this exam.
        Different thresholds for CQ vs MCQ exam types.
        
        Point System:
        
        Superb (+20 points):
        - CQ: >= 85%
        - MCQ: >= 93%
        
        Good (+15 points):
        - CQ: 70-84.99%
        - MCQ: 77-92.99%
        
        Average (0 points):
        - CQ: 50-69.99%
        - MCQ: 55-76.99%
        
        Poor (-10 points):
        - CQ: 33-49.99%
        - MCQ: 40-54.99%
        
        Fail (-15 points):
        - CQ: 20-32.99%
        - MCQ: 30-39.99%
        
        Horrible (-20 points):
        - CQ: < 20%
        - MCQ: < 30%
        
        Returns:
            int: Points earned (can be negative)
        """
        percentage = self.percentage
        exam_type_name = self.exam_type.name.upper().strip() if self.exam_type else ""
        
        # MCQ grading thresholds
        if exam_type_name == "MCQ":
            if percentage >= 93:
                return 20  # Superb
            elif percentage >= 77:
                return 15  # Good
            elif percentage >= 55:
                return 0   # Average
            elif percentage >= 40:
                return -10 # Poor
            elif percentage >= 30:
                return -15 # Fail
            else:
                return -20 # Horrible
        
        # CQ grading thresholds (default)
        else:
            if percentage >= 85:
                return 20  # Superb
            elif percentage >= 70:
                return 15  # Good
            elif percentage >= 50:
                return 0   # Average
            elif percentage >= 33:
                return -10 # Poor
            elif percentage >= 20:
                return -15 # Fail
            else:
                return -20 # Horrible
        
        # if you change value here, run 'python manage.py recalculate_all_points' to update all students' lifetime points based on the new values

    def save(self, *args, **kwargs):
        """Override save, no longer recalculates lifetime points (handled by signal)"""
        super().save(*args, **kwargs)


class LifetimePoints(models.Model):
    """Model tracking accumulated points for rewards/achievements"""
    student = models.OneToOneField(Student, on_delete=models.CASCADE)
    points_earned = models.IntegerField(default=0, help_text="Total points earned from exams")
    points_spent = models.IntegerField(default=0, help_text="Points spent on rewards")

    class Meta:
        verbose_name = "Lifetime Points"
        verbose_name_plural = "Lifetime Points"

    def __str__(self):
        return f"{self.student.name} - {self.points_remaining} points remaining"

    @property
    def total_points(self):
        """
        Total lifetime points earned (never decreases).
        
        Returns:
            int: Total points earned from all exams
        """
        return self.points_earned

    @property
    def points_remaining(self):
        """
        Calculate remaining available points.
        
        Returns:
            int: Points earned minus points spent
        """
        return self.points_earned - self.points_spent


class PointsSpent(models.Model):
    """Legacy model for backward compatibility - now creates PointTransaction entries"""

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='points_spent_records',
        null=True,
        blank=True,
        help_text="Teacher who recorded this points spent"
    )
    points_spent = models.IntegerField(help_text="Number of points spent")
    description = models.CharField(max_length=15, help_text="How points were used")
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Points Spent (Legacy)"
        verbose_name_plural = "Points Spent (Legacy)"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.student.name} - {self.points_spent} points on {self.date}"

    def save(self, *args, **kwargs):
        """Create corresponding PointTransaction entry"""
        super().save(*args, **kwargs)
        # Create or update corresponding PointTransaction
        PointTransaction.objects.update_or_create(
            student=self.student,
            teacher=self.teacher,
            transaction_type='spent',
            date=self.date,
            description=self.description,
            defaults={
                'points_change': -self.points_spent,  # Negative for spending
                'exam': None
            }
        )
        # Update student's lifetime points
        from django.db.models import Sum
        lifetime_points, created = LifetimePoints.objects.get_or_create(student=self.student)
        total_spent = PointsSpent.objects.filter(student=self.student).aggregate(
            total=Sum('points_spent')
        )['total'] or 0
        lifetime_points.points_spent = total_spent
        lifetime_points.save()

    def delete(self, *args, **kwargs):
        """Remove corresponding PointTransaction entry"""
        # Find and delete corresponding PointTransaction
        PointTransaction.objects.filter(
            student=self.student,
            teacher=self.teacher,
            transaction_type='spent',
            date=self.date,
            description=self.description
        ).delete()

        student = self.student
        super().delete(*args, **kwargs)
        # Update the student's total points spent after deletion
        from django.db.models import Sum
        lifetime_points = LifetimePoints.objects.filter(student=student).first()
        if lifetime_points:
            total_spent = PointsSpent.objects.filter(student=student).aggregate(
                total=Sum('points_spent')
            )['total'] or 0
            lifetime_points.points_spent = total_spent
            lifetime_points.save()

    class Meta:
        verbose_name = "Points Spent"
        verbose_name_plural = "Points Spent"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.student.name} - {self.points_spent} points on {self.date}"

    def save(self, *args, **kwargs):
        """Create corresponding PointTransaction entry and update lifetime points"""
        super().save(*args, **kwargs)

        # Create or update corresponding PointTransaction
        PointTransaction.objects.update_or_create(
            student=self.student,
            teacher=self.teacher,
            transaction_type='spent',
            date=self.date,
            description=self.description,
            defaults={
                'points_change': -self.points_spent,  # Negative for spending
                'exam': None
            }
        )

        # Update the student's total points spent
        from django.db.models import Sum
        lifetime_points, created = LifetimePoints.objects.get_or_create(student=self.student)
        total_spent = PointsSpent.objects.filter(student=self.student).aggregate(
            total=Sum('points_spent')
        )['total'] or 0
        lifetime_points.points_spent = total_spent
        lifetime_points.save()

    def delete(self, *args, **kwargs):
        """Override delete to update student's lifetime points"""
        student = self.student
        super().delete(*args, **kwargs)
        # Update the student's total points spent after deletion
        from django.db.models import Sum
        lifetime_points = LifetimePoints.objects.filter(student=student).first()
        if lifetime_points:
            total_spent = PointsSpent.objects.filter(student=student).aggregate(
                total=Sum('points_spent')
            )['total'] or 0
            lifetime_points.points_spent = total_spent
            lifetime_points.save()


class PointTransaction(models.Model):
    """Unified model for all point transactions (manual spending and automatic adjustments)"""

    TRANSACTION_TYPES = [
        ('spent', 'Points Spent (Manual)'),
        ('exam_bonus', 'Exam Performance Bonus'),
        ('exam_penalty', 'Exam Performance Penalty'),
        ('monthly_win', 'Monthly Winner Bonus'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='point_transactions',
        null=True,
        blank=True,
        help_text="Teacher who recorded this transaction"
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        default='spent',
        help_text="Type of point transaction"
    )
    points_change = models.IntegerField(
        help_text="Points gained (positive) or lost (negative). Use negative values for spending/penalties."
    )
    description = models.CharField(max_length=100, help_text="Description of the transaction")
    date = models.DateField()
    exam = models.ForeignKey(
        'Exam',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Related exam (for exam-based transactions)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Point Transaction"
        verbose_name_plural = "Point Transactions"
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.student.name} - {self.get_transaction_type_display()} - {self.points_change:+d} pts on {self.date}"

    @property
    def short_description(self):
        """Return a compact description for mobile views (e.g. abbreviated year, short subject name)."""
        import re
        desc = self.description
        # Convert "Monthly winner – January 2025" → "Monthly winner – January '25"
        match = re.match(r"^(Monthly winner \u2013 \w+) (\d{4})$", desc)
        if match:
            desc = f"{match.group(1)} '{match.group(2)[2:]}"
        # Replace full subject name with short name if available
        if self.exam and self.exam.subject and self.exam.subject.short_name:
            desc = desc.replace(self.exam.subject.name, self.exam.subject.short_name)
        return desc

    @property
    def is_positive(self):
        """Check if this transaction adds points"""
        return self.points_change > 0

    @property
    def is_negative(self):
        """Check if this transaction subtracts points"""
        return self.points_change < 0
