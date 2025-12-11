from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Sum, Q
import json
from .models import Student, Subject, ExamType, Exam, GradeScale, LifetimePoints, PointsSpent
from .services import LeaderboardService, DashboardService, ChartDataService, count_unique_exams


def dashboard(request):
    """Main dashboard view with analytics"""
    summary = DashboardService.get_dashboard_summary()
    subject_performance = DashboardService.get_subject_performance_table()
    exam_type_performance = DashboardService.get_exam_type_performance_table()
    grade_distribution = DashboardService.get_grade_distribution()
    recent_exams = DashboardService.get_recent_exams(limit=10)
    
    # Leaderboards
    total_marks_leaderboard = LeaderboardService.total_marks_leaderboard()[:5]
    average_leaderboard = LeaderboardService.average_leaderboard()[:5]
    points_leaderboard = LeaderboardService.lifetime_points_leaderboard()[:5]
    
    # Serialize subject_performance for JavaScript
    subject_performance_json = json.dumps([
        {
            'subject': {'name': item['subject'].name, 'id': item['subject'].id},
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


def student_list(request):
    """List all students"""
    students = Student.objects.all().order_by('name')
    
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


def student_detail(request, student_id):
    """Student profile dashboard"""
    from datetime import datetime
    from django.db.models import Avg, Sum
    
    student = get_object_or_404(Student, id=student_id)
    
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
    
    # Calculate Monthly Winner Count (only past months, #1 positions)
    from datetime import date
    current_year = date.today().year
    current_month = date.today().month
    
    monthly_winner_count = 0
    exam_dates = Exam.objects.values_list('date', flat=True).distinct()
    months_set = set()
    
    for exam_date in exam_dates:
        if exam_date:
            # Only count months that have fully passed
            if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                months_set.add((exam_date.year, exam_date.month))
    
    for year, month in months_set:
        # Get all students who had exams in this month
        students_in_month = Student.objects.filter(
            exam__date__year=year,
            exam__date__month=month
        ).distinct()
        
        month_rankings = []
        for s in students_in_month:
            month_exams = s.exam_set.filter(date__year=year, date__month=month)
            exams_count = month_exams.values('exam_id').distinct().count()
            
            if exams_count > 0:
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
    
    # Calculate Subject Champion Count (how many subjects they've topped)
    subject_champion_count = 0
    subjects = Subject.objects.all()
    
    for subject in subjects:
        students_in_subject = Student.objects.filter(exam__subject=subject).distinct()
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
    
    # Get all other students for comparison dropdown
    all_students = Student.objects.exclude(id=student_id).order_by('name')
    
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


def compare_students(request, student1_id, student2_id):
    """Compare two students side by side"""
    from datetime import date
    
    student1 = get_object_or_404(Student, id=student1_id)
    student2 = None
    if student2_id != 0:
        student2 = get_object_or_404(Student, id=student2_id)
    
    # Get all other students for the dropdown
    all_students = Student.objects.exclude(id=student1_id).order_by('name')
    
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
        
        # Monthly winner count
        current_year = date.today().year
        current_month = date.today().month
        monthly_winner_count = 0
        
        exam_dates = Exam.objects.values_list('date', flat=True).distinct()
        months_set = set()
        for exam_date in exam_dates:
            if exam_date:
                if (exam_date.year < current_year) or (exam_date.year == current_year and exam_date.month < current_month):
                    months_set.add((exam_date.year, exam_date.month))
        
        for year, month in months_set:
            students_in_month = Student.objects.filter(
                exam__date__year=year,
                exam__date__month=month
            ).distinct()
            
            month_rankings = []
            for s in students_in_month:
                month_exams = s.exam_set.filter(date__year=year, date__month=month)
                exams_count = month_exams.count()
                if exams_count > 0:
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
        
        # Subject champion count
        subject_champion_count = 0
        subjects = Subject.objects.all()
        for subject in subjects:
            students_in_subject = Student.objects.filter(exam__subject=subject).distinct()
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


def subject_list(request):
    """List all subjects"""
    subjects = Subject.objects.all().order_by('name')
    
    subject_data = []
    for subject in subjects:
        exams = Exam.objects.filter(subject=subject)
        subject_data.append({
            'subject': subject,
            'average': subject.average_marks,
            'total_exams': count_unique_exams(exams)
        })
    
    context = {'subjects': subject_data}
    return render(request, 'marks/subject_list.html', context)


def subject_detail(request, subject_id):
    """Subject dashboard"""
    subject = get_object_or_404(Subject, id=subject_id)
    
    # Get subject statistics
    exams = Exam.objects.filter(subject=subject)
    best_student = subject.best_student()
    
    # Get all students in this subject with their performance
    students = Student.objects.filter(exam__subject=subject).distinct()
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
    
    context = {
        'subject': subject,
        'average_marks': subject.average_marks,
        'total_exams': count_unique_exams(exams),
        'best_student': best_student,
        'student_performance': student_performance,
        'excellence_rate': round(excellence_rate, 1),
        'cq_stats': cq_stats,
        'mcq_stats': mcq_stats,
    }
    
    return render(request, 'marks/subject_detail.html', context)


def add_student(request):
    """Add a new student"""
    if request.method == 'POST':
        name = request.POST.get('name')
        roll = request.POST.get('roll')
        class_number = request.POST.get('class_number')
        
        if name and roll and class_number:
            student = Student.objects.create(
                name=name,
                roll=roll,
                class_name=str(class_number)
            )
            messages.success(request, f'Student "{name}" added successfully!')
            return redirect('student_detail', student_id=student.id)
        else:
            messages.error(request, 'Student name, class, and roll number are all required!')
    
    return render(request, 'marks/add_student.html')


def add_subject(request):
    """Add a new subject"""
    if request.method == 'POST':
        name = request.POST.get('name')
        
        if name:
            subject = Subject.objects.create(name=name)
            messages.success(request, f'Subject "{name}" added successfully!')
            return redirect('subject_list')
        else:
            messages.error(request, 'Subject name is required!')
    
    return render(request, 'marks/add_subject.html')


def add_exam_type(request):
    """Add a new exam type"""
    if request.method == 'POST':
        name = request.POST.get('name')
        
        if name:
            exam_type = ExamType.objects.create(name=name)
            messages.success(request, f'Exam type "{name}" added successfully!')
            return redirect('add_exam')
        else:
            messages.error(request, 'Exam type name is required!')
    
    return render(request, 'marks/add_exam_type.html')


def add_exam(request):
    """Add a new exam"""
    if request.method == 'POST':
        student_id = request.POST.get('student')
        subject_id = request.POST.get('subject')
        exam_type_name = request.POST.get('exam_type')  # Now it's CQ or MCQ string
        date = request.POST.get('date')
        chapter = request.POST.get('chapter')
        class_number = request.POST.get('class_number')
        total_marks = request.POST.get('total_marks')
        mark_obtained = request.POST.get('mark_obtained')
        
        exam_id = request.POST.get('exam_id')
        if all([student_id, subject_id, exam_type_name, date, class_number, total_marks, mark_obtained, exam_id]):
            try:
                student = Student.objects.get(id=student_id)
                subject = Subject.objects.get(id=subject_id)
                # Get or create exam type (CQ or MCQ)
                exam_type, created = ExamType.objects.get_or_create(name=exam_type_name)
                # Convert to integers
                class_number = int(class_number)
                total_marks = int(total_marks)
                mark_obtained = int(mark_obtained)
                exam_id = int(exam_id)
                exam = Exam.objects.create(
                    student=student,
                    subject=subject,
                    exam_type=exam_type,
                    date=date,
                    chapter=chapter if chapter else None,
                    class_number=class_number,
                    total_marks=total_marks,
                    mark_obtained=mark_obtained,
                    exam_id=exam_id
                )
                messages.success(request, 'Exam added successfully!')
                return redirect('student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f'Error adding exam: {str(e)}')
        else:
            messages.error(request, 'All required fields must be filled!')
    
    students = Student.objects.all().order_by('name')
    subjects = Subject.objects.all().order_by('name')
    
    context = {
        'students': students,
        'subjects': subjects,
    }
    
    return render(request, 'marks/add_exam.html', context)


def add_bulk_exam(request):
    """Add exam for multiple students at once"""
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
            
            exam_id = request.POST.get('exam_id')
            if all([subject_id, exam_type_name, date, class_number, total_marks, exam_id]):
                try:
                    subject = Subject.objects.get(id=subject_id)
                    # Get or create exam type (CQ or MCQ)
                    exam_type, created = ExamType.objects.get_or_create(name=exam_type_name)
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
                        if student_id and mark_obtained:
                            student = Student.objects.get(id=student_id)
                            mark_obtained = int(mark_obtained)
                            Exam.objects.create(
                                student=student,
                                subject=subject,
                                exam_type=exam_type,
                                date=date,
                                chapter=chapter if chapter else None,
                                class_number=class_number,
                                total_marks=total_marks,
                                mark_obtained=mark_obtained,
                                group_id=group_id,
                                exam_id=exam_id
                            )
                            created_count += 1
                    messages.success(request, f'Successfully added 1 exam with {created_count} student results!')
                    return redirect('all_exams')
                except Exception as e:
                    messages.error(request, f'Error adding exams: {str(e)}')
            else:
                messages.error(request, 'All required fields must be filled!')
        else:
            # Step 1: Get student count and show the form
            student_count = int(request.POST.get('student_count', 0))
    
    students = Student.objects.all().order_by('name')
    subjects = Subject.objects.all().order_by('name')
    
    context = {
        'students': students,
        'subjects': subjects,
        'student_count': student_count,
        'student_range': range(1, student_count + 1) if student_count else [],
    }
    
    return render(request, 'marks/add_bulk_exam.html', context)


# API endpoints for chart data
def api_marks_over_time(request, student_id):
    """API endpoint for marks over time chart data"""
    data = ChartDataService.marks_over_time(student_id)
    return JsonResponse(data)


def api_subject_performance(request, student_id):
    """API endpoint for subject performance chart data"""
    data = ChartDataService.subject_performance_chart(student_id)
    return JsonResponse(data)


def api_grade_distribution(request, student_id):
    """API endpoint for grade distribution chart data"""
    data = ChartDataService.grade_distribution_chart(student_id)
    return JsonResponse(data)


def api_student_comparison(request, subject_id):
    """API endpoint for student comparison chart data"""
    data = ChartDataService.student_comparison_chart(subject_id)
    return JsonResponse(data)


def api_overall_grade_distribution(request):
    """API endpoint for overall grade distribution chart data"""
    data = ChartDataService.overall_grade_distribution()
    return JsonResponse(data)


def all_exams(request):
    """Display all exam entries in detail"""
    exams = Exam.objects.all().select_related('student', 'subject', 'exam_type').order_by('-date', '-exam_id')
    
    # Get filter parameters
    student_filter = request.GET.get('student')
    subject_filter = request.GET.get('subject')
    exam_type_filter = request.GET.get('exam_type')
    class_filter = request.GET.get('class_number')
    month_filter = request.GET.get('month')
    
    # Apply filters
    if student_filter:
        exams = exams.filter(student_id=student_filter)
    if subject_filter:
        exams = exams.filter(subject_id=subject_filter)
    if exam_type_filter:
        exams = exams.filter(exam_type_id=exam_type_filter)
    if class_filter:
        exams = exams.filter(class_number=class_filter)
    if month_filter:
        # month_filter format: "YYYY-MM"
        year, month = month_filter.split('-')
        exams = exams.filter(date__year=year, date__month=month)
    
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
    
    # Get all options for filters
    students = Student.objects.all().order_by('name')
    subjects = Subject.objects.all().order_by('name')
    exam_types = ExamType.objects.all().order_by('name')
    
    # Generate available months from exam dates
    from datetime import datetime
    all_exams = Exam.objects.all().values_list('date', flat=True).distinct()
    months_set = set()
    for exam_date in all_exams:
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
    }
    
    return render(request, 'marks/all_exams.html', context)


def points(request):
    """Points management page with history and summary"""
    # Get all students for filters
    students = Student.objects.all().order_by('name')
    
    # Get points spent history with filters
    points_history = PointsSpent.objects.all().select_related('student')
    
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
    
    # Get student points summary
    student_summary = []
    for student in Student.objects.all().order_by('name'):
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


def add_points_spent(request):
    """Form to record points spent by a student"""
    if request.method == 'POST':
        student_id = request.POST.get('student')
        points_spent = request.POST.get('points_spent')
        description = request.POST.get('description')
        
        try:
            student = Student.objects.get(id=student_id)
            points_spent = int(points_spent)
            
            # Get or create lifetime points for validation
            lifetime_points, created = LifetimePoints.objects.get_or_create(student=student)
            
            # Validate points
            if points_spent <= 0:
                messages.error(request, 'Points spent must be greater than 0.')
            elif points_spent > lifetime_points.points_remaining:
                messages.error(request, f'{student.name} only has {lifetime_points.points_remaining} points remaining.')
            else:
                # Create the points spent record
                PointsSpent.objects.create(
                    student=student,
                    points_spent=points_spent,
                    description=description[:15]  # Enforce max 15 characters
                )
                messages.success(request, f'Successfully recorded {points_spent} points spent by {student.name}.')
                return redirect('points')
        except Student.DoesNotExist:
            messages.error(request, 'Student not found.')
        except ValueError:
            messages.error(request, 'Invalid points value.')
    
    # Get all students for the form
    students = Student.objects.all().order_by('name')
    
    context = {
        'students': students,
    }
    
    return render(request, 'marks/add_points_spent.html', context)


def leaderboard(request):
    """Leaderboard page with overall, subject-wise, and monthly rankings"""
    from django.db.models import Avg, Count, Max, Sum
    from datetime import datetime
    
    # Get class filter from request
    class_filter = request.GET.get('class_number', 'all')
    
    # Get available class numbers
    available_classes = Exam.objects.values_list('class_number', flat=True).distinct().order_by('class_number')
    
    # Overall Rankings
    overall_rankings = []
    students = Student.objects.all()
    
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
                    students_in_month = Student.objects.filter(exam__class_number=exams.first().class_number, exam__date__year=year, exam__date__month=month).distinct()
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
    
    # Subject-wise Leaders
    subject_leaders = []
    subjects = Subject.objects.all()
    
    for subject in subjects:
        leaders = []
        
        # Filter by class if specified
        if class_filter != 'all':
            students_in_subject = Student.objects.filter(
                exam__subject=subject,
                exam__class_number=int(class_filter)
            ).distinct()
        else:
            students_in_subject = Student.objects.filter(exam__subject=subject).distinct()
        
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
            'leaders': leaders[:10],  # Top 10 per subject
        })
    
    # Monthly Champions (exclude current month)
    monthly_champions = []
    
    # Get all unique year-month combinations from exams (only past months)
    from datetime import date as date_type
    current_year = date_type.today().year
    current_month = date_type.today().month
    
    # Filter exam dates by class
    if class_filter != 'all':
        exam_dates = Exam.objects.filter(class_number=int(class_filter)).values_list('date', flat=True).distinct()
    else:
        exam_dates = Exam.objects.values_list('date', flat=True).distinct()
    
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
        
        # Get all students who had exams in this month (with class filter)
        if class_filter != 'all':
            students_in_month = Student.objects.filter(
                exam__date__year=year,
                exam__date__month=month,
                exam__class_number=int(class_filter)
            ).distinct()
        else:
            students_in_month = Student.objects.filter(
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
            'champions': champions[:10],  # Top 10 per month
        })
    
    context = {
        'overall_rankings': overall_rankings,
        'subject_leaders': subject_leaders,
        'monthly_champions': monthly_champions,
        'available_classes': available_classes,
        'selected_class': class_filter,
    }
    
    return render(request, 'marks/leaderboard.html', context)


def guide(request):
    """User guide page explaining grading system, points, and terminology"""
    return render(request, 'marks/guide.html')



