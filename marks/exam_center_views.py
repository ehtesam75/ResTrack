"""
Views for the Exam Center feature.
Handles exam CRUD (teacher), exam detail / participation (student),
answer submission, bonus-time grants, and real-time status API.
"""

import json
import datetime as _dt

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ExamCenterExam, AnswerSubmission
from .forms import ExamCenterExamForm
from .views import is_teacher, is_student, get_teacher_for_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ordered_active_exams(teacher):
    """Return non-finished exams ordered by priority (running first, then latest upcoming)."""
    all_exams = ExamCenterExam.objects.filter(teacher=teacher)
    running = []
    submission = []
    upcoming = []
    for e in all_exams:
        s = e.computed_status
        if s == 'running':
            running.append(e)
        elif s == 'submission':
            submission.append(e)
        elif s == 'upcoming':
            upcoming.append(e)
    # Sort upcoming by start_datetime descending (latest first)
    upcoming.sort(key=lambda e: e.start_datetime, reverse=True)
    return running + submission + upcoming


def _get_finished_exams(teacher):
    """Return finished exams, newest first."""
    all_exams = ExamCenterExam.objects.filter(teacher=teacher)
    finished = [e for e in all_exams if e.is_finished]
    finished.sort(key=lambda e: e.final_end_datetime, reverse=True)
    return finished


def _iso(dt):
    """Format a datetime to ISO-8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@login_required
def exam_center(request):
    """Main Exam Center page – lists upcoming & finished exams."""
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        messages.error(request, 'Unable to determine your teacher account.')
        return redirect('dashboard')

    active_exams = _get_ordered_active_exams(teacher)
    finished_exams = _get_finished_exams(teacher)
    can_create = ExamCenterExam.can_create_exam(teacher)
    active_count = len(active_exams)

    context = {
        'active_exams': active_exams,
        'finished_exams': finished_exams,
        'can_create': can_create,
        'active_count': active_count,
        'is_teacher': is_teacher(request.user),
        'is_student': is_student(request.user),
        'server_now': _iso(timezone.now()),
    }
    return render(request, 'marks/exam_center.html', context)


# ---------------------------------------------------------------------------
# Create / Edit / Delete (teacher only)
# ---------------------------------------------------------------------------

@login_required
def exam_center_create(request):
    """Create a new Exam Center exam (teacher only)."""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can create exams.')
        return redirect('exam_center')

    if not ExamCenterExam.can_create_exam(request.user):
        messages.warning(request, 'You already have 3 active exams. Wait until one finishes.')
        return redirect('exam_center')

    if request.method == 'POST':
        form = ExamCenterExamForm(request.POST, request.FILES, teacher=request.user)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.teacher = request.user
            exam.save()
            return redirect('exam_center')
    else:
        form = ExamCenterExamForm(teacher=request.user)

    context = {
        'form': form,
        'editing': False,
        'can_create': ExamCenterExam.can_create_exam(request.user),
    }
    return render(request, 'marks/exam_center_create.html', context)


@login_required
def exam_center_edit(request, exam_id):
    """Edit an upcoming exam (teacher only, before it starts)."""
    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=request.user)

    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can edit exams.')
        return redirect('exam_center')

    if not exam.is_upcoming:
        messages.warning(request, 'Only upcoming exams can be edited.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    if request.method == 'POST':
        form = ExamCenterExamForm(request.POST, request.FILES, instance=exam, teacher=request.user)
        if form.is_valid():
            form.save()
            return redirect('exam_center')
    else:
        form = ExamCenterExamForm(instance=exam, teacher=request.user)

    context = {
        'form': form,
        'editing': True,
        'exam': exam,
    }
    return render(request, 'marks/exam_center_create.html', context)


@login_required
@require_POST
def exam_center_delete(request, exam_id):
    """Delete an upcoming exam (teacher only)."""
    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=request.user)

    if not is_teacher(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    if not exam.is_upcoming:
        messages.warning(request, 'Only upcoming exams can be deleted.')
        return redirect('exam_center')

    label = exam.exam_display_id
    exam.delete()
    return redirect('exam_center')


# ---------------------------------------------------------------------------
# Detail page (student & teacher)
# ---------------------------------------------------------------------------

@login_required
def exam_center_detail(request, exam_id):
    """Exam detail – countdown, PDF viewer, submission form, etc."""
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=teacher)
    status = exam.computed_status
    now = timezone.now()

    # Submission info for current student
    submissions = []
    submission_count = 0
    if is_student(request.user) and exam.exam_mode == 'online':
        submissions = AnswerSubmission.objects.filter(
            exam=exam, student_user=request.user
        ).order_by('-submitted_at')
        submission_count = submissions.count()

    # All submissions for teacher (finished online exams)
    all_submissions = []
    if is_teacher(request.user) and exam.exam_mode == 'online':
        all_submissions = AnswerSubmission.objects.filter(
            exam=exam, is_final=True
        ).select_related('student_user').order_by('student_user__student_profile__student__first_name')

    context = {
        'exam': exam,
        'status': status,
        'is_teacher': is_teacher(request.user),
        'is_student': is_student(request.user),
        'submissions': submissions,
        'submission_count': submission_count,
        'max_submissions': 3,
        'all_submissions': all_submissions,
        'server_now': _iso(now),
        'start_iso': _iso(exam.start_datetime),
        'exam_end_iso': _iso(exam.exam_end_datetime),
        'final_end_iso': _iso(exam.final_end_datetime),
    }
    return render(request, 'marks/exam_center_detail.html', context)


# ---------------------------------------------------------------------------
# Answer submission (student, online exam only)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def exam_center_submit_answer(request, exam_id):
    """Handle answer-sheet upload during submission period."""
    teacher = get_teacher_for_user(request.user)
    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=teacher)

    if not is_student(request.user):
        messages.error(request, 'Only students can submit answers.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    if exam.exam_mode != 'online':
        messages.error(request, 'This is an offline exam – no submission needed.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    status = exam.computed_status
    if status not in ('running', 'submission'):
        messages.error(request, 'Answer submission is not open for this exam.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    # Check attempt count
    existing = AnswerSubmission.objects.filter(exam=exam, student_user=request.user)
    if existing.count() >= 3:
        messages.error(request, 'You have reached the maximum of 3 submission attempts.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    answer_file = request.FILES.get('answer_file')
    if not answer_file:
        messages.error(request, 'Please select a file to upload.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    # Validate file type
    allowed_ext = ('.pdf', '.zip', '.rar')
    if not answer_file.name.lower().endswith(allowed_ext):
        messages.error(request, 'Only PDF, ZIP, or RAR files are allowed.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    # Validate file size (10 MB)
    if answer_file.size > 10 * 1024 * 1024:
        messages.error(request, 'File must be 10 MB or smaller.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    # Mark all previous submissions as not final
    existing.update(is_final=False)

    # Create new submission
    AnswerSubmission.objects.create(
        exam=exam,
        student_user=request.user,
        answer_file=answer_file,
        is_final=True,
    )

    return redirect('exam_center_detail', exam_id=exam.pk)


# ---------------------------------------------------------------------------
# Bonus time (teacher, AJAX)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def exam_center_bonus_time(request, exam_id):
    """Grant bonus time to an exam (teacher only)."""
    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=request.user)

    if not is_teacher(request.user):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    status = exam.computed_status
    if status not in ('running', 'submission'):
        return JsonResponse({'error': 'Bonus time can only be granted during a running exam or submission period.'}, status=400)

    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else {}
        minutes = int(data.get('minutes', 0) or request.POST.get('minutes', 0))
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid minutes value.'}, status=400)

    if status == 'running':
        # During running: max 15 min per grant, adds to exam duration
        if minutes < 1 or minutes > 15:
            return JsonResponse({'error': 'Bonus time during exam must be between 1 and 15 minutes.'}, status=400)
        exam.exam_bonus_minutes += minutes
    else:
        # During submission: any amount, adds to submission time
        if minutes < 1 or minutes > 120:
            return JsonResponse({'error': 'Bonus time must be between 1 and 120 minutes.'}, status=400)
        exam.submission_bonus_minutes += minutes

    exam.save(update_fields=['exam_bonus_minutes', 'submission_bonus_minutes', 'updated_at'])

    return JsonResponse({
        'success': True,
        'exam_bonus': exam.exam_bonus_minutes,
        'submission_bonus': exam.submission_bonus_minutes,
        'final_end_iso': _iso(exam.final_end_datetime),
        'exam_end_iso': _iso(exam.exam_end_datetime),
    })


# ---------------------------------------------------------------------------
# Status API (AJAX polling)
# ---------------------------------------------------------------------------

@login_required
def exam_center_status_api(request, exam_id):
    """Return current exam status and timestamps (for JS timer sync)."""
    teacher = get_teacher_for_user(request.user)
    if not teacher:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=teacher)

    return JsonResponse({
        'status': exam.computed_status,
        'status_label': exam.status_label,
        'server_now': _iso(timezone.now()),
        'start_iso': _iso(exam.start_datetime),
        'exam_end_iso': _iso(exam.exam_end_datetime),
        'final_end_iso': _iso(exam.final_end_datetime),
        'exam_bonus_minutes': exam.exam_bonus_minutes,
        'submission_bonus_minutes': exam.submission_bonus_minutes,
        'exam_mode': exam.exam_mode,
    })


# ---------------------------------------------------------------------------
# Teacher submissions view
# ---------------------------------------------------------------------------

@login_required
def exam_center_submissions(request, exam_id):
    """View all student submissions for a finished online exam (teacher only)."""
    if not is_teacher(request.user):
        messages.error(request, 'Only teachers can view submissions.')
        return redirect('exam_center')

    exam = get_object_or_404(ExamCenterExam, pk=exam_id, teacher=request.user)

    if exam.exam_mode != 'online':
        messages.info(request, 'Offline exams do not have answer submissions.')
        return redirect('exam_center_detail', exam_id=exam.pk)

    submissions = AnswerSubmission.objects.filter(
        exam=exam, is_final=True
    ).select_related('student_user')

    # Build a list with student info
    submission_list = []
    for sub in submissions:
        try:
            student_name = sub.student_user.student_profile.student.name
        except Exception:
            student_name = sub.student_user.username
        submission_list.append({
            'student_name': student_name,
            'file_url': sub.answer_file.url if sub.answer_file else None,
            'submitted_at': sub.submitted_at,
            'total_attempts': AnswerSubmission.objects.filter(
                exam=exam, student_user=sub.student_user
            ).count(),
        })

    context = {
        'exam': exam,
        'submission_list': submission_list,
        'status': exam.computed_status,
    }
    return render(request, 'marks/exam_center_submissions.html', context)
