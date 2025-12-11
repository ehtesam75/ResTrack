from django.db.models import Sum, Avg, Count, Q
from .models import Student, Subject, ExamType, Exam, GradeScale

# Default color mapping for grades (from GradeScale table for consistency)
DEFAULT_GRADE_COLORS = {
    'Average': '#FEF08A',
    'Fail': '#FECACA',
    'Good': '#D1FAE5',
    'Horrible': '#FCA5A5',
    'Poor': '#FDE68A',
    'Superb': '#A7F3D0',
}
from collections import Counter


def count_unique_exams(queryset):
    """
    Helper function to count unique exams in a queryset.
    Grouped exams (bulk entries) count as 1, individual exams count as 1 each.
    
    Args:
        queryset: Django QuerySet of Exam objects
        
    Returns:
        int: Count of unique exams
    """
    # Count total unique exam_id values only
    return queryset.values('exam_id').distinct().count()


class LeaderboardService:
    """Service class for generating various leaderboards"""
    
    @staticmethod
    def total_marks_leaderboard():
        """Generate leaderboard based on total marks"""
        students = Student.objects.all()
        leaderboard = [
            {
                'student': student,
                'total_marks': student.total_marks,
                'total_exams': student.total_exams
            }
            for student in students
        ]
        return sorted(leaderboard, key=lambda x: x['total_marks'], reverse=True)
    
    @staticmethod
    def average_leaderboard():
        """Generate leaderboard based on average percentage"""
        students = Student.objects.all()
        leaderboard = [
            {
                'student': student,
                'average': student.average_percentage,
                'total_exams': student.total_exams
            }
            for student in students if student.total_exams > 0
        ]
        return sorted(leaderboard, key=lambda x: x['average'], reverse=True)
    
    @staticmethod
    def subject_wise_leaderboard(subject_id):
        """Generate leaderboard for a specific subject"""
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            return []
        
        students = Student.objects.filter(exam__subject=subject).distinct()
        leaderboard = []
        
        for student in students:
            exams = student.exam_set.filter(subject=subject)
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
            
            leaderboard.append({
                'student': student,
                'average': round(avg_percentage, 2),
                'total_marks': total_marks_obtained,
                'exam_count': exams.count()
            })
        
        return sorted(leaderboard, key=lambda x: x['average'], reverse=True)
    
    @staticmethod
    def exam_type_leaderboard(exam_type_id):
        """Generate leaderboard for a specific exam type"""
        try:
            exam_type = ExamType.objects.get(id=exam_type_id)
        except ExamType.DoesNotExist:
            return []
        
        students = Student.objects.filter(exam__exam_type=exam_type).distinct()
        leaderboard = []
        
        for student in students:
            exams = student.exam_set.filter(exam_type=exam_type)
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
            
            leaderboard.append({
                'student': student,
                'average': round(avg_percentage, 2),
                'total_marks': total_marks_obtained,
                'exam_count': exams.count()
            })
        
        return sorted(leaderboard, key=lambda x: x['average'], reverse=True)
    
    @staticmethod
    def lifetime_points_leaderboard():
        """Generate leaderboard based on lifetime points"""
        from .models import LifetimePoints
        lifetime_points = LifetimePoints.objects.all()
        leaderboard = [
            {
                'student': lp.student,
                'total_points': lp.total_points,
                'points_earned': lp.points_earned,
                'points_spent': lp.points_spent
            }
            for lp in lifetime_points
        ]
        return sorted(leaderboard, key=lambda x: x['total_points'], reverse=True)


class DashboardService:
    """Service class for generating dashboard data"""
    
    @staticmethod
    def get_dashboard_summary():
        """Get overall dashboard summary statistics"""
        total_exams = count_unique_exams(Exam.objects.all())
        total_subjects = Subject.objects.count()
        total_students = Student.objects.count()
        
        # Get highest performers
        students = Student.objects.all()
        if students:
            highest_marks_student = max(students, key=lambda s: s.total_marks)
            highest_avg_student = max(
                [s for s in students if s.total_exams > 0],
                key=lambda s: s.average_percentage,
                default=None
            )
            best_student = highest_avg_student
        else:
            highest_marks_student = None
            highest_avg_student = None
            best_student = None
        
        return {
            'total_exams': total_exams,
            'total_subjects': total_subjects,
            'total_students': total_students,
            'highest_marks_student': highest_marks_student,
            'highest_avg_student': highest_avg_student,
            'best_student': best_student
        }
    
    @staticmethod
    def get_subject_performance_table():
        """Get performance data for all subjects"""
        subjects = Subject.objects.all()
        performance_data = []
        
        for subject in subjects:
            exams = Exam.objects.filter(subject=subject)
            if exams.exists():
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (
                    (total_marks_obtained * 100 / total_possible_marks) 
                    if total_possible_marks > 0 else 0
                )
                
                performance_data.append({
                    'subject': subject,
                    'average_percentage': round(avg_percentage, 2),
                    'total_exams': count_unique_exams(exams),
                    'best_student': subject.best_student()
                })
        
        return sorted(performance_data, key=lambda x: x['average_percentage'], reverse=True)
    
    @staticmethod
    def get_exam_type_performance_table():
        """Get performance data for all exam types"""
        exam_types = ExamType.objects.all()
        performance_data = []
        
        for exam_type in exam_types:
            exams = Exam.objects.filter(exam_type=exam_type)
            if exams.exists():
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (
                    (total_marks_obtained * 100 / total_possible_marks) 
                    if total_possible_marks > 0 else 0
                )
                
                performance_data.append({
                    'exam_type': exam_type,
                    'average_percentage': round(avg_percentage, 2),
                    'total_exams': count_unique_exams(exams)
                })
        
        return sorted(performance_data, key=lambda x: x['average_percentage'], reverse=True)
    
    @staticmethod
    def get_grade_distribution():
        """Get grade distribution across all exams"""
        exams = Exam.objects.all()
        grades = [exam.grade for exam in exams]
        distribution = Counter(grades)

        # Get color codes for each grade, fallback to default mapping
        grade_data = []
        for grade_name, count in distribution.items():
            grade_scale = GradeScale.objects.filter(grade_name=grade_name).first()
            if grade_scale:
                color = grade_scale.color_code
            else:
                color = DEFAULT_GRADE_COLORS.get(grade_name, '#000000')
            grade_data.append({
                'grade': grade_name,
                'count': count,
                'color': color
            })
        return grade_data
    
    @staticmethod
    def get_recent_exams(limit=10):
        """Get most recent exams"""
        return Exam.objects.all().order_by('-date', '-exam_id')[:limit]


class ChartDataService:
    """Service class for generating chart data"""
    
    @staticmethod
    def marks_over_time(student_id):
        """Generate line chart data for student marks over time"""
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return {'labels': [], 'data': []}
        
        exams = student.exam_set.all().order_by('date')
        labels = [f"{exam.subject.name} ({exam.date.strftime('%m/%d')})" for exam in exams]
        data = [float(exam.percentage) for exam in exams]
        
        return {'labels': labels, 'data': data}
    
    @staticmethod
    def subject_performance_chart(student_id):
        """Generate chart data for per-subject performance"""
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return {'labels': [], 'data': []}
        
        subject_summary = student.subject_wise_summary()
        labels = [item['subject'].name for item in subject_summary]
        data = [float(item['average_percentage']) for item in subject_summary]
        
        return {'labels': labels, 'data': data}
    
    @staticmethod
    def grade_distribution_chart(student_id):
        """Generate chart data for grade distribution"""
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return {'labels': [], 'data': [], 'colors': []}

        grade_freq = student.grade_frequency()
        labels = list(grade_freq.keys())
        data = list(grade_freq.values())

        # Get colors for each grade, fallback to default mapping
        colors = []
        for grade_name in labels:
            grade_scale = GradeScale.objects.filter(grade_name=grade_name).first()
            if grade_scale:
                color = grade_scale.color_code
            else:
                color = DEFAULT_GRADE_COLORS.get(grade_name, '#000000')
            colors.append(color)
        return {'labels': labels, 'data': data, 'colors': colors}
    
    @staticmethod
    def student_comparison_chart(subject_id):
        """Generate chart comparing all students in a subject"""
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            return {'labels': [], 'data': []}
        
        students = Student.objects.filter(exam__subject=subject).distinct()
        comparison_data = []
        
        for student in students:
            exams = student.exam_set.filter(subject=subject)
            if exams.exists():
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
                comparison_data.append({
                    'student': student.name,
                    'average': round(avg_percentage, 2)
                })
        
        comparison_data = sorted(comparison_data, key=lambda x: x['average'], reverse=True)
        labels = [item['student'] for item in comparison_data]
        data = [float(item['average']) for item in comparison_data]
        
        return {'labels': labels, 'data': data}
    
    @staticmethod
    def overall_grade_distribution():
        """Generate chart for overall grade distribution"""
        grade_data = DashboardService.get_grade_distribution()
        labels = [item['grade'] for item in grade_data]
        data = [item['count'] for item in grade_data]
        colors = [item['color'] for item in grade_data]
        
        return {'labels': labels, 'data': data, 'colors': colors}
