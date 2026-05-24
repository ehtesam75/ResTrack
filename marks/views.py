from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, Http404, HttpResponse
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum, Q
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from smtplib import SMTPException
import logging
import socket
import json
from .models import Student, Subject, ExamType, Exam, ExamQuestionPaper, GradeScale, LifetimePoints, PointsSpent, PointTransaction, TeacherProfile, StudentProfile, ExamCenterExam, GuestTeacherAccount
from .services import LeaderboardService, DashboardService, ChartDataService, count_unique_exams, get_grade_color_map
from .forms import (
    TeacherSignupForm,
    LoginForm,
    StudentAccountForm,
    GuestAccountForm,
    UsernamePasswordResetRequestForm,
    EmailUsernameLookupForm,
    UsernameSelectionForm,
    TargetedPasswordResetForm,
)
from .notifications import notify_result_published, notify_result_edited
from .guest_access import start_guest_session, clear_guest_session, is_guest_session, delete_guest_user_account, add_guest_read_only_message, add_guest_session_started_message, add_guest_submission_access_denied_message


logger = logging.getLogger(__name__)

CLASS_GROUP_MAX_LENGTH = 10


def _class_group_too_long(value):
    return len((value or '').strip()) > CLASS_GROUP_MAX_LENGTH


def _get_safe_redirect_target(request, target_url, fallback_name='dashboard'):
    """Return a safe local redirect target or a fallback route name."""
    if target_url and url_has_allowed_host_and_scheme(
        url=target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return target_url
    return fallback_name


def _is_safe_redirect_target(request, target_url):
    return bool(target_url) and url_has_allowed_host_and_scheme(
        url=target_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )


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
    
    # Cache global stats for 10 minutes to avoid DB hits on every page load
    from django.core.cache import cache
    context = cache.get('home_page_stats')
    if context is None:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        total_teachers = TeacherProfile.objects.count()
        total_students = Student.objects.count()
        # Calculate total exams as the sum of unique exams per teacher
        teacher_users = list(TeacherProfile.objects.select_related('user').all())
        total_exams = 0
        for tp in teacher_users:
            teacher_exams = Exam.objects.filter(teacher=tp.user)
            total_exams += count_unique_exams(teacher_exams)
        total_points = LifetimePoints.objects.aggregate(total=Sum('points_earned'))['total'] or 0

        context = {
            'total_teachers': total_teachers,
            'total_students': total_students,
            'total_exams': total_exams,
            'total_points': total_points,
        }
        cache.set('home_page_stats', context, 600)  # 10 minutes

    return render(request, 'marks/home.html', context)


def teacher_signup(request):
    """Handle teacher registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')

    teacher_registration_enabled = getattr(settings, 'TEACHER_REGISTRATION_ENABLED', True)
    registration_disabled_message = getattr(
        settings,
        'TEACHER_REGISTRATION_DISABLED_MESSAGE',
        'New account registration is temporarily disabled due to current system resource limits. Please try again later.'
    )

    if request.method == 'POST' and not teacher_registration_enabled:
        messages.error(request, registration_disabled_message)
        return redirect('signup')
    
    if request.method == 'POST':
        form = TeacherSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome, {user.first_name or user.username}.")
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = TeacherSignupForm()
    
    return render(
        request,
        'marks/signup.html',
        {
            'form': form,
            'teacher_registration_enabled': teacher_registration_enabled,
            'registration_disabled_message': registration_disabled_message,
        }
    )


def user_login(request):
    """Handle user login (both teacher and student)"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()

            # Guest credentials log into the owning teacher account in read-only mode.
            if hasattr(user, 'guest_teacher_account'):
                guest_account = user.guest_teacher_account
                teacher = guest_account.teacher
                if not hasattr(teacher, 'teacher_profile'):
                    messages.error(request, 'Invalid guest account configuration.')
                    return redirect('login')

                login(request, teacher)
                start_guest_session(request, guest_account)
                add_guest_session_started_message(request)
            else:
                login(request, user)
                clear_guest_session(request)
                messages.success(request, f"Welcome, {user.first_name or user.username}.")
            
            next_url = request.GET.get('next', 'dashboard')
            return redirect(_get_safe_redirect_target(request, next_url, 'dashboard'))
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'marks/login.html', {'form': form})


def guest_explore(request):
    """Allow visitors to start a view-only session for a public guest account."""
    public_guest_accounts = list(
        GuestTeacherAccount.objects.select_related('teacher', 'teacher__teacher_profile', 'guest_user')
        .filter(is_publicly_accessible=True, teacher__teacher_profile__isnull=False)
        .order_by('teacher__first_name', 'teacher__last_name', 'teacher__username')
    )

    if request.method == 'POST':
        selected_id = (request.POST.get('guest_account_id') or '').strip()
        selected_account = None

        if selected_id.isdigit():
            selected_account = next(
                (account for account in public_guest_accounts if account.id == int(selected_id)),
                None,
            )

        if not selected_account:
            messages.error(request, 'Please select an available teacher to continue.')
            return render(
                request,
                'marks/guest_explore.html',
                {
                    'public_guest_accounts': public_guest_accounts,
                    'selected_guest_account_id': selected_id,
                },
            )

        login(request, selected_account.teacher)
        start_guest_session(request, selected_account)
        add_guest_session_started_message(request)
        return redirect('dashboard')

    return render(
        request,
        'marks/guest_explore.html',
        {'public_guest_accounts': public_guest_accounts},
    )


def _send_targeted_password_reset_email(request, user):
    """Send Django built-in password reset email for exactly one selected user."""
    form = TargetedPasswordResetForm(
        data={'email': user.email},
        target_user=user,
    )
    if not form.is_valid():
        logger.warning('Password reset form invalid for user_id=%s username=%s', user.pk, user.username)
        return False

    eligible_users = list(form.get_users(user.email or ''))
    if not eligible_users:
        logger.warning(
            'Password reset email skipped (no eligible recipients) for user_id=%s username=%s has_usable_password=%s email_present=%s',
            user.pk,
            user.username,
            user.has_usable_password(),
            bool((user.email or '').strip()),
        )
        return False

    logger.info(
        'Attempting password reset email send for user_id=%s username=%s recipient=%s backend=%s timeout=%s',
        user.pk,
        user.username,
        user.email,
        settings.EMAIL_BACKEND,
        getattr(settings, 'EMAIL_TIMEOUT', None),
    )

    try:
        form.save(
            request=request,
            use_https=request.is_secure(),
            token_generator=default_token_generator,
            email_template_name='registration/password_reset_email.txt',
            subject_template_name='registration/password_reset_subject.txt',
        )
    except (SMTPException, OSError, socket.timeout, Exception):
        logger.exception(
            'Failed to send password reset email for user_id=%s username=%s',
            user.pk,
            user.username,
        )
        return False
    logger.info('Password reset email handed off to backend for user_id=%s username=%s', user.pk, user.username)
    return True


def password_reset_request(request):
    """Password reset entry page with username-first and email-fallback workflow."""
    username_form = UsernamePasswordResetRequestForm()
    email_form = EmailUsernameLookupForm()
    active_tab = 'username'

    if request.method == 'POST':
        action = request.POST.get('action', 'by_username')

        if action == 'by_email':
            active_tab = 'email'
            email_form = EmailUsernameLookupForm(request.POST)
            if email_form.is_valid():
                try:
                    users = list(email_form.get_users())
                except ValidationError as exc:
                    email_form.add_error('email', exc)
                else:
                    request.session['password_reset_lookup'] = {
                        'email': email_form.cleaned_data['email'],
                        'usernames': [u.username for u in users],
                    }
                    return redirect('password_reset_select_username')
        else:
            active_tab = 'username'
            username_form = UsernamePasswordResetRequestForm(request.POST)
            if username_form.is_valid():
                target_user = username_form.get_user()
                if target_user and _send_targeted_password_reset_email(request, target_user):
                    return redirect('password_reset_done')
                username_form.add_error('username', 'Unable to send reset email for this account.')

    return render(
        request,
        'registration/password_reset_form.html',
        {
            'username_form': username_form,
            'email_form': email_form,
            'active_tab': active_tab,
        },
    )


def password_reset_select_username(request):
    """Show usernames found by email and send reset for selected username."""
    lookup = request.session.get('password_reset_lookup')
    if not lookup or not lookup.get('email') or not lookup.get('usernames'):
        return redirect('password_reset')

    username_choices = [(u, u) for u in lookup['usernames']]

    if request.method == 'POST':
        form = UsernameSelectionForm(request.POST, username_choices=username_choices)
        if form.is_valid():
            selected_username = form.cleaned_data['username']
            user = get_user_model().objects.filter(
                username=selected_username,
                email__iexact=lookup['email'],
                is_active=True,
                teacher_profile__isnull=False,
            ).first()

            if user and _send_targeted_password_reset_email(request, user):
                request.session.pop('password_reset_lookup', None)
                return redirect('password_reset_done')

            form.add_error('username', 'Unable to send reset email for this account right now. Please try again later.')
    else:
        form = UsernameSelectionForm(username_choices=username_choices)

    return render(
        request,
        'registration/password_reset_select_username.html',
        {
            'form': form,
            'lookup_email': lookup['email'],
            'username_count': len(username_choices),
        },
    )


def user_logout(request):
    """Handle user logout"""
    clear_guest_session(request)
    messages.success(request, 'You have been logged out successfully.')
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
    guest_account_exists = GuestTeacherAccount.objects.filter(teacher=teacher).exists()
    
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
        'guest_account_exists': guest_account_exists,
    }
    return render(request, 'marks/manage.html', context)


@login_required(login_url='login')
def dashboard(request):
    """Main dashboard view with analytics.

    Teachers see class-level analytics. Students see only their personal analytics.
    """
    from collections import Counter

    teacher = get_teacher_for_user(request.user)
    is_student_dashboard = is_student(request.user)
    dashboard_student = None

    if is_student_dashboard:
        dashboard_student = get_object_or_404(
            Student,
            id=request.user.student_profile.student_id,
            teacher=teacher,
        )
        student_exams = Exam.objects.filter(teacher=teacher, student=dashboard_student)

        summary = {
            'total_exams': dashboard_student.total_exams,
            'total_subjects': len(dashboard_student.subject_wise_summary()),
            'total_students': 1,
            'highest_marks_student': dashboard_student,
            'highest_avg_student': dashboard_student,
            'best_student': dashboard_student,
            'rank': dashboard_student.rank,
            'average_percentage': round(dashboard_student.average_percentage, 2),
        }

        subject_performance = sorted(
            [
                {
                    'subject': item['subject'],
                    'average_percentage': round(item['average_percentage'], 2),
                    'total_exams': item['exam_count'],
                    'best_student': None,
                }
                for item in dashboard_student.subject_wise_summary()
            ],
            key=lambda x: x['average_percentage'],
            reverse=True,
        )

        exam_type_performance = sorted(
            [
                {
                    'exam_type': item['exam_type'],
                    'average_percentage': round(item['average_percentage'], 2),
                    'total_exams': item['exam_count'],
                }
                for item in dashboard_student.exam_type_summary()
            ],
            key=lambda x: x['average_percentage'],
            reverse=True,
        )

        distribution = Counter(dashboard_student.grade_frequency())
        recent_exams = student_exams.order_by('-date', '-exam_id')[:10]
        total_marks_leaderboard = [
            {
                'student': dashboard_student,
                'total_marks': dashboard_student.total_marks,
                'total_exams': dashboard_student.total_exams,
            }
        ]
        average_leaderboard = []
        if dashboard_student.total_exams > 0:
            average_leaderboard = [
                {
                    'student': dashboard_student,
                    'average': dashboard_student.average_percentage,
                    'total_exams': dashboard_student.total_exams,
                }
            ]
        student_points = LifetimePoints.objects.filter(student=dashboard_student).first()
        points_leaderboard = []
        if student_points:
            points_leaderboard = [
                {
                    'student': dashboard_student,
                    'total_points': student_points.total_points,
                    'points_earned': student_points.points_earned,
                    'points_spent': student_points.points_spent,
                }
            ]
    else:
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
            'best_student': best_student,
            'rank': None,
            'average_percentage': None,
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
        # Use a single query with select_related instead of N individual queries
        student_ids = [s.id for s in teacher_students]
        lp_map = {
            lp.student_id: lp
            for lp in LifetimePoints.objects.filter(student_id__in=student_ids).select_related('student')
        }
        points_leaderboard = []
        for student in teacher_students:
            lp = lp_map.get(student.id)
            if lp:
                points_leaderboard.append({
                    'student': student,
                    'total_points': lp.total_points,
                    'points_earned': lp.points_earned,
                    'points_spent': lp.points_spent
                })
        points_leaderboard = sorted(points_leaderboard, key=lambda x: x['total_points'], reverse=True)[:3]

    grade_color_map = get_grade_color_map()

    grade_distribution = []
    for grade_name, count in distribution.items():
        color = grade_color_map.get(grade_name, '#000000')
        grade_distribution.append({'grade': grade_name, 'count': count, 'color': color})

    # Serialize subject_performance for JavaScript
    subject_performance_json = json.dumps([
        {
            'subject': {
                'name': item['subject'].name,
                'short_name': item['subject'].short_name,
                'chart_label': item['subject'].short_name or ChartDataService.shorten_subject_name(item['subject'].name),
                'id': item['subject'].id
            },
            'average_percentage': item['average_percentage'],
            'total_exams': item['total_exams'],
            'best_student': item['best_student'].name if item['best_student'] else None
        }
        for item in subject_performance
    ])
    
    context = {
        'is_student_dashboard': is_student_dashboard,
        'dashboard_student': dashboard_student,
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
def manage_guest_account(request):
    """Create, edit, or delete one guest account for the current teacher."""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can manage guest accounts.')
        return redirect('dashboard')

    if is_guest_session(request):
        add_guest_read_only_message(request)
        next_url = request.GET.get('next')
        if _is_safe_redirect_target(request, next_url):
            return redirect(next_url)
        referer = request.META.get('HTTP_REFERER')
        if _is_safe_redirect_target(request, referer):
            return redirect(referer)
        return redirect('dashboard')

    teacher = request.user
    guest_account = GuestTeacherAccount.objects.select_related('guest_user').filter(teacher=teacher).first()

    if request.method == 'POST':
        action = request.POST.get('action', '').strip()

        if action == 'delete':
            if not guest_account:
                messages.error(request, 'No guest account exists for deletion.')
                return redirect('manage_guest_account')

            delete_guest_user_account(guest_account)
            messages.success(request, 'Guest account deleted successfully.')
            return redirect('manage_guest_account')

        if action == 'create':
            if guest_account:
                messages.error(request, 'You can only keep one guest account at a time.')
                return redirect('manage_guest_account')

            form = GuestAccountForm(request.POST, require_password=True)
            if form.is_valid():
                username = form.cleaned_data['username']
                new_password = form.cleaned_data['new_password']
                is_publicly_accessible = form.cleaned_data.get('is_publicly_accessible', False)

                with transaction.atomic():
                    User = get_user_model()
                    guest_user = User.objects.create_user(username=username, password=new_password)
                    GuestTeacherAccount.objects.create(
                        teacher=teacher,
                        guest_user=guest_user,
                        is_publicly_accessible=is_publicly_accessible,
                    )
                messages.success(request, f"Guest account '{username}' created successfully.")
                if is_publicly_accessible:
                    messages.info(
                        request,
                        'This guest account is publicly accessible in view-only mode. Anyone can open your data using Guest Explore.',
                    )
                return redirect('manage_guest_account')
            for _, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
        elif action == 'edit':
            if not guest_account:
                messages.error(request, 'No guest account exists to edit.')
                return redirect('manage_guest_account')

            form = GuestAccountForm(
                request.POST,
                existing_user=guest_account.guest_user,
                require_password=False,
            )
            if form.is_valid():
                username = form.cleaned_data['username']
                new_password = form.cleaned_data.get('new_password')
                is_publicly_accessible = form.cleaned_data.get('is_publicly_accessible', False)

                guest_user = guest_account.guest_user
                credential_changed = False
                visibility_changed = guest_account.is_publicly_accessible != is_publicly_accessible

                if guest_user.username != username:
                    guest_user.username = username
                    credential_changed = True

                if new_password:
                    guest_user.set_password(new_password)
                    credential_changed = True

                if visibility_changed:
                    guest_account.is_publicly_accessible = is_publicly_accessible

                if credential_changed or visibility_changed:
                    with transaction.atomic():
                        if credential_changed:
                            guest_user.save()
                        if visibility_changed:
                            guest_account.save(update_fields=['is_publicly_accessible', 'updated_at'])
                    messages.success(request, 'Guest account updated successfully.', extra_tags='success-popup')
                    if is_publicly_accessible:
                        messages.info(
                            request,
                            'This guest account is publicly accessible in view-only mode. Anyone can open your data using Guest Explore.',
                        )
                else:
                    messages.info(request, 'No changes detected for guest account.')

                return redirect('manage_guest_account')
            for _, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
        else:
            messages.error(request, 'Invalid action.')
            return redirect('manage_guest_account')
    else:
        if guest_account:
            form = GuestAccountForm(
                initial={
                    'username': guest_account.guest_user.username,
                    'is_publicly_accessible': guest_account.is_publicly_accessible,
                },
                existing_user=guest_account.guest_user,
                require_password=False,
            )
        else:
            form = GuestAccountForm(require_password=True)

    return render(
        request,
        'marks/manage_guest_account.html',
        {
            'guest_account': guest_account,
            'form': form,
        },
    )


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
        class_number = (request.POST.get('class_number') or '').strip()
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        # Validate all required fields
        if not all([first_name, roll, class_number, username, password, confirm_password]):
            messages.error(request, 'All required fields must be filled!')
        elif _class_group_too_long(class_number):
            messages.error(request, 'Class cannot exceed 10 characters.')
        elif password != confirm_password:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'This username is already taken. Please choose another.')
        else:
            try:
                validate_password(password)
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
                    class_name=class_number,
                    teacher=request.user
                )
                
                # Create student profile linking user to student
                StudentProfile.objects.create(
                    user=user,
                    student=student,
                    created_by=request.user,
                )
                messages.success(request, f'Student {student.name} created successfully.')
                
                return redirect('student_detail', student_id=student.id)
            except ValidationError as e:
                messages.error(request, ' '.join(e.messages))
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
    guest_session = is_guest_session(request)
    
    # Get the student's user account if it exists
    student_user = None
    if hasattr(student, 'user_profile'):
        student_user = student.user_profile.user
    
    if request.method == 'POST':
        action = request.POST.get('action', 'save')

        if guest_session:
            add_guest_read_only_message(request)
        elif action == 'delete':
            try:
                student_name = student.name
                student_user_id = student_user.id if student_user else None

                with transaction.atomic():
                    student.delete()
                    if student_user_id:
                        User.objects.filter(id=student_user_id).delete()

                messages.success(request, f'Student {student_name} deleted successfully.', extra_tags='success-popup')
                return redirect('student_list')
            except Exception as e:
                messages.error(request, f'Error deleting student: {str(e)}')
                return redirect('edit_student', student_id=student_id)
        else:
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            roll = request.POST.get('roll')
            class_number = (request.POST.get('class_number') or '').strip()
            username = request.POST.get('username')
            new_password = request.POST.get('new_password')
            confirm_password = request.POST.get('confirm_password')

            # Validate required fields
            if not all([first_name, roll, class_number]):
                messages.error(request, 'First name, roll, and class are required!')
            elif _class_group_too_long(class_number):
                messages.error(request, 'Class cannot exceed 10 characters.')
            else:
                try:
                    # Update student info
                    student.first_name = first_name
                    student.last_name = last_name or None
                    student.roll = roll
                    student.class_name = class_number
                    student.save()
                    
                    # Update user credentials if provided
                    if student_user:
                        # Update username if changed
                        if username and username != student_user.username:
                            if User.objects.filter(username=username).exclude(id=student_user.id).exists():
                                messages.error(request, 'This username is already taken. Please choose another.')
                                return redirect('edit_student', student_id=student_id)
                            student_user.username = username
                            student_user.save()
                        
                        # Update password if provided
                        if new_password:
                            if new_password != confirm_password:
                                messages.error(request, 'Passwords do not match.')
                                return redirect('edit_student', student_id=student_id)
                            try:
                                validate_password(new_password, student_user)
                            except ValidationError as e:
                                messages.error(request, ' '.join(e.messages))
                                return redirect('edit_student', student_id=student_id)
                            student_user.set_password(new_password)
                            student_user.save()

                    messages.success(request, f'Student {student.name} updated successfully.', extra_tags='success-popup')
                    
                    return redirect('student_detail', student_id=student.id)
                except Exception as e:
                    messages.error(request, f'Error updating student: {str(e)}')

    context = {
        'student': student,
        'student_user': student_user,
        'is_guest_session': guest_session,
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
        name = (request.POST.get('name') or '').strip()
        short_name = (request.POST.get('short_name') or '').strip()
        if not name or not short_name:
            messages.error(request, 'Both subject name and short name are required!')
        elif len(name) > 25:
            messages.error(request, 'Subject name cannot exceed 25 characters.')
        elif len(short_name) > 10:
            messages.error(request, 'Short name cannot exceed 10 characters.')
        else:
            subject = Subject.objects.create(name=name, short_name=short_name, teacher=request.user)
            messages.success(request, f'Subject {subject.name} added successfully.')
            return redirect('subject_list')

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
        name = (request.POST.get('name') or '').strip()
        short_name = (request.POST.get('short_name') or '').strip()

        if not name or not short_name:
            messages.error(request, 'Both subject name and short name are required.')
            return redirect('add_subject')
        if len(name) > 25:
            messages.error(request, 'Subject name cannot exceed 25 characters.')
            return redirect('add_subject')
        if len(short_name) > 10:
            messages.error(request, 'Short name cannot exceed 10 characters.')
            return redirect('add_subject')

        try:
            subject = Subject.objects.get(id=subject_id, teacher=request.user)
            subject.name = name
            subject.short_name = short_name
            subject.save()
            messages.success(request, f'Subject {subject.name} updated successfully.')

            return redirect('add_subject')
        except Subject.DoesNotExist:
            messages.error(request, 'Subject not found or you do not have permission to edit it.')
        except Exception as e:
            messages.error(request, f'Error updating subject: {str(e)}')

    return redirect('add_subject')


@login_required(login_url='login')
def delete_subject(request, subject_id):
    """Delete a subject owned by the current teacher (and cascaded exam results)."""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can delete subjects.')
        return redirect('dashboard')

    if request.method != 'POST':
        messages.error(request, 'Invalid request method for subject deletion.')
        return redirect('add_subject')

    if is_guest_session(request):
        add_guest_read_only_message(request)
        return redirect('add_subject')

    subject = get_object_or_404(Subject, id=subject_id, teacher=request.user)

    try:
        related_exam_count = Exam.objects.filter(subject=subject, teacher=request.user).count()
        subject_name = subject.name
        subject.delete()
        messages.success(
            request,
            f'Subject {subject_name} deleted successfully. Removed {related_exam_count} related exam result(s).'
        )
    except Exception as e:
        messages.error(request, f'Error deleting subject: {str(e)}')

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
        class_number = (request.POST.get('class_number') or '').strip()
        total_marks = request.POST.get('total_marks')
        mark_obtained = request.POST.get('mark_obtained')
        question_pdf = request.FILES.get('question_pdf')
        marked_answer_paper = request.FILES.get('marked_answer_paper')
        
        exam_id = request.POST.get('exam_id')
        if all([student_id, subject_id, exam_type_name, date, chapter, class_number, total_marks, mark_obtained, exam_id]):
            if _class_group_too_long(class_number):
                messages.error(request, 'Class cannot exceed 10 characters.')
                return redirect('add_exam')
            try:
                # Ensure student belongs to this teacher
                student = Student.objects.get(id=student_id, teacher=teacher)
                subject = Subject.objects.get(id=subject_id, teacher=teacher)
                # Get or create exam type (CQ or MCQ) for this teacher
                exam_type, created = ExamType.objects.get_or_create(name=exam_type_name, teacher=teacher)
                # Convert numeric fields
                total_marks = int(total_marks)
                mark_obtained = int(mark_obtained)
                exam_id = int(exam_id)
                # Validate exam_id range
                max_existing = Exam.objects.filter(teacher=teacher).values_list('exam_id', flat=True).order_by('-exam_id').first() or 0
                if exam_id < 1 or exam_id > max_existing + 1:
                    messages.error(request, f'Exam ID must be between 1 and {max_existing + 1}.')
                    return redirect('add_exam')
                # Prevent duplicate: same student + same exam_id for this teacher
                if Exam.objects.filter(exam_id=exam_id, student=student, teacher=teacher).exists():
                    messages.error(request, f'A result for {student.display_name} already exists for Exam ID {exam_id}.')
                    return redirect('add_exam')
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
                    marked_answer_paper=marked_answer_paper
                )
                # Save question paper to ExamQuestionPaper (one per exam_id)
                if question_pdf:
                    ExamQuestionPaper.objects.update_or_create(
                        exam_id=exam_id,
                        teacher=teacher,
                        defaults={'question_pdf': question_pdf}
                    )
                # Notify the student about published results
                try:
                    notify_result_published(exam_id, [student.id], teacher)
                except Exception:
                    pass  # Don't let push failures block result publishing
                messages.success(request, f'Result added successfully for {student.name}.')
                return redirect('student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f'Error adding exam: {str(e)}')
        else:
            messages.error(request, 'All required fields must be filled!')
    
    # Filter students and subjects by teacher
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    subjects = Subject.objects.filter(teacher=teacher).order_by('name')
    exam_types = ExamType.objects.filter(teacher=teacher).order_by('name')
    
    # Get max exam ID for validation
    max_exam_id = Exam.objects.filter(teacher=teacher).values_list('exam_id', flat=True).order_by('-exam_id').first() or 0
    
    # Check if running on production (non-localhost)
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'students': students,
        'subjects': subjects,
        'exam_types': exam_types,
        'is_production': is_production,
        'max_exam_id': max_exam_id,
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
            if is_guest_session(request):
                add_guest_read_only_message(request)
                return redirect('add_bulk_exams')
            # Step 2: Process and save all exams
            student_count = int(request.POST.get('student_count'))
            subject_id = request.POST.get('subject')
            exam_type_name = request.POST.get('exam_type')  # Now it's CQ or MCQ string
            date = request.POST.get('date')
            chapter = request.POST.get('chapter')
            class_number = (request.POST.get('class_number') or '').strip()
            total_marks = request.POST.get('total_marks')
            question_pdf = request.FILES.get('question_pdf')
            
            exam_id = request.POST.get('exam_id')
            if all([subject_id, exam_type_name, date, chapter, class_number, total_marks, exam_id]):
                if _class_group_too_long(class_number):
                    messages.error(request, 'Class cannot exceed 10 characters.')
                    return redirect('add_bulk_exams')
                try:
                    # Ensure subject belongs to this teacher
                    subject = Subject.objects.get(id=subject_id, teacher=teacher)
                    # Get or create exam type (CQ or MCQ) for this teacher
                    exam_type, created = ExamType.objects.get_or_create(name=exam_type_name, teacher=teacher)
                    total_marks = int(total_marks)
                    exam_id = int(exam_id)
                    # Validate exam_id range
                    max_existing = Exam.objects.filter(teacher=teacher).values_list('exam_id', flat=True).order_by('-exam_id').first() or 0
                    if exam_id < 1 or exam_id > max_existing + 1:
                        messages.error(request, f'Exam ID must be between 1 and {max_existing + 1}.')
                        return redirect('add_bulk_exams')
                    # Generate unique group ID for this exam session
                    import uuid
                    from datetime import datetime
                    group_id = f"bulk_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
                    # Create exams for all students
                    # Skip per-save recalculation during bulk insert — we do it once at the end
                    created_count = 0
                    skipped_students = []
                    affected_students = set()
                    for i in range(1, student_count + 1):
                        student_id = request.POST.get(f'student_{i}')
                        mark_obtained = request.POST.get(f'marks_{i}')
                        marked_answer_paper = request.FILES.get(f'marked_answer_{i}')
                        if student_id and mark_obtained:
                            # Ensure student belongs to this teacher
                            student = Student.objects.get(id=student_id, teacher=teacher)
                            # Prevent duplicate: same student + same exam_id
                            if Exam.objects.filter(exam_id=exam_id, student=student, teacher=teacher).exists():
                                skipped_students.append(student.display_name)
                                continue
                            mark_obtained = int(mark_obtained)
                            exam_obj = Exam(
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
                                marked_answer_paper=marked_answer_paper
                            )
                            exam_obj._skip_recalculate = True
                            exam_obj.save()
                            affected_students.add(student)
                            created_count += 1
                    # Recalculate points once per affected student (not per exam)
                    for student in affected_students:
                        student.recalculate_lifetime_points()
                    # Save question paper to ExamQuestionPaper (one per exam_id)
                    if question_pdf:
                        ExamQuestionPaper.objects.update_or_create(
                            exam_id=exam_id,
                            teacher=teacher,
                            defaults={'question_pdf': question_pdf}
                        )
                    # Warn about skipped duplicates
                    if skipped_students:
                        names = ', '.join(skipped_students)
                        messages.warning(request, f'Skipped duplicate entries for: {names} (already have results for Exam ID {exam_id}).')
                    # Notify all participating students about published results
                    participating_student_ids = []
                    for i in range(1, student_count + 1):
                        sid = request.POST.get(f'student_{i}')
                        if sid and request.POST.get(f'marks_{i}'):
                            participating_student_ids.append(int(sid))
                    if participating_student_ids:
                        try:
                            notify_result_published(exam_id, participating_student_ids, teacher)
                        except Exception:
                            pass  # Don't let push failures block result publishing
                    messages.success(request, f'{created_count} results added successfully.')
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
    
    # Get max exam ID for validation
    max_exam_id = Exam.objects.filter(teacher=teacher).values_list('exam_id', flat=True).order_by('-exam_id').first() or 0
    
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
        'max_exam_id': max_exam_id,
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
        class_number = (request.POST.get('class_number') or '').strip()
        total_marks = request.POST.get('total_marks')
        mark_obtained = request.POST.get('mark_obtained')
        exam_id_new = request.POST.get('exam_id')
        marked_answer_paper = request.FILES.get('marked_answer_paper')
        
        if all([student_id, subject_id, exam_type_name, date, chapter, class_number, total_marks, mark_obtained, exam_id_new]):
            if _class_group_too_long(class_number):
                messages.error(request, 'Class cannot exceed 10 characters.')
                return redirect('edit_exam', exam_id=exam.id)
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
                exam.class_number = class_number
                exam.total_marks = int(total_marks)
                exam.mark_obtained = int(mark_obtained)
                exam.exam_id = int(exam_id_new)
                
                if marked_answer_paper:
                    exam.marked_answer_paper = marked_answer_paper
                
                exam.save()
                
                # Recalculate student's lifetime points
                exam.student.recalculate_lifetime_points()
                
                # Notify the student about the updated result
                try:
                    notify_result_edited(exam)
                except Exception:
                    pass  # Don't let push failures block result editing
                messages.success(request, 'Exam result updated successfully.')
                
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
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        return JsonResponse({'error': 'Not authorized'}, status=403)

    student = get_object_or_404(Student, id=student_id, teacher=teacher)
    data = ChartDataService.marks_over_time(student.id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_subject_performance(request, student_id):
    """API endpoint for subject performance chart data"""
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        return JsonResponse({'error': 'Not authorized'}, status=403)

    student = get_object_or_404(Student, id=student_id, teacher=teacher)
    data = ChartDataService.subject_performance_chart(student.id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_grade_distribution(request, student_id):
    """API endpoint for grade distribution chart data"""
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        return JsonResponse({'error': 'Not authorized'}, status=403)

    student = get_object_or_404(Student, id=student_id, teacher=teacher)
    data = ChartDataService.grade_distribution_chart(student.id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_student_comparison(request, subject_id):
    """API endpoint for student comparison chart data"""
    if not is_teacher(request.user):
        return JsonResponse({'error': 'Not authorized'}, status=403)

    teacher = get_teacher_for_user(request.user)
    subject = get_object_or_404(Subject, id=subject_id, teacher=teacher)

    data = ChartDataService.student_comparison_chart(subject.id)
    return JsonResponse(data)


@login_required(login_url='login')
def api_overall_grade_distribution(request):
    """API endpoint for overall grade distribution chart data"""
    teacher = get_teacher_for_user(request.user)
    if is_student(request.user):
        student = get_object_or_404(
            Student,
            id=request.user.student_profile.student_id,
            teacher=teacher,
        )
        data = ChartDataService.grade_distribution_chart(student.id)
    else:
        data = ChartDataService.overall_grade_distribution(teacher=teacher)
    return JsonResponse(data)


@login_required(login_url='login')
def all_exams(request):
    """Display all exam entries in detail - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    exams = Exam.objects.filter(teacher=teacher).select_related('student', 'subject', 'exam_type').order_by('-date', '-exam_id')
    student_user = is_student(request.user)
    student_profile = request.user.student_profile if student_user else None
    
    # Get filter parameters
    student_filter = request.GET.get('student')
    subject_filter = request.GET.get('subject')
    exam_type_filter = request.GET.get('exam_type')
    class_filter = (request.GET.get('class_number') or '').strip()
    month_filter = request.GET.get('month')
    chapter_filter = request.GET.get('chapter')
    exam_id_from = request.GET.get('exam_id_from')
    exam_id_to = request.GET.get('exam_id_to')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if student_user:
        # Students can only access their own results, regardless of query parameters.
        student_filter = str(student_profile.student_id)
        exams = exams.filter(student_id=student_profile.student_id)

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
    
    # Calculate statistics using DB aggregation instead of Python iteration
    from django.db.models import Max, Min
    average_percentage = 0
    highest_percentage = 0
    lowest_percentage = 0
    
    agg = exams.aggregate(
        total_obtained=Sum('mark_obtained'),
        total_possible=Sum('total_marks'),
    )
    if agg['total_possible'] and agg['total_possible'] > 0:
        average_percentage = (float(agg['total_obtained']) * 100 / float(agg['total_possible']))
        # For highest/lowest percentage we still need per-exam computation,
        # but we can limit it to annotated values
        from django.db.models import F, FloatField, ExpressionWrapper
        exams_with_pct = exams.annotate(
            pct=ExpressionWrapper(
                F('mark_obtained') * 100.0 / F('total_marks'),
                output_field=FloatField()
            )
        )
        pct_agg = exams_with_pct.aggregate(
            highest=Max('pct'),
            lowest=Min('pct'),
        )
        highest_percentage = pct_agg['highest'] or 0
        lowest_percentage = pct_agg['lowest'] or 0
    
    # Get all options for filters (filtered by teacher)
    if student_user:
        students = Student.objects.filter(id=student_profile.student_id, teacher=teacher).order_by('first_name', 'last_name')
    else:
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
        'is_student': student_user,
        'student_filter': student_filter,
    }
    
    return render(request, 'marks/all_exams.html', context)


@login_required(login_url='login')
def exam_detail(request, exam_id):
    """Exam detail page showing overview and all participant results for a specific exam_id"""
    teacher = get_teacher_for_user(request.user)

    # Get all exam records sharing this exam_id for this teacher
    exam_records = Exam.objects.filter(
        teacher=teacher, exam_id=exam_id
    ).select_related('student', 'subject', 'exam_type').order_by('-mark_obtained')

    if not exam_records.exists():
        from django.http import Http404
        raise Http404("Exam not found")

    # Use the first record to extract shared exam metadata
    first = exam_records.first()
    exam_date = first.date
    class_number = first.class_number
    subject = first.subject
    chapter = first.chapter
    exam_type = first.exam_type
    total_marks = first.total_marks

    # Participant stats
    num_participants = exam_records.count()
    percentages = [e.percentage for e in exam_records]
    class_average = sum(percentages) / len(percentages) if percentages else 0
    lowest_score = min(percentages) if percentages else 0
    highest_score = max(percentages) if percentages else 0

    # Best performer
    best_exam = exam_records.first()  # already ordered by -mark_obtained
    best_performer = best_exam.student if best_exam else None

    # Build participant list with rank
    participants = []
    sorted_records = sorted(exam_records, key=lambda e: e.percentage, reverse=True)
    current_rank = 0
    prev_pct = None
    for idx, exam in enumerate(sorted_records):
        pct = round(exam.percentage, 2)
        if pct != prev_pct:
            current_rank = idx + 1
        participants.append({
            'rank': current_rank,
            'student': exam.student,
            'mark_obtained': exam.mark_obtained,
            'total_marks': exam.total_marks,
            'percentage': exam.percentage,
            'grade': exam.grade,
            'grade_color': exam.grade_color,
            'exam_pk': exam.pk,
        })
        prev_pct = pct

    # Role-based: identify logged-in student (if any)
    current_student_id = None
    user_is_student = is_student(request.user)
    if user_is_student:
        try:
            current_student_id = request.user.student_profile.student.id
        except Exception:
            pass

    # Document availability for download buttons
    question_paper_url = None
    # Check ExamQuestionPaper model first, then legacy field
    try:
        qp = ExamQuestionPaper.objects.get(exam_id=exam_id, teacher=teacher)
        if qp.question_pdf:
            question_paper_url = qp.question_pdf.url if hasattr(qp.question_pdf, 'url') else str(qp.question_pdf)
    except ExamQuestionPaper.DoesNotExist:
        # Fallback to legacy field on first exam record
        if first.question_pdf:
            question_paper_url = first.question_pdf.url if hasattr(first.question_pdf, 'url') else str(first.question_pdf)

    # Build per-participant marked answer paper info
    detail_next_url = reverse('exam_detail', args=[exam_id])
    for p in participants:
        exam_record = next((e for e in exam_records if e.student_id == p['student'].id), None)
        p['has_answer_paper'] = bool(exam_record and exam_record.marked_answer_paper)
        p['answer_paper_exam_pk'] = exam_record.pk if exam_record else None
        if exam_record and exam_record.marked_answer_paper:
            p['answer_paper_url'] = f"{reverse('exam_view_answer', args=[exam_record.pk])}?next={detail_next_url}"
        else:
            p['answer_paper_url'] = None

    # Track whether a question paper was uploaded at all (before access checks)
    question_paper_uploaded = bool(question_paper_url)

    # Check if the logged-in student participated in this exam
    student_participated = True
    if user_is_student:
        student_participated = any(p['student'].id == current_student_id for p in participants)
        # If student didn't participate, hide question paper
        if not student_participated:
            question_paper_url = None

    context = {
        'exam_id': exam_id,
        'exam_date': exam_date,
        'class_number': class_number,
        'subject': subject,
        'chapter': chapter,
        'exam_type': exam_type,
        'total_marks': total_marks,
        'num_participants': num_participants,
        'class_average': class_average,
        'lowest_score': lowest_score,
        'highest_score': highest_score,
        'best_performer': best_performer,
        'participants': participants,
        'is_student': user_is_student,
        'current_student_id': current_student_id,
        'has_question_paper': bool(question_paper_url),
        'question_paper_url': question_paper_url,
        'question_paper_uploaded': question_paper_uploaded,
        'student_participated': student_participated,
    }
    return render(request, 'marks/exam_detail.html', context)


def _cloudinary_download_url(url):
    """Convert a Cloudinary URL to force-download by inserting fl_attachment."""
    url = str(url)
    if 'cloudinary.com' in url and '/upload/' in url:
        return url.replace('/upload/', '/upload/fl_attachment/', 1)
    # Non-cloudinary or unexpected format — return as-is
    return url


@login_required(login_url='login')
def exam_download_question(request, exam_id):
    """Download question paper for an exam (Cloudinary redirect with fl_attachment)."""
    from django.http import Http404, HttpResponseForbidden
    teacher = get_teacher_for_user(request.user)

    # If the user is a student, verify they participated in this exam
    if is_student(request.user):
        try:
            student = request.user.student_profile.student
            if not Exam.objects.filter(exam_id=exam_id, teacher=teacher, student=student).exists():
                return HttpResponseForbidden("You did not participate in this exam.")
        except Exception:
            return HttpResponseForbidden("You did not participate in this exam.")

    # Try ExamQuestionPaper model first
    url = None
    try:
        qp = ExamQuestionPaper.objects.get(exam_id=exam_id, teacher=teacher)
        if qp.question_pdf:
            url = qp.question_pdf.url if hasattr(qp.question_pdf, 'url') else str(qp.question_pdf)
    except ExamQuestionPaper.DoesNotExist:
        pass

    # Fallback to legacy field
    if not url:
        exam_record = Exam.objects.filter(exam_id=exam_id, teacher=teacher).first()
        if exam_record and exam_record.question_pdf:
            url = exam_record.question_pdf.url if hasattr(exam_record.question_pdf, 'url') else str(exam_record.question_pdf)

    if not url:
        raise Http404("Question paper not found")

    return redirect(_cloudinary_download_url(url))


@login_required(login_url='login')
def exam_view_answer(request, exam_pk):
    """Open marked answer paper for a specific exam record."""
    from django.http import Http404

    teacher = get_teacher_for_user(request.user)
    exam = get_object_or_404(Exam, pk=exam_pk, teacher=teacher)

    if is_guest_session(request):
        add_guest_submission_access_denied_message(request)
        next_url = request.GET.get('next')
        if _is_safe_redirect_target(request, next_url):
            return redirect(next_url)
        referer = request.META.get('HTTP_REFERER')
        if _is_safe_redirect_target(request, referer):
            return redirect(referer)
        return redirect('exam_detail', exam_id=exam.exam_id)

    if not exam.marked_answer_paper:
        raise Http404("Answer paper not found")

    url = exam.marked_answer_paper.url if hasattr(exam.marked_answer_paper, 'url') else str(exam.marked_answer_paper)
    return redirect(url)


@login_required(login_url='login')
def exam_download_answer(request, exam_pk):
    """Download marked answer paper for a specific exam record."""
    from django.http import Http404

    teacher = get_teacher_for_user(request.user)
    exam = get_object_or_404(Exam, pk=exam_pk, teacher=teacher)

    if is_guest_session(request):
        add_guest_submission_access_denied_message(request)
        next_url = request.GET.get('next')
        if _is_safe_redirect_target(request, next_url):
            return redirect(next_url)
        referer = request.META.get('HTTP_REFERER')
        if _is_safe_redirect_target(request, referer):
            return redirect(referer)
        return redirect('exam_detail', exam_id=exam.exam_id)

    if not exam.marked_answer_paper:
        raise Http404("Answer paper not found")

    url = exam.marked_answer_paper.url if hasattr(exam.marked_answer_paper, 'url') else str(exam.marked_answer_paper)
    return redirect(_cloudinary_download_url(url))


@login_required(login_url='login')
def points(request):
    """Points management page with history and summary - filtered by teacher"""
    teacher = get_teacher_for_user(request.user)
    
    # Get all students for filters (filtered by teacher)
    students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    
    # Get points transaction history with filters (filtered by teacher)
    points_history = PointTransaction.objects.filter(teacher=teacher).select_related('student', 'exam')

    # Apply filters from GET parameters
    student_filter = request.GET.get('student')
    from_date = request.GET.get('from_date')
    to_date = request.GET.get('to_date')
    transaction_type = request.GET.get('transaction_type')
    min_change = request.GET.get('min_change')

    if student_filter:
        points_history = points_history.filter(student_id=student_filter)
    if from_date:
        points_history = points_history.filter(date__gte=from_date)
    if to_date:
        points_history = points_history.filter(date__lte=to_date)
    if transaction_type:
        points_history = points_history.filter(transaction_type=transaction_type)
    if min_change:
        # For absolute value comparison (both positive and negative)
        min_val = int(min_change)
        points_history = points_history.filter(
            Q(points_change__gte=min_val) | Q(points_change__lte=-min_val)
        )
    
    # Calculate statistics for filtered records
    total_points_change = 0
    average_change = 0
    highest_change = 0
    lowest_change = 0
    total_spent = 0  # Only negative transactions
    total_earned = 0  # Only positive transactions

    if points_history.exists():
        changes = [record.points_change for record in points_history]
        total_points_change = sum(changes)
        average_change = total_points_change / len(changes)
        highest_change = max(changes)
        lowest_change = min(changes)

        # Separate spent vs earned
        total_spent = abs(sum(change for change in changes if change < 0))
        total_earned = sum(change for change in changes if change > 0)
    
    # Get student points summary (filtered by teacher) — single query instead of N get_or_create
    teacher_students_all = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    lp_map = {
        lp.student_id: lp
        for lp in LifetimePoints.objects.filter(student__teacher=teacher)
    }
    student_summary = []
    for student in teacher_students_all:
        lp = lp_map.get(student.id)
        if lp:
            student_summary.append({
                'student': student,
                'points_earned': lp.points_earned,
                'points_spent': lp.points_spent,
                'points_remaining': lp.points_remaining
            })
        else:
            student_summary.append({
                'student': student,
                'points_earned': 0,
                'points_spent': 0,
                'points_remaining': 0
            })
    
    # Sort by points earned descending
    student_summary.sort(key=lambda x: x['points_earned'], reverse=True)
    
    context = {
        'students': students,
        'points_history': points_history,
        'student_summary': student_summary,
        'total_points_change': total_points_change,
        'average_change': average_change,
        'highest_change': highest_change,
        'lowest_change': lowest_change,
        'total_spent': total_spent,
        'total_earned': total_earned,
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
                messages.success(request, f'Points deduction recorded for {student.name}.')
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
    class_filter = (request.GET.get('class_number', 'all') or 'all').strip()
    
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
        available_classes = [c for c in available_classes if c is not None and str(c).strip()]
    except (ValueError, TypeError):
        available_classes = []
    
    # Overall Rankings (filtered by teacher)
    overall_rankings = []
    students = Student.objects.filter(teacher=teacher)
    
    for student in students:
        # Filter exams by class if specified
        if class_filter != 'all':
            exams = student.exam_set.filter(class_number=class_filter)
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
                exam__class_number=class_filter
            ).distinct()
        else:
            students_in_subject = Student.objects.filter(teacher=teacher, exam__subject=subject).distinct()
        
        for student in students_in_subject:
            # Filter exams by class
            if class_filter != 'all':
                exams = student.exam_set.filter(subject=subject, class_number=class_filter)
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
        exam_dates = Exam.objects.filter(teacher=teacher, class_number=class_filter).values_list('date', flat=True).distinct()
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
                exam__class_number=class_filter
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
                    class_number=class_filter
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
                    'total_possible': total_possible,
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
            exam__class_number=class_filter
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
                class_number=class_filter
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
                'total_possible': total_possible,
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


def terms_of_service(request):
    """Terms of Service page"""
    return render(request, 'marks/terms_of_service.html')


def privacy_policy(request):
    """Privacy Policy page"""
    return render(request, 'marks/privacy_policy.html')


@login_required(login_url='login')
def manage_question_paper(request):
    """Manage exam-level question paper PDFs"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can manage question papers.')
        return redirect('dashboard')
    
    teacher = request.user
    
    if request.method == 'POST':
        exam_id = request.POST.get('exam_id')
        question_pdf = request.FILES.get('question_pdf')
        
        if exam_id and question_pdf:
            try:
                exam_id = int(exam_id)
                # Verify this exam_id belongs to this teacher
                if not Exam.objects.filter(exam_id=exam_id, teacher=teacher).exists():
                    messages.error(request, f'No exam found with ID #{exam_id}.')
                    return redirect('manage_question_paper')
                
                ExamQuestionPaper.objects.update_or_create(
                    exam_id=exam_id,
                    teacher=teacher,
                    defaults={'question_pdf': question_pdf}
                )
                messages.success(request, f'Question paper updated for Exam ID #{exam_id}.')
                return redirect('manage_question_paper')
            except (ValueError, Exception) as e:
                messages.error(request, f'Error uploading question paper: {str(e)}')
        else:
            messages.error(request, 'Please select an Exam ID and upload a PDF file.')
    
    # Get all distinct exam IDs for this teacher
    exam_ids = (Exam.objects.filter(teacher=teacher)
                .values('exam_id')
                .distinct()
                .order_by('-exam_id'))
    
    # Build exam info list
    exam_list = []
    for item in exam_ids:
        eid = item['exam_id']
        if eid is None:
            continue
        first_exam = Exam.objects.filter(exam_id=eid, teacher=teacher).select_related('subject', 'exam_type').first()
        qp = ExamQuestionPaper.objects.filter(exam_id=eid, teacher=teacher).first()
        exam_list.append({
            'exam_id': eid,
            'subject': first_exam.subject.name if first_exam else 'N/A',
            'exam_type': first_exam.exam_type.name if first_exam else 'N/A',
            'date': first_exam.date if first_exam else None,
            'chapter': first_exam.chapter or 'N/A',
            'total_marks': first_exam.total_marks if first_exam else 'N/A',
            'student_count': Exam.objects.filter(exam_id=eid, teacher=teacher).count(),
            'has_pdf': bool(qp and qp.question_pdf) or bool(first_exam and first_exam.question_pdf),
            'pdf_url': (qp.question_pdf.url if qp and qp.question_pdf else 
                       (first_exam.question_pdf.url if first_exam and first_exam.question_pdf else None)),
        })
    
    # Check if running on production
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'exam_list': exam_list,
        'is_production': is_production,
    }
    return render(request, 'marks/manage_question_paper.html', context)


@login_required(login_url='login')
def manage_answer_paper(request):
    """Manage student-level marked answer paper PDFs"""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can manage answer papers.')
        return redirect('dashboard')

    teacher = request.user
    
    if request.method == 'POST':
        exam_record_id = request.POST.get('exam_record_id')
        marked_answer_paper = request.FILES.get('marked_answer_paper')
        
        if exam_record_id and marked_answer_paper:
            try:
                exam_record = Exam.objects.get(id=int(exam_record_id), teacher=teacher)
                exam_record.marked_answer_paper = marked_answer_paper
                exam_record.save()
                messages.success(request, f'Answer paper updated for {exam_record.student.name}.')
                return redirect('manage_answer_paper')
            except (ValueError, Exam.DoesNotExist) as e:
                messages.error(request, f'Error uploading answer paper: {str(e)}')
        else:
            messages.error(request, 'Please select a student record and upload a file.')
    
    # Get all distinct exam IDs for this teacher
    exam_ids = (Exam.objects.filter(teacher=teacher)
                .values('exam_id')
                .distinct()
                .order_by('-exam_id'))
    
    exam_list = []
    for item in exam_ids:
        eid = item['exam_id']
        if eid is None:
            continue
        records = Exam.objects.filter(exam_id=eid, teacher=teacher).select_related('subject', 'exam_type', 'student')
        first_exam = records.first()
        total_students = records.count()
        students_with_paper = records.exclude(marked_answer_paper='').exclude(marked_answer_paper__isnull=True).count()
        exam_list.append({
            'exam_id': eid,
            'subject': first_exam.subject.name if first_exam else 'N/A',
            'exam_type': first_exam.exam_type.name if first_exam else 'N/A',
            'date': first_exam.date if first_exam else None,
            'chapter': first_exam.chapter or 'N/A',
            'total_marks': first_exam.total_marks if first_exam else 'N/A',
            'student_count': total_students,
            'papers_uploaded': students_with_paper,
        })
    
    # Check if running on production
    host = request.get_host().lower()
    is_production = not (host.startswith('localhost') or host.startswith('127.0.0.1'))
    
    context = {
        'exam_list': exam_list,
        'is_production': is_production,
    }
    return render(request, 'marks/manage_answer_paper.html', context)


@login_required(login_url='login')
def answer_paper_info_api(request):
    """API endpoint for fetching student records by exam_id for the answer paper management page"""
    if not is_teacher(request.user):
        return JsonResponse({'success': False, 'error': 'Not authorized'})

    teacher = request.user
    exam_id = request.GET.get('exam_id', '').strip()
    
    if not exam_id:
        return JsonResponse({'success': False, 'error': 'Please enter an exam ID'})
    
    try:
        exam_id = int(exam_id)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid exam ID'})
    
    exams = Exam.objects.filter(exam_id=exam_id, teacher=teacher).select_related('subject', 'exam_type', 'student')
    
    if not exams.exists():
        return JsonResponse({'success': False, 'error': f'No exam found with ID #{exam_id}'})
    
    first_exam = exams.first()
    next_url = reverse('manage_answer_paper')
    
    students = []
    for exam in exams:
        has_paper = bool(exam.marked_answer_paper)
        paper_url = exam.marked_answer_paper.url if has_paper else None
        students.append({
            'record_id': exam.id,
            'student_name': exam.student.name,
            'marks': exam.mark_obtained,
            'total_marks': exam.total_marks,
            'percentage': round(exam.percentage, 1),
            'grade': exam.grade,
            'has_paper': has_paper,
            'paper_url': paper_url,
            'paper_view_url': f"{reverse('exam_view_answer', args=[exam.id])}?next={next_url}" if has_paper else None,
            'paper_download_url': f"{reverse('exam_download_answer', args=[exam.id])}?next={next_url}" if has_paper else None,
        })
    
    return JsonResponse({
        'success': True,
        'exam': {
            'exam_id': exam_id,
            'subject': first_exam.subject.name,
            'exam_type': first_exam.exam_type.name,
            'date': first_exam.date.strftime('%B %d, %Y') if first_exam.date else 'N/A',
            'chapter': first_exam.chapter or 'N/A',
            'total_marks': first_exam.total_marks,
            'student_count': exams.count(),
        },
        'students': students,
    })


@login_required(login_url='login')
def exam_id_lookup_api(request):
    """API endpoint for fetching exam info by exam_id for add exam forms (auto-populate fields)"""
    if not is_teacher(request.user):
        return JsonResponse({'found': False})
    
    teacher = request.user
    exam_id = request.GET.get('exam_id', '').strip()
    
    # Always return max_exam_id
    max_id = Exam.objects.filter(teacher=teacher).values_list('exam_id', flat=True).order_by('-exam_id').first() or 0
    
    if not exam_id:
        return JsonResponse({'found': False, 'max_exam_id': max_id})
    
    try:
        exam_id = int(exam_id)
    except ValueError:
        return JsonResponse({'found': False, 'max_exam_id': max_id})
    
    # Find students who already have results for this exam_id (to exclude from dropdown)
    existing_student_ids = list(
        Exam.objects.filter(exam_id=exam_id, teacher=teacher)
        .values_list('student_id', flat=True)
    )
    
    # Build list of available students (all teacher's students minus those already recorded)
    all_students = Student.objects.filter(teacher=teacher).order_by('first_name', 'last_name')
    available_students = [
        {'id': s.id, 'display_name': s.display_name}
        for s in all_students if s.id not in existing_student_ids
    ]
    
    exams = Exam.objects.filter(exam_id=exam_id, teacher=teacher).select_related('subject', 'exam_type')
    
    if exams.exists():
        first_exam = exams.first()
        return JsonResponse({
            'found': True,
            'max_exam_id': max_id,
            'existing_student_ids': existing_student_ids,
            'available_students': available_students,
            'exam': {
                'exam_type': first_exam.exam_type.name,
                'subject_id': first_exam.subject.id,
                'date': first_exam.date.strftime('%Y-%m-%d') if first_exam.date else '',
                'total_marks': first_exam.total_marks,
                'class_number': first_exam.class_number,
                'chapter': first_exam.chapter or '',
            }
        })

    # Also search ExamCenterExam (upcoming/finished exams) by exam_display_id
    ec_exam = ExamCenterExam.objects.filter(
        exam_display_id=str(exam_id), teacher=teacher
    ).first()

    if ec_exam:
        # Map ExamCenterExam subject (string) to Subject FK id
        subject_match = Subject.objects.filter(name__iexact=ec_exam.subject, teacher=teacher).first()
        subject_id = subject_match.id if subject_match else ''

        return JsonResponse({
            'found': True,
            'max_exam_id': max_id,
            'source': 'exam_center',
            'existing_student_ids': existing_student_ids,
            'available_students': available_students,
            'exam': {
                'exam_type': ec_exam.exam_type.upper(),  # 'cq' -> 'CQ', 'mcq' -> 'MCQ'
                'subject_id': subject_id,
                'date': ec_exam.exam_date.strftime('%Y-%m-%d') if ec_exam.exam_date else '',
                'total_marks': ec_exam.total_marks,
                'class_number': ec_exam.class_number,
                'chapter': ec_exam.chapter or '',
            }
        })

    # Exam ID not found yet — all students are available
    return JsonResponse({
        'found': False,
        'max_exam_id': max_id,
        'existing_student_ids': existing_student_ids,
        'available_students': available_students,
    })


@login_required(login_url='login')
def exam_info_api(request):
    """API endpoint for fetching exam info by exam_id for the question paper management page"""
    if not is_teacher(request.user):
        return JsonResponse({'success': False, 'error': 'Not authorized'})
    
    teacher = request.user
    exam_id = request.GET.get('exam_id', '').strip()
    
    if not exam_id:
        return JsonResponse({'success': False, 'error': 'Please enter an exam ID'})
    
    try:
        exam_id = int(exam_id)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid exam ID'})
    
    exams = Exam.objects.filter(exam_id=exam_id, teacher=teacher).select_related('subject', 'exam_type')
    
    if not exams.exists():
        return JsonResponse({'success': False, 'error': f'No exam found with ID #{exam_id}'})
    
    first_exam = exams.first()
    qp = ExamQuestionPaper.objects.filter(exam_id=exam_id, teacher=teacher).first()
    
    # Check legacy field too
    has_pdf = bool(qp and qp.question_pdf) or bool(first_exam.question_pdf)
    pdf_url = None
    if qp and qp.question_pdf:
        pdf_url = qp.question_pdf.url
    elif first_exam.question_pdf:
        pdf_url = first_exam.question_pdf.url
    
    return JsonResponse({
        'success': True,
        'exam': {
            'exam_id': exam_id,
            'subject': first_exam.subject.name,
            'exam_type': first_exam.exam_type.name,
            'date': first_exam.date.strftime('%B %d, %Y') if first_exam.date else 'N/A',
            'chapter': first_exam.chapter or 'N/A',
            'total_marks': first_exam.total_marks,
            'student_count': exams.count(),
            'has_pdf': has_pdf,
            'pdf_url': pdf_url,
        }
    })


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
    # Count exams with question papers from both ExamQuestionPaper and legacy Exam field
    exam_ids_with_new_pdf = set(ExamQuestionPaper.objects.filter(teacher=teacher).values_list('exam_id', flat=True))
    exam_ids_with_legacy_pdf = set(qs.exclude(question_pdf='').exclude(question_pdf__isnull=True).values_list('exam_id', flat=True).distinct())
    exams_with_pdf = len(exam_ids_with_new_pdf | exam_ids_with_legacy_pdf)
    
    # Calculate marked answer paper stats for students
    exams_with_answer_sheet = 0
    total_student_exams = 0
    total_student_unique_exams = 0
    
    if is_student(request.user):
        # Get the student record for the logged-in user
        student = request.user.student_profile.student
        student_exams = qs.filter(student=student)
        total_student_exams = student_exams.count()
        total_student_unique_exams = student_exams.values('exam_id').distinct().count()
        exams_with_answer_sheet = student_exams.exclude(marked_answer_paper='').exclude(marked_answer_paper__isnull=True).count()
        # For students, filter exams_with_pdf to only exams they participated in
        student_exam_ids = set(student_exams.values_list('exam_id', flat=True).distinct())
        exams_with_pdf = len((exam_ids_with_new_pdf | exam_ids_with_legacy_pdf) & student_exam_ids)
    
    # Calculate percentages
    pdf_denom = total_student_unique_exams if is_student(request.user) and total_student_unique_exams > 0 else total_exams
    pdf_percentage = round((exams_with_pdf / pdf_denom * 100), 1) if pdf_denom > 0 else 0
    answer_sheet_percentage = round((exams_with_answer_sheet / total_student_exams * 100), 1) if total_student_exams > 0 else 0

    context = {
        'min_exam_id': min_exam_id or 'N/A',
        'max_exam_id': max_exam_id or 'N/A',
        'exams_with_pdf': exams_with_pdf,
        'total_exams': total_exams,
        'total_student_unique_exams': total_student_unique_exams,
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
    next_url = reverse('exam_lookup')
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
    
    # Get PDF URL if available (check ExamQuestionPaper first, then legacy)
    pdf_url = None
    try:
        qp = ExamQuestionPaper.objects.get(exam_id=first_exam.exam_id, teacher=teacher)
        if qp.question_pdf:
            pdf_url = qp.question_pdf.url
    except ExamQuestionPaper.DoesNotExist:
        # Fallback to legacy field on Exam
        if first_exam.question_pdf:
            pdf_url = first_exam.question_pdf.url

    # If the user is a student who didn't participate, hide the question paper
    student_participated_in_exam = None
    if is_student(request.user):
        try:
            student = request.user.student_profile.student
            student_participated_in_exam = exams.filter(student=student).exists()
            if not student_participated_in_exam:
                pdf_url = None
        except Exception:
            student_participated_in_exam = False
            pdf_url = None
    
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
            marked_answer_view_url = reverse('exam_view_answer', args=[student_exam.pk]) if student_exam.marked_answer_paper else None
            marked_answer_download_url = reverse('exam_download_answer', args=[student_exam.pk]) if student_exam.marked_answer_paper else None

            student_data = {
                'student_name': student_exam.student.name,
                'marks': student_marks,
                'total_marks': student_total,
                'percentage': student_percentage,
                'has_marked_answer': marked_answer_url is not None,
                'marked_answer_url': marked_answer_url,
                'marked_answer_view_url': f"{marked_answer_view_url}?next={next_url}" if marked_answer_view_url else None,
                'marked_answer_download_url': f"{marked_answer_download_url}?next={next_url}" if marked_answer_download_url else None,
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
                'marked_answer_view_url': f"{reverse('exam_view_answer', args=[exam.pk])}?next={next_url}" if marked_answer_url else None,
                'marked_answer_download_url': f"{reverse('exam_download_answer', args=[exam.pk])}?next={next_url}" if marked_answer_url else None,
            })

    # For backward compatibility, keep the old fields for student view
    student_marks = student_data['marks'] if student_data else None
    student_total = student_data['total_marks'] if student_data else None
    student_percentage = student_data['percentage'] if student_data else None
    marked_answer_url = student_data['marked_answer_url'] if student_data else None
    marked_answer_view_url = student_data['marked_answer_view_url'] if student_data else None
    marked_answer_download_url = student_data['marked_answer_download_url'] if student_data else None

    # Compute class average and lowest score for desktop stats
    total_participants = exams.count()
    if total_participants > 0:
        total_marks_sum = sum(e.mark_obtained for e in exams)
        total_possible_sum = sum(e.total_marks for e in exams)
        class_average = round((total_marks_sum / total_possible_sum) * 100, 1) if total_possible_sum > 0 else 0
        lowest_percentage = round(min(e.percentage for e in exams), 1)
        marked_papers_count = sum(1 for e in exams if e.marked_answer_paper)
    else:
        class_average = 0
        lowest_percentage = 0
        marked_papers_count = 0

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
            'total_participants': total_participants,
            'class_average': class_average,
            'lowest_percentage': lowest_percentage,
            'marked_papers_count': marked_papers_count,
            'has_pdf': pdf_url is not None,
            'pdf_url': pdf_url,
            'has_marked_answer': marked_answer_url is not None,
            'marked_answer_url': marked_answer_url,
            'marked_answer_view_url': marked_answer_view_url,
            'marked_answer_download_url': marked_answer_download_url,
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
            pdfs_count = ExamQuestionPaper.objects.filter(teacher=teacher).count()
            marked_answer_papers_count = Exam.objects.filter(teacher=teacher).exclude(marked_answer_paper__isnull=True).exclude(marked_answer_paper='').count()

            return render(request, 'marks/delete_account_confirm.html', {
                'step': 3,
                'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
                'students_count': students_count,
                'subjects_count': subjects_count,
                'exams_count': exams_count,
                'points_spent_count': points_spent_count,
                'pdfs_count': pdfs_count,
                'marked_answer_papers_count': marked_answer_papers_count,
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
                pdfs_count = ExamQuestionPaper.objects.filter(teacher=teacher).count()
                marked_answer_papers_count = Exam.objects.filter(teacher=teacher).exclude(marked_answer_paper__isnull=True).exclude(marked_answer_paper='').count()

                return render(request, 'marks/delete_account_confirm.html', {
                    'step': 3,
                    'warning_message': 'This action is irreversible. Once deleted, your account and all associated data cannot be recovered.',
                    'students_count': students_count,
                    'subjects_count': subjects_count,
                    'exams_count': exams_count,
                    'points_spent_count': points_spent_count,
                    'pdfs_count': pdfs_count,
                    'marked_answer_papers_count': marked_answer_papers_count,
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
        # Delete linked guest account (if present) before deleting teacher.
        guest_account = GuestTeacherAccount.objects.filter(teacher=teacher).select_related('guest_user').first()
        if guest_account:
            delete_guest_user_account(guest_account)

        # Step 0: Delete Cloudinary PDF files uploaded by this teacher
        cloudinary_files_deleted = 0
        try:
            # Get all exams created by this teacher that have PDF files
            teacher_exams = Exam.objects.filter(teacher=teacher).filter(
                Q(question_pdf__isnull=False) & ~Q(question_pdf='') |
                Q(marked_answer_paper__isnull=False) & ~Q(marked_answer_paper='')
            )

            # Collect all Cloudinary public IDs from both fields
            cloudinary_public_ids = []
            for exam in teacher_exams:
                if exam.question_pdf_public_id:
                    cloudinary_public_ids.append(exam.question_pdf_public_id)
                if exam.marked_answer_paper_public_id:
                    cloudinary_public_ids.append(exam.marked_answer_paper_public_id)

            # Remove duplicates
            cloudinary_public_ids = list(set(cloudinary_public_ids))

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

                print(f"Deleted {cloudinary_files_deleted} Cloudinary files for teacher '{teacher.username}'")

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
        

def health(request):
    return HttpResponse("OK", content_type="text/plain")