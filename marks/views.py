from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.db.models import Sum, Q
import json
from .models import Student, Subject, ExamType, Exam, GradeScale, LifetimePoints, PointsSpent, TeacherProfile, StudentProfile
from django.db.models import Q
from .services import LeaderboardService, DashboardService, ChartDataService, count_unique_exams
from .forms import TeacherSignupForm, LoginForm, StudentAccountForm


def is_teacher(user):
    """Check if user is a teacher"""
    if not user.is_authenticated:
        return False
    return hasattr(user, 'teacher_profile')


def is_student(user):
    """Check if user is a student"""
    if not user.is_authenticated:
        return False
    return hasattr(user, 'student_profile')


def get_teacher_for_user(user):
    """
    Get the teacher user for data filtering.
    - If user is a teacher, return the user
    - If user is a student, return the teacher who created them
    """
    if not user.is_authenticated:
        return None
    
    if hasattr(user, 'teacher_profile'):
        return user
    
    if hasattr(user, 'student_profile'):
        # Return the teacher who created this student
        return user.student_profile.created_by
    
    return None


def home(request):
    """Landing page for the application"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    # Get global stats for home page
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    total_teachers = TeacherProfile.objects.count()
    total_students = Student.objects.count()
    # Calculate total exams as the sum of unique exams per teacher
    teacher_users = [tp.user for tp in TeacherProfile.objects.all()]
    total_exams = 0
    for teacher in teacher_users:
        teacher_exams = Exam.objects.filter(teacher=teacher)
        total_exams += count_unique_exams(teacher_exams)
    total_points = LifetimePoints.objects.aggregate(total=Sum('points_earned'))['total'] or 0

    context = {
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_exams': total_exams,
        'total_points': total_points,
    }

    return render(request, 'marks/home.html', context)


def teacher_signup(request):
    """Handle teacher registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TeacherSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = TeacherSignupForm()
    
    return render(request, 'marks/signup.html', {'form': form})


def user_login(request):
    """Handle user login (both teacher and student)"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'marks/login.html', {'form': form})


def user_logout(request):
    """Handle user logout"""
    logout(request)
    return redirect('home')


@login_required(login_url='login')
def manage(request):
    """Teacher management dashboard"""
    teacher = get_teacher_for_user(request.user)
    
    # Filter all data by teacher
    teacher_students = Student.objects.filter(teacher=teacher)
    teacher_subjects = Subject.objects.filter(teacher=teacher)
    teacher_exams = Exam.objects.filter(teacher=teacher)
    teacher_exam_types = ExamType.objects.filter(teacher=teacher)
    
    from .models import LifetimePoints
    # Get all student IDs under this teacher
    student_ids = teacher_students.values_list('id', flat=True)
    # Sum all points_earned for these students
    teacher_students_lifetime_points = LifetimePoints.objects.filter(student_id__in=student_ids).aggregate(total=Sum('points_earned'))['total'] or 0

    context = {
        'is_teacher': is_teacher(request.user),
        'total_students': teacher_students.count(),
        'total_subjects': teacher_subjects.count(),
        'total_exams': count_unique_exams(teacher_exams),
        # 'total_exam_types': teacher_exam_types.count(),  # No longer needed in template
        'teacher_students_lifetime_points': teacher_students_lifetime_points,
        'recent_students': teacher_students.order_by('-created_at')[:5],
        'recent_exams': teacher_exams.order_by('-date', '-id')[:100],
    }
    return render(request, 'marks/manage.html', context)


@login_required(login_url='login')
def dashboard(request):
    """Main dashboard view with analytics - filtered by teacher"""
    from collections import Counter
    
    teacher = get_teacher_for_user(request.user)
    
    # Filter all data by teacher
    teacher_students = Student.objects.filter(teacher=teacher)
    teacher_subjects = Subject.objects.filter(teacher=teacher)
    teacher_exams = Exam.objects.filter(teacher=teacher)
    teacher_exam_types = ExamType.objects.filter(teacher=teacher)
    
    # Dashboard summary
    total_exams = count_unique_exams(teacher_exams)
    total_subjects = teacher_subjects.count()
    total_students = teacher_students.count()
    
    # Get highest performers among teacher's students
    best_student = None
    highest_marks_student = None
    highest_avg_student = None
    
    if teacher_students.exists():
        students_with_exams = [s for s in teacher_students if s.total_exams > 0]
        if students_with_exams:
            highest_marks_student = max(teacher_students, key=lambda s: s.total_marks)
            highest_avg_student = max(students_with_exams, key=lambda s: s.average_percentage)
            best_student = highest_avg_student
    
    summary = {
        'total_exams': total_exams,
        'total_subjects': total_subjects,
        'total_students': total_students,
        'highest_marks_student': highest_marks_student,
        'highest_avg_student': highest_avg_student,
        'best_student': best_student
    }
    
    # Subject performance - filtered by teacher
    subject_performance = []
    for subject in teacher_subjects:
        exams = teacher_exams.filter(subject=subject)
        if exams.exists():
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
            
            # Best student in this subject (among teacher's students)
            best_in_subject = None
            best_avg = 0
            for student in teacher_students:
                student_exams = exams.filter(student=student)
                if student_exams.exists():
                    s_total = sum(float(e.mark_obtained) for e in student_exams)
                    s_possible = sum(float(e.total_marks) for e in student_exams)
                    s_avg = (s_total * 100 / s_possible) if s_possible > 0 else 0
                    if s_avg > best_avg:
                        best_avg = s_avg
                        best_in_subject = student
            
            subject_performance.append({
                'subject': subject,
                'average_percentage': round(avg_percentage, 2),
                'total_exams': count_unique_exams(exams),
                'best_student': best_in_subject
            })
    
    subject_performance = sorted(subject_performance, key=lambda x: x['average_percentage'], reverse=True)
    
    # Exam type performance - filtered by teacher
    exam_type_performance = []
    for exam_type in teacher_exam_types:
        exams = teacher_exams.filter(exam_type=exam_type)
        if exams.exists():
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
            
            exam_type_performance.append({
                'exam_type': exam_type,
                'average_percentage': round(avg_percentage, 2),
                'total_exams': count_unique_exams(exams)
            })
    
    exam_type_performance = sorted(exam_type_performance, key=lambda x: x['average_percentage'], reverse=True)
    
    # Grade distribution - filtered by teacher
    grades = [exam.grade for exam in teacher_exams]
    distribution = Counter(grades)
    
    grade_colors = {
        'Average': '#FEF08A', 'Fail': '#FECACA', 'Good': '#D1FAE5',
        'Horrible': '#FCA5A5', 'Poor': '#FDE68A', 'Superb': '#A7F3D0',
    }
    
    grade_distribution = []
    for grade_name, count in distribution.items():
        grade_scale = GradeScale.objects.filter(grade_name=grade_name).first()
        color = grade_scale.color_code if grade_scale else grade_colors.get(grade_name, '#000000')
        grade_distribution.append({'grade': grade_name, 'count': count, 'color': color})
    
    # Recent exams - filtered by teacher
    recent_exams = teacher_exams.order_by('-date', '-exam_id')[:10]
    
    # Leaderboards - filtered by teacher's students (TOP 3 only)
    total_marks_leaderboard = sorted(
        [{'student': s, 'total_marks': s.total_marks, 'total_exams': s.total_exams} for s in teacher_students],
        key=lambda x: x['total_marks'], reverse=True
    )[:3]
    
    average_leaderboard = sorted(
        [{'student': s, 'average': s.average_percentage, 'total_exams': s.total_exams} 
         for s in teacher_students if s.total_exams > 0],
        key=lambda x: x['average'], reverse=True
    )[:3]
    
    # Points leaderboard - filtered by teacher's students (TOP 3 only)
    from .models import LifetimePoints
    points_leaderboard = []
    for student in teacher_students:
        lp = LifetimePoints.objects.filter(student=student).first()
        if lp:
            points_leaderboard.append({
                'student': student,
                'total_points': lp.total_points,
                'points_earned': lp.points_earned,
                'points_spent': lp.points_spent
            })
    points_leaderboard = sorted(points_leaderboard, key=lambda x: x['total_points'], reverse=True)[:3]
    
    # Serialize subject_performance for JavaScript
    subject_performance_json = json.dumps([
        {
            'subject': {
                'name': item['subject'].name,
                'short_name': item['subject'].short_name,
                'id': item['subject'].id
            },
            'average_percentage': item['average_percentage'],
            'total_exams': item['total_exams'],
            'best_student': item['best_student'].name if item['best_student'] else None
        }
        for item in subject_performance
    ])
    
    context = {
        'summary': summary,
        'subject_performance': subject_performance,
        'subject_performance_json': subject_performance_json,
        'exam_type_performance': exam_type_performance,
        'grade_distribution': grade_distribution,
        'recent_exams': recent_exams,
        'total_marks_leaderboard': total_marks_leaderboard,
        'average_leaderboard': average_leaderboard,
        'points_leaderboard': points_leaderboard,
    }
    
    return render(request, 'marks/dashboard.html', context)


@login_required(login_url='login')
def student_list(request):
    """List all students - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    
    # Add computed properties for sorting/display
    student_data = [
        {
            'student': student,
            'total_marks': student.total_marks,
            'average': student.average_percentage,
            'rank': student.rank
        }
        for student in students
    ]
    
    context = {'students': student_data}
    return render(request, 'marks/student_list.html', context)


@login_required(login_url='login')
def student_detail(request, student_id):
    """Student profile dashboard"""
    from datetime import datetime
    from django.db.models import Avg, Sum
    
    teacher = get_teacher_for_user(request.user)
    student = get_object_or_404(Student, id=student_id, teacher=teacher)
    
    # Get student statistics
    subject_summary = student.subject_wise_summary()
    exam_type_summary = student.exam_type_summary()
    grade_frequency = student.grade_frequency()
    recent_exams = student.exam_set.all().order_by('-date', '-exam_id')[:10]
    
    # Get lifetime points
    try:
        lifetime_points = LifetimePoints.objects.get(student=student)
    except LifetimePoints.DoesNotExist:
        lifetime_points = None
    
    # Calculate Excellence Rate (CQ >=80%, MCQ >=85%)
    exams = student.exam_set.all()
    total_exams = student.total_exams
    excellence_rate = 0
    
    if total_exams > 0:
        excellent_exams = 0
        for exam in exams:
            # Count exams meeting excellence criteria based on exam type
            percentage = exam.percentage
            exam_type_name = exam.exam_type.name.upper().strip()
            
            if exam_type_name == "MCQ" and percentage >= 85:
                excellent_exams += 1
            elif exam_type_name == "CQ" and percentage >= 80:
                excellent_exams += 1
        excellence_rate = (excellent_exams / total_exams) * 100
    
    # Calculate Monthly Winner Count (only past months, #1 positions) - within same teacher
    from datetime import date
    current_year = date.today().year
    current_month = date.today().month
    
    monthly_winner_count = 0
    # Only look at teacher's exams
    exam_dates = Exam.objects.filter(teacher=teacher).values_list('date', flat=True).distinct()
    months_set = set()
    
    for exam_date in exam_dates:
        if exam_date:
            # Only count months that have fully passed
            if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                months_set.add((exam_date.year, exam_date.month))
    
    for year, month in months_set:
        # Get total unique exams conducted in this month (teacher-scoped)
        total_month_exams = Exam.objects.filter(
            teacher=teacher,
            date__year=year,
            date__month=month
        ).values('exam_id').distinct().count()
        
        # Get all students who had exams in this month (teacher-scoped)
        students_in_month = Student.objects.filter(
            teacher=teacher,
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
        
        # Check if this student is tied for #1
        if month_rankings:
            top_avg = month_rankings[0]['average_percentage']
            top_total = month_rankings[0]['total_marks']
            
            # Find this student in rankings
            for ranking in month_rankings:
                if ranking['student_id'] == student.id:
                    # If this student has same avg AND same total marks as top, count it as a win
                    if (abs(ranking['average_percentage'] - top_avg) < 0.01 and
                        ranking['total_marks'] == top_total):
                        monthly_winner_count += 1
                    break
    
    # Calculate Subject Champion Count (how many subjects they've topped) - within same teacher
    subject_champion_count = 0
    subjects = Subject.objects.filter(teacher=teacher)
    
    for subject in subjects:
        students_in_subject = Student.objects.filter(teacher=teacher, exam__subject=subject).distinct()
        subject_rankings = []
        
        for s in students_in_subject:
            subject_exams = s.exam_set.filter(subject=subject)
            exams_count = subject_exams.count()
            
            if exams_count > 0:
                total_marks = sum(float(e.mark_obtained) for e in subject_exams)
                total_possible = sum(float(e.total_marks) for e in subject_exams)
                avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
                
                subject_rankings.append({
                    'student_id': s.id,
                    'average_percentage': avg_percentage,
                    'total_marks': total_marks,
                })
        
        # Sort by average score (primary), then total marks (tie-breaker)
        subject_rankings.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
        
        # Check if this student is tied for #1
        if subject_rankings:
            top_avg = subject_rankings[0]['average_percentage']
            top_total = subject_rankings[0]['total_marks']
            
            # Find this student in rankings
            for ranking in subject_rankings:
                if ranking['student_id'] == student.id:
                    # If this student has same avg AND same total marks as top, count it
                    if (abs(ranking['average_percentage'] - top_avg) < 0.01 and
                        ranking['total_marks'] == top_total):
                        subject_champion_count += 1
                    break
    
    # Calculate Best 5 Months (exclude current month)
    monthly_performance = []
    all_exam_dates = student.exam_set.values_list('date', flat=True).distinct()
    student_months_set = set()
    
    for exam_date in all_exam_dates:
        if exam_date:
            # Only include months that have fully passed
            if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                student_months_set.add((exam_date.year, exam_date.month))
    
    for year, month in student_months_set:
        month_exams = student.exam_set.filter(date__year=year, date__month=month)
        exams_count = month_exams.count()
        
        if exams_count > 0:
            total_marks = sum(float(e.mark_obtained) for e in month_exams)
            total_possible = sum(float(e.total_marks) for e in month_exams)
            avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
            points_earned = sum(e.points_earned for e in month_exams)
            
            month_name = datetime(year, month, 1).strftime('%B %Y')
            
            monthly_performance.append({
                'month_name': month_name,
                'exams_count': exams_count,
                'average_percentage': avg_percentage,
                'points_earned': points_earned,
            })
    
    # Sort by average percentage and get top 5
    monthly_performance.sort(key=lambda x: x['average_percentage'], reverse=True)
    best_5_months = monthly_performance[:5]
    
    # Get all other students for comparison dropdown (teacher-scoped)
    all_students = Student.objects.filter(teacher=teacher).exclude(id=student_id).order_by('first_name', 'last_name')
    
    context = {
        'student': student,
        'subject_summary': subject_summary,
        'exam_type_summary': exam_type_summary,
        'grade_frequency': grade_frequency,
        'recent_exams': recent_exams,
        'lifetime_points': lifetime_points,
        'excellence_rate': excellence_rate,
        'monthly_winner_count': monthly_winner_count,
        'subject_champion_count': subject_champion_count,
        'best_5_months': best_5_months,
        'all_students': all_students,
    }
    
    return render(request, 'marks/student_detail.html', context)


@login_required(login_url='login')
def compare_students(request, student1_id, student2_id):
    """Compare two students side by side - filtered by teacher"""
    from datetime import date
    
    teacher = get_teacher_for_user(request.user)
    
    student1 = get_object_or_404(Student, id=student1_id, teacher=teacher)
    student2 = None
    if student2_id != 0:
        student2 = get_object_or_404(Student, id=student2_id, teacher=teacher)
    
    # Get all other students for the dropdown (filtered by teacher)
    all_students = Student.objects.filter(teacher=teacher).exclude(id=student1_id).order_by('first_name', 'last_name')
    
    # Get teacher-scoped querysets for calculations
    teacher_exams = Exam.objects.filter(teacher=teacher)
    teacher_students = Student.objects.filter(teacher=teacher)
    teacher_subjects = Subject.objects.filter(teacher=teacher)
    
    def get_student_stats(student):
        """Get comprehensive stats for a student"""
        # Basic stats
        total_marks = student.total_marks
        average_percentage = student.average_percentage
        total_exams = student.total_exams
        rank = student.rank
        
        # Excellence rate
        exams = student.exam_set.all()
        excellence_rate = 0
        if total_exams > 0:
            excellent_exams = 0
            for exam in exams:
                percentage = exam.percentage
                exam_type_name = exam.exam_type.name.upper().strip()
                if exam_type_name == "MCQ" and percentage >= 85:
                    excellent_exams += 1
                elif exam_type_name == "CQ" and percentage >= 80:
                    excellent_exams += 1
            excellence_rate = (excellent_exams / total_exams) * 100
        
        # Monthly winner count (within teacher's students)
        current_year = date.today().year
        current_month = date.today().month
        monthly_winner_count = 0
        
        exam_dates = teacher_exams.values_list('date', flat=True).distinct()
        months_set = set()
        for exam_date in exam_dates:
            if exam_date:
                if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                    months_set.add((exam_date.year, exam_date.month))
        
        for year, month in months_set:
            # Get total unique exams conducted in this month (teacher-scoped)
            total_month_exams = teacher_exams.filter(
                date__year=year,
                date__month=month
            ).values('exam_id').distinct().count()
            
            students_in_month = teacher_students.filter(
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
                    total_m = sum(float(e.mark_obtained) for e in month_exams)
                    total_p = sum(float(e.total_marks) for e in month_exams)
                    avg_p = (total_m * 100 / total_p) if total_p > 0 else 0
                    month_rankings.append({
                        'student_id': s.id,
                        'average_percentage': avg_p,
                        'total_marks': total_m
                    })
            
            # Sort by average score (primary), then total marks (tie-breaker)
            month_rankings.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
            
            # Check if this student is tied for #1
            if month_rankings:
                top_avg = month_rankings[0]['average_percentage']
                top_total = month_rankings[0]['total_marks']
                
                for ranking in month_rankings:
                    if ranking['student_id'] == student.id:
                        if (abs(ranking['average_percentage'] - top_avg) < 0.01 and
                            ranking['total_marks'] == top_total):
                            monthly_winner_count += 1
                        break
        
        # Subject champion count (teacher-scoped)
        subject_champion_count = 0
        for subject in teacher_subjects:
            students_in_subject = teacher_students.filter(exam__subject=subject).distinct()
            subject_rankings = []
            for s in students_in_subject:
                subject_exams = s.exam_set.filter(subject=subject)
                exams_count = subject_exams.values('exam_id').distinct().count()
                if exams_count > 0:
                    total_m = sum(float(e.mark_obtained) for e in subject_exams)
                    total_p = sum(float(e.total_marks) for e in subject_exams)
                    avg_p = (total_m * 100 / total_p) if total_p > 0 else 0
                    subject_rankings.append({
                        'student_id': s.id,
                        'average_percentage': avg_p,
                        'total_marks': total_m
                    })
            
            # Sort by average score (primary), then total marks (tie-breaker)
            subject_rankings.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
            
            # Check if this student is tied for #1
            if subject_rankings:
                top_avg = subject_rankings[0]['average_percentage']
                top_total = subject_rankings[0]['total_marks']
                
                for ranking in subject_rankings:
                    if ranking['student_id'] == student.id:
                        if (abs(ranking['average_percentage'] - top_avg) < 0.01 and
                            ranking['total_marks'] == top_total):
                            subject_champion_count += 1
                        break
        
        # Best month
        from datetime import datetime
        monthly_performance = []
        all_exam_dates = student.exam_set.values_list('date', flat=True).distinct()
        student_months_set = set()
        for exam_date in all_exam_dates:
            if exam_date:
                if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                    student_months_set.add((exam_date.year, exam_date.month))
        
        for year, month in student_months_set:
            month_exams = student.exam_set.filter(date__year=year, date__month=month)
            exams_count = month_exams.values('exam_id').distinct().count()
            if exams_count > 0:
                total_m = sum(float(e.mark_obtained) for e in month_exams)
                total_p = sum(float(e.total_marks) for e in month_exams)
                avg_p = (total_m * 100 / total_p) if total_p > 0 else 0
                month_name = datetime(year, month, 1).strftime('%B %Y')
                monthly_performance.append({
                    'month_name': month_name,
                    'average_percentage': avg_p,
                })
        
        monthly_performance.sort(key=lambda x: x['average_percentage'], reverse=True)
        best_month = monthly_performance[0]['month_name'] if monthly_performance else 'N/A'
        
        # Subject-wise performance
        subject_summary = student.subject_wise_summary()
        
        # Lifetime points
        try:
            lifetime_points = student.lifetimepoints.points_earned
        except:
            lifetime_points = 0
        
        # MCQ and CQ averages
        mcq_exams = exams.filter(exam_type__name__iexact='MCQ')
        cq_exams = exams.filter(exam_type__name__iexact='CQ')
        
        mcq_average = 0
        if mcq_exams.exists():
            mcq_total_obtained = sum(float(e.mark_obtained) for e in mcq_exams)
            mcq_total_possible = sum(float(e.total_marks) for e in mcq_exams)
            mcq_average = (mcq_total_obtained * 100 / mcq_total_possible) if mcq_total_possible > 0 else 0
        
        cq_average = 0
        if cq_exams.exists():
            cq_total_obtained = sum(float(e.mark_obtained) for e in cq_exams)
            cq_total_possible = sum(float(e.total_marks) for e in cq_exams)
            cq_average = (cq_total_obtained * 100 / cq_total_possible) if cq_total_possible > 0 else 0
        
        return {
            'student': student,
            'total_marks': total_marks,
            'average_percentage': average_percentage,
            'total_exams': total_exams,
            'rank': rank,
            'excellence_rate': round(excellence_rate, 1),
            'monthly_winner_count': monthly_winner_count,
            'subject_champion_count': subject_champion_count,
            'best_month': best_month,
            'subject_summary': subject_summary,
            'lifetime_points': lifetime_points,
            'mcq_average': round(mcq_average, 1),
            'cq_average': round(cq_average, 1),
        }
    
    stats1 = get_student_stats(student1)
    stats2 = get_student_stats(student2) if student2 else None
    
    context = {
        'student1_stats': stats1,
        'student2_stats': stats2,
        'all_students': all_students,
    }
    
    return render(request, 'marks/compare_students.html', context)


@login_required(login_url='login')
def subject_list(request):
    """List all subjects - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    
    subject_data = []
    for subject in subjects:
        exams = Exam.objects.filter(subject=subject, teacher=teacher)
        # Calculate average marks for teacher's students
        avg_marks = 0
        if exams.exists():
            total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
            total_possible_marks = sum(float(e.total_marks) for e in exams)
            avg_marks = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
        
        subject_data.append({
            'subject': subject,
            'average': round(avg_marks, 2),
            'total_exams': count_unique_exams(exams)
        })
    
    context = {'subjects': subject_data}
    return render(request, 'marks/subject_list.html', context)


@login_required(login_url='login')
def subject_detail(request, subject_id):
    """Subject dashboard - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)
    
    # Get subject statistics (filtered by teacher)
    exams = Exam.objects.filter(subject=subject, teacher=teacher)
    
    # Get best student among teacher's students
    teacher_students = Student.objects.filter(teacher=teacher)
    best_student = None
    best_avg = 0
    for student in teacher_students:
        student_exams = exams.filter(student=student)
        if student_exams.exists():
            total = sum(float(e.mark_obtained) for e in student_exams)
            possible = sum(float(e.total_marks) for e in student_exams)
            avg = (total * 100 / possible) if possible > 0 else 0
            if avg > best_avg:
                best_avg = avg
                best_student = student
    
    # Get all students in this subject with their performance (teacher-scoped)
    students = teacher_students.filter(exam__subject=subject).distinct()
    student_performance = []
    
    for student in students:
        student_exams = student.exam_set.filter(subject=subject)
        total_marks_obtained = sum(float(e.mark_obtained) for e in student_exams)
        total_possible_marks = sum(float(e.total_marks) for e in student_exams)
        avg_percentage = (
            (total_marks_obtained * 100 / total_possible_marks) 
            if total_possible_marks > 0 else 0
        )
        
        student_performance.append({
            'student': student,
            'average': round(avg_percentage, 2),
            'exam_count': count_unique_exams(student_exams),
            'total_marks_obtained': round(total_marks_obtained, 2),
            'total_possible_marks': round(total_possible_marks, 2)
        })
    
    student_performance = sorted(student_performance, key=lambda x: x['average'], reverse=True)
    
    # Calculate excellence rate: (Number of Excellent Exams / Total Exams) × 100%
    # CQ Excellence Threshold: ≥ 80%
    # MCQ Excellence Threshold: ≥ 85%
    excellent_exams = 0
    total_exams_count = 0
    
    for exam in exams:
        total_exams_count += 1
        # Check if exam meets excellence threshold
        exam_type_name = exam.exam_type.name.upper().strip()
        if exam_type_name == 'CQ' and exam.percentage >= 80:
            excellent_exams += 1
        elif exam_type_name == 'MCQ' and exam.percentage >= 85:
            excellent_exams += 1
    
    excellence_rate = (excellent_exams / total_exams_count * 100) if total_exams_count > 0 else 0
    
    # Calculate CQ and MCQ statistics
    cq_exams = exams.filter(exam_type__name__iexact='CQ')
    mcq_exams = exams.filter(exam_type__name__iexact='MCQ')
    
    # CQ Statistics
    cq_stats = {
        'exam_count': count_unique_exams(cq_exams),  # Use unique count
        'total_marks_obtained': 0,
        'total_marks_possible': 0,
        'average': 0,
        'excellence_rate': 0,
        'best_student': None,
    }
    
    if cq_exams.exists():
        cq_stats['total_marks_obtained'] = sum(float(e.mark_obtained) for e in cq_exams)
        cq_stats['total_marks_possible'] = sum(float(e.total_marks) for e in cq_exams)
        cq_stats['average'] = (cq_stats['total_marks_obtained'] * 100 / cq_stats['total_marks_possible']) if cq_stats['total_marks_possible'] > 0 else 0
        
        # CQ Excellence Rate (≥80%)
        cq_excellent = sum(1 for e in cq_exams if e.percentage >= 80)
        cq_total_count = cq_exams.count()  # Use total count for excellence rate
        cq_stats['excellence_rate'] = (cq_excellent / cq_total_count * 100) if cq_total_count > 0 else 0
        
        # Find best CQ student
        cq_student_avgs = {}
        for student in students:
            student_cq = student.exam_set.filter(subject=subject, exam_type__name__iexact='CQ')
            if student_cq.exists():
                cq_marks = sum(float(e.mark_obtained) for e in student_cq)
                cq_total = sum(float(e.total_marks) for e in student_cq)
                cq_student_avgs[student] = (cq_marks * 100 / cq_total) if cq_total > 0 else 0
        
        if cq_student_avgs:
            cq_stats['best_student'] = max(cq_student_avgs, key=cq_student_avgs.get)
    
    # MCQ Statistics
    mcq_stats = {
        'exam_count': count_unique_exams(mcq_exams),  # Use unique count
        'total_marks_obtained': 0,
        'total_marks_possible': 0,
        'average': 0,
        'excellence_rate': 0,
        'best_student': None,
    }
    
    if mcq_exams.exists():
        mcq_stats['total_marks_obtained'] = sum(float(e.mark_obtained) for e in mcq_exams)
        mcq_stats['total_marks_possible'] = sum(float(e.total_marks) for e in mcq_exams)
        mcq_stats['average'] = (mcq_stats['total_marks_obtained'] * 100 / mcq_stats['total_marks_possible']) if mcq_stats['total_marks_possible'] > 0 else 0
        
        # MCQ Excellence Rate (≥85%)
        mcq_excellent = sum(1 for e in mcq_exams if e.percentage >= 85)
        mcq_total_count = mcq_exams.count()  # Use total count for excellence rate
        mcq_stats['excellence_rate'] = (mcq_excellent / mcq_total_count * 100) if mcq_total_count > 0 else 0
        
        # Find best MCQ student
        mcq_student_avgs = {}
        for student in students:
            student_mcq = student.exam_set.filter(subject=subject, exam_type__name__iexact='MCQ')
            if student_mcq.exists():
                mcq_marks = sum(float(e.mark_obtained) for e in student_mcq)
                mcq_total = sum(float(e.total_marks) for e in student_mcq)
                mcq_student_avgs[student] = (mcq_marks * 100 / mcq_total) if mcq_total > 0 else 0
        
        if mcq_student_avgs:
            mcq_stats['best_student'] = max(mcq_student_avgs, key=mcq_student_avgs.get)
    
    # Get recent exams for this subject
    recent_exams = exams.order_by('-date', '-exam_id')[:10]
    
    context = {
        'subject': subject,
        'average_marks': subject.average_marks,
        'total_exams': count_unique_exams(exams),
        'best_student': best_student,
        'student_performance': student_performance,
        'excellence_rate': round(excellence_rate, 1),
        'cq_stats': cq_stats,
        'mcq_stats': mcq_stats,
        'recent_exams': recent_exams,
        'is_student': is_student(request.user),
    }
    
    return render(request, 'marks/subject_detail.html', context)


@login_required(login_url='login')
def add_student(request):
    """Add a new student with login credentials"""
    from django.contrib.auth.models import User
    
    # Check if user is a teacher
    teacher_check = is_teacher(request.user)
    
    if request.method == 'POST' and teacher_check:
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        roll = request.POST.get('roll')
        class_number = request.POST.get('class_number')
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Validate all required fields
        if not all([first_name, roll, class_number, username, password, confirm_password]):
            messages.error(request, 'All required fields must be filled!')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match!')
        elif len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters!')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'This username is already taken. Please choose another.')
        else:
            try:
                # Create user account
                user = User.objects.create_user(
                    username=username,
                    password=password
                )
                
                # Create student record with teacher assignment
                student = Student.objects.create(
                    first_name=first_name,
                    last_name=last_name if last_name else "",
                    roll=roll,
                    class_name=str(class_number),
                    teacher=request.user
                )
                
                # Create student profile linking user to student
                StudentProfile.objects.create(
                    user=user,
                    student=student,
                    created_by=request.user
                )
                
                return redirect('student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f'Error creating student: {str(e)}')
    
    return render(request, 'marks/add_student_new.html', {'is_teacher': teacher_check})


@login_required(login_url='login')
def edit_student(request, student_id):
    """Edit student personal information and credentials"""
    from django.contrib.auth.models import User
    
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can edit students.')
        return redirect('dashboard')
    
    teacher = request.user
    student = get_object_or_404(Student, id=student_id, teacher=teacher)
    
    # Get the student's user account if it exists
    student_user = None
    if hasattr(student, 'user_profile'):
        student_user = student.user_profile.user
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        roll = request.POST.get('roll')
        class_number = request.POST.get('class_number')
        username = request.POST.get('username')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # Validate required fields
        if not all([first_name, roll, class_number]):
            messages.error(request, 'First name, roll, and class are required!')
        else:
            try:
                # Update student info
                student.first_name = first_name
                student.last_name = last_name or None
                student.roll = roll
                student.class_name = str(class_number)
                student.save()
                
                # Update user credentials if provided
                if student_user:
                    # Update username if changed
                    if username and username != student_user.username:
                        if User.objects.filter(username=username).exclude(id=student_user.id).exists():
                            messages.error(request, 'This username is already taken.')
                            return redirect('edit_student', student_id=student_id)
                        student_user.username = username
                        student_user.save()
                    
                    # Update password if provided
                    if new_password:
                        if new_password != confirm_password:
                            messages.error(request, 'Passwords do not match!')
                            return redirect('edit_student', student_id=student_id)
                        if len(new_password) < 6:
                            messages.error(request, 'Password must be at least 6 characters!')
                            return redirect('edit_student', student_id=student_id)
                        student_user.set_password(new_password)
                        student_user.save()
                
                return redirect('student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f'Error updating student: {str(e)}')
    
    context = {
        'student': student,
        'student_user': student_user,
        'is_teacher': True,
    }
    return render(request, 'marks/edit_student.html', context)


@login_required(login_url='login')
def add_subject(request):
    """Add a new subject and show already added subjects for the current teacher"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can add subjects.')
        return redirect('dashboard')

    # Get all subjects for the current teacher
    subjects = Subject.objects.filter(teacher=request.user).order_by('-created_at')

    if request.method == 'POST':
        name = request.POST.get('name')
        short_name = request.POST.get('short_name')
        if name and short_name:
            subject = Subject.objects.create(name=name, short_name=short_name, teacher=request.user)
            return redirect('subject_list')
        else:
            messages.error(request, 'Both subject name and short name are required!')

    # Check if running on production (non-localhost)
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))

    context = {
        'subjects': subjects,
        'is_production': is_production,
    }
    return render(request, 'marks/add_subject.html', context)


@login_required(login_url='login')
def edit_subject(request):
    """Edit an existing subject"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can edit subjects.')
        return redirect('dashboard')

    if request.method == 'POST':
        subject_id = request.POST.get('subject_id')
        name = request.POST.get('name')
        short_name = request.POST.get('short_name')

        try:
            subject = Subject.objects.get(id=subject_id, teacher=request.user)
            subject.name = name
            subject.short_name = short_name
            subject.save()

            return redirect('add_subject')
        except Subject.DoesNotExist:
            messages.error(request, 'Subject not found or you do not have permission to edit it.')
        except Exception as e:
            messages.error(request, f'Error updating subject: {str(e)}')

    return redirect('add_subject')




@login_required(login_url='login')
def add_exam(request):
    """Add a new exam"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can add exams.')
        return redirect('dashboard')
    
    teacher = request.user
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject_id = request.POST.get('subject')
        exam_type_name = request.POST.get('exam_type')  # Now it's CQ or MCQ string
        date = request.POST.get('date')
        chapter = request.POST.get('chapter')
        class_number = request.POST.get('class_number')
        total_marks = request.POST.get('total_marks')
        mark_obtained = request.POST.get('mark_obtained')
        question_pdf = request.FILES.get('question_pdf')
        marked_answer_paper = request.FILES.get('marked_answer_paper')
        
        exam_id = request.POST.get('exam_id')
        if all([student_id, subject_id, exam_type_name, date, chapter, class_number, total_marks, mark_obtained, exam_id]):
            try:
                # Ensure student belongs to this teacher
                student = Student.objects.get(id=student_id, teacher=teacher)
                subject = Subject.objects.get(id=subject_id, teacher=teacher)
                # Get or create exam type (CQ or MCQ) for this teacher
                exam_type, created = ExamType.objects.get_or_create(name=exam_type_name, teacher=teacher)
                # Convert to integers
                class_number = int(class_number)
                total_marks = int(total_marks)
                mark_obtained = int(mark_obtained)
                exam_id = int(exam_id)
                exam = Exam.objects.create(
                    student=student,
                    subject=subject,
                    exam_type=exam_type,
                    teacher=teacher,
                    date=date,
                    chapter=chapter,
                    class_number=class_number,
                    total_marks=total_marks,
                    mark_obtained=mark_obtained,
                    exam_id=exam_id,
                    question_pdf=question_pdf,
                    marked_answer_paper=marked_answer_paper
                )
                return redirect('student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f'Error adding exam: {str(e)}')
        else:
            messages.error(request, 'All required fields must be filled!')
    
    # Filter students and subjects by teacher
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    exam_types = ExamType.objects.filter(teacher=teacher).order_by('name')
    
    # Check if running on production (non-localhost)
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'students': students,
        'subjects': subjects,
        'exam_types': exam_types,
        'is_production': is_production,
    }
    
    return render(request, 'marks/add_exam.html', context)


@login_required(login_url='login')
def add_bulk_exam(request):
    """Add exam for multiple students at once"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can add exams.')
        return redirect('dashboard')
    
    teacher = request.user
    student_count = None
    
    if request.method == 'POST':
        # Check if this is step 1 (getting student count) or step 2 (submitting exams)
        if request.POST.get('submit_exams'):
            # Step 2: Process and save all exams
            student_count = int(request.POST.get('student_count'))
            subject_id = request.POST.get('subject')
            exam_type_name = request.POST.get('exam_type')  # Now it's CQ or MCQ string
            date = request.POST.get('date')
            chapter = request.POST.get('chapter')
            class_number = request.POST.get('class_number')
            total_marks = request.POST.get('total_marks')
            question_pdf = request.FILES.get('question_pdf')
            
            exam_id = request.POST.get('exam_id')
            if all([subject_id, exam_type_name, date, chapter, class_number, total_marks, exam_id]):
                try:
                    # Ensure subject belongs to this teacher
                    subject = Subject.objects.get(id=subject_id, teacher=teacher)
                    # Get or create exam type (CQ or MCQ) for this teacher
                    exam_type, created = ExamType.objects.get_or_create(name=exam_type_name, teacher=teacher)
                    class_number = int(class_number)
                    total_marks = int(total_marks)
                    exam_id = int(exam_id)
                    # Generate unique group ID for this exam session
                    import uuid
                    from datetime import datetime
                    group_id = f"bulk_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
                    # Create exams for all students
                    created_count = 0
                    for i in range(1, student_count + 1):
                        student_id = request.POST.get(f'student_{i}')
                        mark_obtained = request.POST.get(f'marks_{i}')
                        marked_answer_paper = request.FILES.get(f'marked_answer_{i}')
                        if student_id and mark_obtained:
                            # Ensure student belongs to this teacher
                            student = Student.objects.get(id=student_id, teacher=teacher)
                            mark_obtained = int(mark_obtained)
                            Exam.objects.create(
                                student=student,
                                subject=subject,
                                exam_type=exam_type,
                                teacher=teacher,
                                date=date,
                                chapter=chapter,
                                class_number=class_number,
                                total_marks=total_marks,
                                mark_obtained=mark_obtained,
                                group_id=group_id,
                                exam_id=exam_id,
                                question_pdf=question_pdf,
                                marked_answer_paper=marked_answer_paper
                            )
                            created_count += 1
                    return redirect('all_exams')
                except Exception as e:
                    messages.error(request, f'Error adding exams: {str(e)}')
            else:
                messages.error(request, 'All required fields must be filled!')
        else:
            # Step 1: Get student count and show the form
            student_count_str = request.POST.get('student_count')
            if student_count_str:
                student_count = int(student_count_str)
    
    # Filter students and subjects by teacher
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    exam_types = ExamType.objects.filter(teacher=teacher).order_by('name')
    
    # Check if running on production (non-localhost)
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'students': students,
        'subjects': subjects,
        'exam_types': exam_types,
        'student_count': student_count,
        'student_range': range(1, student_count + 1) if student_count else [],
        'is_production': is_production,
    }
    
    return render(request, 'marks/add_bulk_exam.html', context)


@login_required(login_url='login')
def edit_exam(request, exam_id):
    """Edit an existing exam result"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can edit exams.')
        return redirect('dashboard')
    
    teacher = request.user
    exam = get_object_or_404(Exam, id=exam_id, teacher=teacher)
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject_id = request.POST.get('subject')
        exam_type_name = request.POST.get('exam_type')
        date = request.POST.get('date')
        chapter = request.POST.get('chapter')
        class_number = request.POST.get('class_number')
        total_marks = request.POST.get('total_marks')
        mark_obtained = request.POST.get('mark_obtained')
        exam_id_new = request.POST.get('exam_id')
        question_pdf = request.FILES.get('question_pdf')
        
        if all([student_id, subject_id, exam_type_name, date, chapter, class_number, total_marks, mark_obtained, exam_id_new]):
            try:
                # Ensure student and subject belong to this teacher
                student = Student.objects.get(id=student_id, teacher=teacher)
                subject = Subject.objects.get(id=subject_id, teacher=teacher)
                exam_type, created = ExamType.objects.get_or_create(name=exam_type_name, teacher=teacher)
                
                # Update exam
                exam.student = student
                exam.subject = subject
                exam.exam_type = exam_type
                exam.date = date
                exam.chapter = chapter
                exam.class_number = int(class_number)
                exam.total_marks = int(total_marks)
                exam.mark_obtained = int(mark_obtained)
                exam.exam_id = int(exam_id_new)
                
                if question_pdf:
                    exam.question_pdf = question_pdf
                
                exam.save()
                
                # Recalculate student's lifetime points
                exam.student.recalculate_lifetime_points()
                
                return redirect('all_exams')
            except Exception as e:
                messages.error(request, f'Error updating exam: {str(e)}')
        else:
            messages.error(request, 'All required fields must be filled!')
    
    # Get teacher's students and subjects for dropdowns
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    exam_types = ExamType.objects.filter(teacher=teacher).order_by('name')
    
    # Check if running on production
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'exam': exam,
        'students': students,
        'subjects': subjects,
        'exam_types': exam_types,
        'is_production': is_production,
    }
    
    return render(request, 'marks/edit_exam.html', context)


# API endpoints for chart data
@login_required(login_url='login')
def api_marks_over_time(request, student_id):
    """API endpoint for marks over time chart data"""
    data = ChartDataService.marks_over_time(student_id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_subject_performance(request, student_id):
    """API endpoint for subject performance chart data"""
    data = ChartDataService.subject_performance_chart(student_id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_grade_distribution(request, student_id):
    """API endpoint for grade distribution chart data"""
    data = ChartDataService.grade_distribution_chart(student_id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_student_comparison(request, subject_id):
    """API endpoint for student comparison chart data"""
    data = ChartDataService.student_comparison_chart(subject_id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_overall_grade_distribution(request):
    """API endpoint for overall grade distribution chart data"""
    teacher = get_teacher_for_user(request.user)
    data = ChartDataService.overall_grade_distribution(teacher=teacher)
    return JsonResponse(data)


@login_required(login_url='login')
def all_exams(request):
    """Display all exam entries in detail - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    exams = Exam.objects.filter(teacher=teacher).select_related('student', 'subject', 'exam_type').order_by('-date', '-exam_id')
    
    # Get filter parameters
    student_filter = request.GET.get('student')
    subject_filter = request.GET.get('subject')
    exam_type_filter = request.GET.get('exam_type')
    class_filter = request.GET.get('class_number')
    month_filter = request.GET.get('month')
    chapter_filter = request.GET.get('chapter')
    exam_id_from = request.GET.get('exam_id_from')
    exam_id_to = request.GET.get('exam_id_to')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    # Apply filters
    if student_filter:
        exams = exams.filter(student_id=student_filter)
    if subject_filter:
        exams = exams.filter(subject_id=subject_filter)
    if exam_type_filter:
        # Filter by exam type name (CQ or MCQ)
        exams = exams.filter(exam_type__name=exam_type_filter)
    if class_filter:
        exams = exams.filter(class_number=class_filter)
    if month_filter:
        # month_filter format: "YYYY-MM"
        year, month = month_filter.split('-')
        exams = exams.filter(date__year=year, date__month=month)
    if chapter_filter:
        exams = exams.filter(chapter__icontains=chapter_filter)
    if exam_id_from:
        exams = exams.filter(exam_id__gte=exam_id_from)
    if exam_id_to:
        exams = exams.filter(exam_id__lte=exam_id_to)
    if date_from:
        exams = exams.filter(date__gte=date_from)
    if date_to:
        exams = exams.filter(date__lte=date_to)
    
    # Count unique exams and total records
    unique_exams_count = count_unique_exams(exams)
    total_records_count = exams.count()
    
    # Calculate statistics
    average_percentage = 0
    highest_percentage = 0
    lowest_percentage = 0
    
    if exams.exists():
        total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
        total_possible_marks = sum(float(e.total_marks) for e in exams)
        average_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
        highest_percentage = max(exam.percentage for exam in exams)
        lowest_percentage = min(exam.percentage for exam in exams)
    
    # Get all options for filters (filtered by teacher)
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    exam_types = ExamType.objects.filter(teacher=teacher).order_by('name')
    
    # Generate available months from teacher's exam dates
    from datetime import datetime
    teacher_exam_dates = Exam.objects.filter(teacher=teacher).values_list('date', flat=True).distinct()
    months_set = set()
    for exam_date in teacher_exam_dates:
        if exam_date:
            months_set.add((exam_date.year, exam_date.month))
    
    # Sort months in descending order (most recent first)
    sorted_months = sorted(months_set, reverse=True)
    available_months = []
    month_names = ['January', 'February', 'March', 'April', 'May', 'June', 
                   'July', 'August', 'September', 'October', 'November', 'December']
    
    for year, month in sorted_months:
        available_months.append({
            'value': f'{year}-{month:02d}',
            'label': f'{month_names[month-1]} {year}'
        })
    
    context = {
        'exams': exams,
        'unique_exams_count': unique_exams_count,
        'total_records_count': total_records_count,
        'students': students,
        'subjects': subjects,
        'exam_types': exam_types,
        'available_months': available_months,
        'average_percentage': average_percentage,
        'highest_percentage': highest_percentage,
        'lowest_percentage': lowest_percentage,
        'is_student': is_student(request.user),
    }
    
    return render(request, 'marks/all_exams.html', context)


@login_required(login_url='login')
def points(request):
    """Points management page with history and summary - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    
    # Get all students for filters (filtered by teacher)
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    
    # Get points spent history with filters (filtered by teacher)
    points_history = PointsSpent.objects.filter(teacher=teacher).select_related('student')
    
    # Apply filters from GET parameters
    student_filter = request.GET.get('student')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    min_spent = request.GET.get('min_spent')
    
    if student_filter:
        points_history = points_history.filter(student_id=student_filter)
    if from_date:
        points_history = points_history.filter(date__gte=from_date)
    if to_date:
        points_history = points_history.filter(date__lte=to_date)
    if min_spent:
        points_history = points_history.filter(points_spent__gte=int(min_spent))
    
    # Calculate statistics for filtered records
    total_points_spent = 0
    average_spent = 0
    highest_spent = 0
    lowest_spent = 0
    
    if points_history.exists():
        total_points_spent = sum(record.points_spent for record in points_history)
        average_spent = total_points_spent / points_history.count()
        highest_spent = max(record.points_spent for record in points_history)
        lowest_spent = min(record.points_spent for record in points_history)
    
    # Get student points summary (filtered by teacher)
    student_summary = []
    for student in Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name'):
        lifetime_points, created = LifetimePoints.objects.get_or_create(student=student)
        student_summary.append({
            'student': student,
            'points_earned': lifetime_points.points_earned,
            'points_spent': lifetime_points.points_spent,
            'points_remaining': lifetime_points.points_remaining
        })
    
    # Sort by points earned descending
    student_summary.sort(key=lambda x: x['points_earned'], reverse=True)
    
    context = {
        'students': students,
        'points_history': points_history,
        'student_summary': student_summary,
        'total_points_spent': total_points_spent,
        'average_spent': average_spent,
        'highest_spent': highest_spent,
        'lowest_spent': lowest_spent,
    }
    
    return render(request, 'marks/points.html', context)


@login_required(login_url='login')
def add_points_spent(request):
    """Form to record points spent by a student"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can record points spent.')
        return redirect('dashboard')
    
    teacher = request.user
    
    if request.method == 'POST':
        student_id = request.POST.get('student')
        points_spent = request.POST.get('points_spent')
        description = request.POST.get('description')
        date = request.POST.get('date')
        
        try:
            # Ensure student belongs to this teacher
            student = Student.objects.get(id=student_id, teacher=teacher)
            points_spent = int(points_spent)
            
            # Get or create lifetime points for validation
            lifetime_points, created = LifetimePoints.objects.get_or_create(student=student)
            
            # Validate points
            if points_spent <= 0:
                messages.error(request, 'Points spent must be greater than 0.')
            elif points_spent > lifetime_points.points_remaining:
                messages.error(request, f'{student.name} only has {lifetime_points.points_remaining} points remaining.')
            else:
                # Create the points spent record with teacher
                PointsSpent.objects.create(
                    student=student,
                    teacher=teacher,
                    points_spent=points_spent,
                    description=description[:15],  # Enforce max 15 characters
                    date=date
                )
                return redirect('points')
        except Student.DoesNotExist:
            messages.error(request, 'Student not found.')
        except ValueError:
            messages.error(request, 'Invalid points value.')
    
    # Get all students for the form (filtered by teacher)
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    
    context = {
        'students': students,
    }
    
    return render(request, 'marks/add_points_spent.html', context)


@login_required(login_url='login')
def leaderboard(request):
    """Leaderboard page with overall, subject-wise, and monthly rankings - filtered by teacher"""
    from django.db.models import Avg, Count, Max, Sum
    from datetime import datetime
    
    teacher = get_teacher_for_user(request.user)
    
    # Get class filter from request (default to 'all')
    class_filter = request.GET.get('class_number', 'all')
    
    # Get available class numbers (only classes with actual exam records, filtered by teacher)
    try:
        available_classes = list(
            Exam.objects.filter(teacher=teacher)
            .exclude(class_number__isnull=True)
            .values_list('class_number', flat=True)
            .distinct()
            .order_by('class_number')
        )
        # Filter out any None or empty values
        available_classes = [c for c in available_classes if c is not None]
    except (ValueError, TypeError):
        available_classes = []
    
    # Overall Rankings (filtered by teacher)
    overall_rankings = []
    students = Student.objects.filter(teacher=teacher)
    
    for student in students:
        # Filter exams by class if specified
        if class_filter != 'all':
            exams = student.exam_set.filter(class_number=int(class_filter))
            if not exams.exists():
                continue

            total_exams = student._count_unique_exams(exams)
            if total_exams > 0:
                # Calculate excellence rate (CQ >=80%, MCQ >=85%)
                excellent_exams = 0
                exam_points = 0
                for exam in exams:
                    percentage = exam.percentage
                    exam_type_name = exam.exam_type.name.upper().strip()
                    exam_points += exam.points_earned
                    if exam_type_name == "MCQ" and percentage >= 85:
                        excellent_exams += 1
                    elif exam_type_name == "CQ" and percentage >= 80:
                        excellent_exams += 1

                # Calculate monthly wins for this class filter
                from datetime import date
                current_year = date.today().year
                current_month = date.today().month
                months_set = set()
                exam_dates = exams.values_list('date', flat=True).distinct()
                for exam_date in exam_dates:
                    if exam_date:
                        if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                            months_set.add((exam_date.year, exam_date.month))

                monthly_wins = 0
                for year, month in months_set:
                    month_exams = exams.filter(date__year=year, date__month=month)
                    if not month_exams.exists():
                        continue
                    students_in_month = Student.objects.filter(teacher=teacher, exam__class_number=exams.first().class_number, exam__date__year=year, exam__date__month=month).distinct()
                    month_rankings = []
                    for s in students_in_month:
                        s_month_exams = s.exam_set.filter(class_number=exams.first().class_number, date__year=year, date__month=month)
                        total_marks = sum(float(e.mark_obtained) for e in s_month_exams)
                        total_possible = sum(float(e.total_marks) for e in s_month_exams)
                        avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
                        month_rankings.append({
                            'student_id': s.id,
                            'average_percentage': avg_percentage,
                            'total_marks': total_marks,
                        })
                    month_rankings.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
                    if month_rankings:
                        top_avg = month_rankings[0]['average_percentage']
                        top_total = month_rankings[0]['total_marks']
                        for ranking in month_rankings:
                            if ranking['student_id'] == student.id:
                                if (abs(ranking['average_percentage'] - top_avg) < 0.01 and ranking['total_marks'] == top_total):
                                    monthly_wins += 1
                                break

                bonus_points = monthly_wins * 40
                total_points = exam_points + bonus_points
                excellence_rate = (excellent_exams / total_exams) * 100
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0

                overall_rankings.append({
                    'student': student,
                    'total_exams': total_exams,
                    'average_percentage': avg_percentage,
                    'total_points': total_points,
                    'excellence_rate': excellence_rate,
                })
        else:
            exams = student.exam_set.all()
            if not exams.exists():
                continue
            total_exams = student._count_unique_exams(exams)
            if total_exams > 0:
                # Calculate excellence rate (CQ >=80%, MCQ >=85%)
                excellent_exams = 0
                for exam in exams:
                    percentage = exam.percentage
                    exam_type_name = exam.exam_type.name.upper().strip()
                    if exam_type_name == "MCQ" and percentage >= 85:
                        excellent_exams += 1
                    elif exam_type_name == "CQ" and percentage >= 80:
                        excellent_exams += 1
                excellence_rate = (excellent_exams / total_exams) * 100
                # Use lifetime points (precomputed, includes all monthly wins)
                lifetime_points_obj = LifetimePoints.objects.filter(student=student).first()
                total_points = lifetime_points_obj.points_earned if lifetime_points_obj else 0
                total_marks_obtained = sum(float(e.mark_obtained) for e in exams)
                total_possible_marks = sum(float(e.total_marks) for e in exams)
                avg_percentage = (total_marks_obtained * 100 / total_possible_marks) if total_possible_marks > 0 else 0
                overall_rankings.append({
                    'student': student,
                    'total_exams': total_exams,
                    'average_percentage': avg_percentage,
                    'total_points': total_points,
                    'excellence_rate': excellence_rate,
                })
    
    # Sort by average score (primary), then total marks (tie-breaker)
    overall_rankings.sort(key=lambda x: (x['average_percentage'], x['total_points']), reverse=True)
    
    # Add ranks with tie handling
    current_rank = 1
    for idx, item in enumerate(overall_rankings):
        if idx > 0:
            prev = overall_rankings[idx - 1]
            # If same score AND same total marks, keep same rank
            if (abs(item['average_percentage'] - prev['average_percentage']) < 0.01 and
                item['total_points'] == prev['total_points']):
                item['rank'] = current_rank  # Share rank
            else:
                current_rank = idx + 1
                item['rank'] = current_rank
        else:
            item['rank'] = 1
    
    # Subject-wise Leaders (filtered by teacher)
    subject_leaders = []
    subjects = Subject.objects.filter(teacher=teacher)
    
    for subject in subjects:
        leaders = []
        
        # Filter by class if specified (teacher-scoped)
        if class_filter != 'all':
            students_in_subject = Student.objects.filter(
                teacher=teacher,
                exam__subject=subject,
                exam__class_number=int(class_filter)
            ).distinct()
        else:
            students_in_subject = Student.objects.filter(teacher=teacher, exam__subject=subject).distinct()
        
        for student in students_in_subject:
            # Filter exams by class
            if class_filter != 'all':
                exams = student.exam_set.filter(subject=subject, class_number=int(class_filter))
            else:
                exams = student.exam_set.filter(subject=subject)
                
            from .services import count_unique_exams
            exams_count = count_unique_exams(exams)
            
            if exams_count > 0:
                total_marks = sum(float(e.mark_obtained) for e in exams)
                total_possible = sum(float(e.total_marks) for e in exams)
                avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
                best_score = max(e.percentage for e in exams)
                
                leaders.append({
                    'student': student,
                    'exams_count': exams_count,
                    'total_marks': total_marks,  # Add for tie-breaking
                    'average_percentage': avg_percentage,
                    'best_score': best_score,
                })
        
        # Sort by average score (primary), then total marks (tie-breaker)
        leaders.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
        
        # Add ranks with tie handling
        current_rank = 1
        for idx, leader in enumerate(leaders):
            if idx > 0:
                prev = leaders[idx - 1]
                # If same score AND same total marks, keep same rank
                if (abs(leader['average_percentage'] - prev['average_percentage']) < 0.01 and
                    leader['total_marks'] == prev['total_marks']):
                    leader['rank'] = current_rank  # Share rank
                else:
                    current_rank = idx + 1
                    leader['rank'] = current_rank
            else:
                leader['rank'] = 1
        
        subject_leaders.append({
            'subject': subject,
            'leaders': leaders[:5],  # Top 5 per subject
        })
    
    # Monthly Champions (exclude current month) - filtered by teacher
    monthly_champions = []
    
    # Get all unique year-month combinations from exams (only past months)
    from datetime import date as date_type
    current_year = date_type.today().year
    current_month = date_type.today().month
    
    # Filter exam dates by class and teacher
    if class_filter != 'all':
        exam_dates = Exam.objects.filter(teacher=teacher, class_number=int(class_filter)).values_list('date', flat=True).distinct()
    else:
        exam_dates = Exam.objects.filter(teacher=teacher).values_list('date', flat=True).distinct()
    
    months_set = set()
    
    for date in exam_dates:
        if date:
            # Only include months that have fully passed
            if (date.year < current_year) or (date.year == current_year and date.month < current_month):
                months_set.add((date.year, date.month))
    
    # Sort months in descending order (most recent first)
    sorted_months = sorted(months_set, reverse=True)
    
    for year, month in sorted_months:
        month_name = datetime(year, month, 1).strftime('%B %Y')
        champions = []
        
        # Get all students who had exams in this month (with class filter, teacher-scoped)
        if class_filter != 'all':
            students_in_month = Student.objects.filter(
                teacher=teacher,
                exam__date__year=year,
                exam__date__month=month,
                exam__class_number=int(class_filter)
            ).distinct()
        else:
            students_in_month = Student.objects.filter(
                teacher=teacher,
                exam__date__year=year,
                exam__date__month=month
            ).distinct()
        
        for student in students_in_month:
            # Filter by class
            if class_filter != 'all':
                exams = student.exam_set.filter(
                    date__year=year,
                    date__month=month,
                    class_number=int(class_filter)
                )
            else:
                exams = student.exam_set.filter(date__year=year, date__month=month)
                
            from .services import count_unique_exams
            exams_count = count_unique_exams(exams)
            
            if exams_count > 0:
                total_marks = sum(float(e.mark_obtained) for e in exams)
                total_marks = sum(float(e.mark_obtained) for e in exams)
                total_possible = sum(float(e.total_marks) for e in exams)
                avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
                points_earned = sum(e.points_earned for e in exams)
                
                champions.append({
                    'student': student,
                    'exams_count': exams_count,
                    'total_marks': total_marks,  # Add for tie-breaking
                    'average_percentage': avg_percentage,
                    'points_earned': points_earned,
                })
        
        # Sort by average score (primary), then total marks (tie-breaker)
        champions.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
        
        # Add ranks with tie handling
        current_rank = 1
        for idx, champion in enumerate(champions):
            if idx > 0:
                prev = champions[idx - 1]
                # If same score AND same total marks, keep same rank
                if (abs(champion['average_percentage'] - prev['average_percentage']) < 0.01 and
                    champion['total_marks'] == prev['total_marks']):
                    champion['rank'] = current_rank  # Share rank
                else:
                    current_rank = idx + 1
                    champion['rank'] = current_rank
            else:
                champion['rank'] = 1
        
        monthly_champions.append({
            'month_name': month_name,
            'year': year,
            'month': month,
            'champions': champions[:5],  # Top 5 per month
        })
    
    # Current Month Top Performers (separate from monthly champions)
    current_month_performers = []
    month_name = datetime(current_year, current_month, 1).strftime('%B %Y')
    
    # Get all students who have exams in the current month (with class filter, teacher-scoped)
    if class_filter != 'all':
        students_current_month = Student.objects.filter(
            teacher=teacher,
            exam__date__year=current_year,
            exam__date__month=current_month,
            exam__class_number=int(class_filter)
        ).distinct()
    else:
        students_current_month = Student.objects.filter(
            teacher=teacher,
            exam__date__year=current_year,
            exam__date__month=current_month
        ).distinct()
    
    for student in students_current_month:
        # Filter by class
        if class_filter != 'all':
            exams = student.exam_set.filter(
                date__year=current_year,
                date__month=current_month,
                class_number=int(class_filter)
            )
        else:
            exams = student.exam_set.filter(date__year=current_year, date__month=current_month)
            
        from .services import count_unique_exams
        exams_count = count_unique_exams(exams)
        
        if exams_count > 0:
            total_marks = sum(float(e.mark_obtained) for e in exams)
            total_possible = sum(float(e.total_marks) for e in exams)
            avg_percentage = (total_marks * 100 / total_possible) if total_possible > 0 else 0
            points_earned = sum(e.points_earned for e in exams)
            
            current_month_performers.append({
                'student': student,
                'exams_count': exams_count,
                'total_marks': total_marks,
                'average_percentage': avg_percentage,
                'points_earned': points_earned,
            })
    
    # Sort by average score (primary), then total marks (tie-breaker)
    current_month_performers.sort(key=lambda x: (x['average_percentage'], x['total_marks']), reverse=True)
    
    # Add ranks with tie handling
    current_rank = 1
    for idx, performer in enumerate(current_month_performers):
        if idx > 0:
            prev = current_month_performers[idx - 1]
            # If same score AND same total marks, keep same rank
            if (abs(performer['average_percentage'] - prev['average_percentage']) < 0.01 and
                performer['total_marks'] == prev['total_marks']):
                performer['rank'] = current_rank  # Share rank
            else:
                current_rank = idx + 1
                performer['rank'] = current_rank
        else:
            performer['rank'] = 1
    
    context = {
        'overall_rankings': overall_rankings,
        'subject_leaders': subject_leaders,
        'monthly_champions': monthly_champions,
        'current_month_performers': current_month_performers[:5],  # Top 5 for current month
        'current_month_name': month_name,
        'available_classes': available_classes,
        'selected_class': class_filter,
    }
    
    return render(request, 'marks/leaderboard.html', context)


def guide(request):
    """User guide page explaining grading system, points, and terminology"""
    return render(request, 'marks/guide.html')


def about(request):
    """About page with project and developer information"""
    return render(request, 'marks/about.html')


@login_required(login_url='login')
@login_required(login_url='login')
def exam_lookup(request):
    """Mobile-only page for looking up exam PDFs and marked answer papers by exam ID"""
    teacher = get_teacher_for_user(request.user)
    
    # Get exam stats for this teacher
    qs = Exam.objects.filter(teacher=teacher)
    min_exam_id = qs.values_list('exam_id', flat=True).distinct().order_by('exam_id').first()
    max_exam_id = qs.values_list('exam_id', flat=True).distinct().order_by('-exam_id').first()
    total_exams = qs.values('exam_id').distinct().count()
    exams_with_pdf = qs.exclude(question_pdf='').exclude(question_pdf__isnull=True).values('exam_id').distinct().count()
    
    # Calculate marked answer paper stats for students
    exams_with_answer_sheet = 0
    total_student_exams = 0
    
    if is_student(request.user):
        # Get the student record for the logged-in user
        student = request.user.student_profile.student
        student_exams = qs.filter(student=student)
        total_student_exams = student_exams.values('exam_id').distinct().count()
        exams_with_answer_sheet = student_exams.exclude(marked_answer_paper='').exclude(marked_answer_paper__isnull=True).values('exam_id').distinct().count()
    
    # Calculate percentages
    pdf_percentage = round((exams_with_pdf / total_exams * 100), 1) if total_exams > 0 else 0
    answer_sheet_percentage = round((exams_with_answer_sheet / total_student_exams * 100), 1) if total_student_exams > 0 else 0

    context = {
        'min_exam_id': min_exam_id or 'N/A',
        'max_exam_id': max_exam_id or 'N/A',
        'exams_with_pdf': exams_with_pdf,
        'total_exams': total_exams,
        'pdf_percentage': pdf_percentage,
        'exams_with_answer_sheet': exams_with_answer_sheet,
        'total_student_exams': total_student_exams,
        'answer_sheet_percentage': answer_sheet_percentage,
        'is_student': is_student(request.user),
    }
    return render(request, 'marks/exam_lookup.html', context)


@login_required(login_url='login')
def exam_lookup_api(request):
    """API endpoint for fetching exam details by exam ID"""
    exam_id = request.GET.get('exam_id', '').strip()
    
    if not exam_id:
        return JsonResponse({'success': False, 'error': 'Please enter an exam ID'})
    
    # Get current teacher
    teacher = get_teacher_for_user(request.user)
    # Find exam(s) with the given exam_id, filtered by teacher
    exams = Exam.objects.filter(exam_id=exam_id, teacher=teacher).select_related('subject', 'exam_type', 'student')
    
    if not exams.exists():
        return JsonResponse({'success': False, 'error': f'No exam found with ID: {exam_id}'})
    
    # Get the first exam for common details
    first_exam = exams.first()
    
    # Find best performer for this exam
    best_student = None
    best_percentage = 0
    for exam in exams:
        if exam.percentage > best_percentage:
            best_percentage = exam.percentage
            best_student = exam.student
    
    # Get PDF URL if available
    pdf_url = None
    if first_exam.question_pdf:
        pdf_url = first_exam.question_pdf.url
    
    # Get marked answer paper data based on user role
    student_data = None
    all_students_data = []

    if is_student(request.user):
        # Student view - only their own data
        student = request.user.student_profile.student
        student_exam = exams.filter(student=student).first()
        if student_exam:
            student_marks = student_exam.mark_obtained
            student_total = student_exam.total_marks
            student_percentage = round(student_exam.percentage, 1)
            marked_answer_url = student_exam.marked_answer_paper.url if student_exam.marked_answer_paper else None

            student_data = {
                'student_name': student_exam.student.name,
                'marks': student_marks,
                'total_marks': student_total,
                'percentage': student_percentage,
                'has_marked_answer': marked_answer_url is not None,
                'marked_answer_url': marked_answer_url,
            }
    else:
        # Teacher view - all students' data
        for exam in exams:
            marked_answer_url = exam.marked_answer_paper.url if exam.marked_answer_paper else None
            all_students_data.append({
                'student_name': exam.student.name,
                'marks': exam.mark_obtained,
                'total_marks': exam.total_marks,
                'percentage': round(exam.percentage, 1),
                'has_marked_answer': marked_answer_url is not None,
                'marked_answer_url': marked_answer_url,
            })

    # For backward compatibility, keep the old fields for student view
    student_marks = student_data['marks'] if student_data else None
    student_total = student_data['total_marks'] if student_data else None
    student_percentage = student_data['percentage'] if student_data else None
    marked_answer_url = student_data['marked_answer_url'] if student_data else None
    
    return JsonResponse({
        'success': True,
        'exam': {
            'exam_id': first_exam.exam_id,
            'date': first_exam.date.strftime('%B %d, %Y') if first_exam.date else 'N/A',
            'subject': first_exam.subject.name,
            'chapter': first_exam.chapter or 'N/A',
            'exam_type': first_exam.exam_type.name,
            'total_marks': str(first_exam.total_marks),
            'best_student': best_student.name if best_student else 'N/A',
            'best_percentage': round(best_percentage, 1),
            'total_participants': exams.count(),
            'has_pdf': pdf_url is not None,
            'pdf_url': pdf_url,
            'has_marked_answer': marked_answer_url is not None,
            'marked_answer_url': marked_answer_url,
            'student_marks': student_marks,
            'student_total': student_total,
            'student_percentage': student_percentage,
            'student_participated': student_exam is not None if is_student(request.user) else None,
            'is_teacher': not is_student(request.user),
            'all_students_data': all_students_data,
        }
    })


@login_required(login_url='login')
def delete_account(request):
    """
    Multi-step account deletion confirmation flow for teachers.
    Only teachers can delete their accounts, and only their own data is affected.
    """
    # Only teachers can delete accounts
    if not is_teacher(request.user):
        messages.error(request, 'Only teacher accounts can be deleted.')
        return redirect('dashboard')

    teacher = request.user

    if request.method == 'POST':
        step = request.POST.get('step', '1')

        if step == '1':
            # First confirmation step - show warning and ask for confirmation
            return render(request, 'marks/delete_account_confirm.html', {
                'step': 2,
                'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
            })

        elif step == '2':
            # Second confirmation step - require typing account name
            typed_name = request.POST.get('typed_name', '').strip()
            account_name = teacher.get_full_name() or teacher.username

            if typed_name != account_name:
                messages.error(request, f'Account name does not match. Please type "{account_name}" exactly.')
                return render(request, 'marks/delete_account_confirm.html', {
                    'step': 2,
                    'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
                })

            # Show final confirmation with data summary
            # Calculate what will be deleted
            students_count = Student.objects.filter(teacher=teacher).count()
            subjects_count = Subject.objects.filter(teacher=teacher).count()
            exams_count = Exam.objects.filter(teacher=teacher).values('exam_id').distinct().count()
            points_spent_count = PointsSpent.objects.filter(teacher=teacher).count()
            pdfs_count = Exam.objects.filter(teacher=teacher).exclude(question_pdf__isnull=True).exclude(question_pdf='').count()

            return render(request, 'marks/delete_account_confirm.html', {
                'step': 3,
                'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
                'students_count': students_count,
                'subjects_count': subjects_count,
                'exams_count': exams_count,
                'points_spent_count': points_spent_count,
                'pdfs_count': pdfs_count,
            })

        elif step == '3':
            # Final confirmation - perform the deletion
            confirm_text = request.POST.get('confirm_text', '').strip()

            if confirm_text != 'DELETE MY ACCOUNT':
                messages.error(request, 'Please type "DELETE MY ACCOUNT" exactly to confirm.')
                # Recalculate counts and show step 3 again
                students_count = Student.objects.filter(teacher=teacher).count()
                subjects_count = Subject.objects.filter(teacher=teacher).count()
                exams_count = Exam.objects.filter(teacher=teacher).values('exam_id').distinct().count()
                points_spent_count = PointsSpent.objects.filter(teacher=teacher).count()
                pdfs_count = Exam.objects.filter(teacher=teacher).exclude(question_pdf__isnull=True).exclude(question_pdf='').count()

                return render(request, 'marks/delete_account_confirm.html', {
                    'step': 3,
                    'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
                    'students_count': students_count,
                    'subjects_count': subjects_count,
                    'exams_count': exams_count,
                    'points_spent_count': points_spent_count,
                    'pdfs_count': pdfs_count,
                })

            # Perform the actual deletion
            try:
                delete_teacher_account(teacher)
                return redirect('home')
            except Exception as e:
                messages.error(request, f'An error occurred while deleting your account: {str(e)}')
                return redirect('dashboard')

    # Initial step - show first warning
    return render(request, 'marks/delete_account_confirm.html', {
        'step': 1,
        'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
    })


def delete_teacher_account(teacher):
    """
    Safely delete a teacher account and all associated data.
    Only deletes data created by this specific teacher.
    Includes deletion of Cloudinary PDF files uploaded by the teacher.

    Args:
        teacher: User instance representing the teacher

    Raises:
        Exception: If deletion fails at any step
    """
    from django.db import transaction
    from django.contrib.auth import get_user_model
    import cloudinary
    import cloudinary.api

    User = get_user_model()

    with transaction.atomic():
        # Step 0: Delete Cloudinary PDF files uploaded by this teacher
        cloudinary_files_deleted = 0
        try:
            # Get all cloudinary_public_id values for exams created by this teacher
            cloudinary_public_ids = list(
                Exam.objects.filter(teacher=teacher)
                .exclude(cloudinary_public_id__isnull=True)
                .exclude(cloudinary_public_id='')
                .values_list('cloudinary_public_id', flat=True)
                .distinct()
            )

            if cloudinary_public_ids:
                # Delete files from Cloudinary using batch deletion
                # Cloudinary API supports deleting multiple files at once
                delete_result = cloudinary.api.delete_resources(
                    cloudinary_public_ids,
                    resource_type="raw",  # PDFs are stored as raw files
                    type="upload"
                )

                # Count successfully deleted files
                for public_id in cloudinary_public_ids:
                    if public_id in delete_result.get('deleted', {}):
                        status = delete_result['deleted'][public_id]
                        if status == 'deleted':
                            cloudinary_files_deleted += 1

                print(f"Deleted {cloudinary_files_deleted} Cloudinary PDF files for teacher '{teacher.username}'")

        except Exception as e:
            # Log the error but continue with database deletion
            # We don't want Cloudinary issues to prevent account deletion
            print(f"Warning: Failed to delete Cloudinary files for teacher '{teacher.username}': {e}")

        # Step 1: Delete PointsSpent records created by this teacher
        points_spent_deleted, _ = PointsSpent.objects.filter(teacher=teacher).delete()

        # Step 2: Delete Exam records created by this teacher
        # This will also delete related LifetimePoints (via CASCADE)
        exams_deleted, _ = Exam.objects.filter(teacher=teacher).delete()

        # Step 3: Delete ExamType records created by this teacher
        exam_types_deleted, _ = ExamType.objects.filter(teacher=teacher).delete()

        # Step 4: Delete Subject records created by this teacher
        subjects_deleted, _ = Subject.objects.filter(teacher=teacher).delete()

        # Step 5: Get student User accounts before deleting Student records
        # We need to explicitly delete student User accounts since CASCADE might not work properly in transaction
        student_users = list(
            StudentProfile.objects.filter(
                student__teacher=teacher
            ).values_list('user', flat=True)
        )

        # Step 6: Delete Student records created by this teacher
        # This will also delete related StudentProfile and LifetimePoints (via CASCADE)
        students_deleted, _ = Student.objects.filter(teacher=teacher).delete()

        # Step 7: Explicitly delete student User accounts
        student_users_deleted = 0
        for user_id in student_users:
            try:
                User.objects.filter(pk=user_id).delete()
                student_users_deleted += 1
            except Exception as e:
                print(f"Warning: Failed to delete student user {user_id}: {e}")

        # Step 8: Delete the TeacherProfile
        teacher_profile_deleted, _ = TeacherProfile.objects.filter(user=teacher).delete()

        # Step 9: Finally, delete the User account
        # This will cascade to any remaining related objects
        user_deleted, _ = User.objects.filter(pk=teacher.pk).delete()

        # Log the deletion for audit purposes
        print(f"Teacher account '{teacher.username}' deleted successfully. "
              f"Removed: {cloudinary_files_deleted} Cloudinary files, {students_deleted} students, "
              f"{student_users_deleted} student accounts, {subjects_deleted} subjects, {exams_deleted} exams, "
              f"{points_spent_deleted} points records, {exam_types_deleted} exam types, "
              f"{teacher_profile_deleted} profile, {user_deleted} user account.")