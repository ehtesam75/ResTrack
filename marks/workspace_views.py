"""
Phase 7 — Workspace management views (plan §9).

Endpoints (all teacher-only, all enforce workspace.teacher == request.user):
  - workspace_list         GET  /workspaces/
  - workspace_create       GET/POST /workspaces/create/
  - workspace_edit         GET/POST /workspaces/<pk>/edit/
  - workspace_archive      POST     /workspaces/<pk>/archive/
  - workspace_restore      POST     /workspaces/<pk>/restore/
  - workspace_delete       GET/POST /workspaces/<pk>/delete/   (type-to-confirm)
  - workspace_switch       POST     /workspaces/<pk>/switch/   (CSRF)

Switcher is hidden for students and guest sessions. Switching from a guest
session is refused (defense — plan §7).
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .guest_access import get_guest_account_for_request
from .models import (
    Exam,
    ExamCenterExam,
    ExamType,
    PointsSpent,
    Student,
    StudentProfile,
    Subject,
    Workspace,
)
from .workspaces import set_active_workspace


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

def _require_teacher(request):
    """Return (teacher_user, error_response). teacher_user is None for non-teachers."""
    if not request.user.is_authenticated:
        return None, redirect('login')
    if not hasattr(request.user, 'teacher_profile'):
        # Students never see workspace pages.
        return None, HttpResponseForbidden('Only teachers can manage workspaces.')
    return request.user, None


def _get_owned_workspace(request, pk):
    """Return the workspace iff it belongs to the requesting teacher, else 404."""
    if not request.user.is_authenticated:
        return None
    return get_object_or_404(Workspace, pk=pk, teacher=request.user)


def _next_slug_number(teacher):
    last = (
        Workspace.objects
        .filter(teacher=teacher)
        .order_by('-slug_number')
        .values_list('slug_number', flat=True)
        .first()
    )
    return (last or 0) + 1


# --------------------------------------------------------------------
# Views
# --------------------------------------------------------------------

@login_required
def workspace_list(request):
    teacher, err = _require_teacher(request)
    if err:
        return err

    all_ws = list(Workspace.objects.filter(teacher=teacher).order_by('slug_number'))
    active = getattr(request, 'workspace', None) if getattr(request, 'user', None) and request.user.is_authenticated else None
    if active and active.teacher_id != teacher.id:
        active = None

    # Per-workspace counts pre-computed into a list of dicts so templates can iterate without filters.
    workspaces_with_counts = []
    for ws in all_ws:
        workspaces_with_counts.append({
            'workspace': ws,
            'students': Student.objects.filter(workspace=ws).count(),
            'subjects': Subject.objects.filter(workspace=ws).count(),
            'exam_types': ExamType.objects.filter(workspace=ws).count(),
            'exams': Exam.objects.filter(workspace=ws).count(),
            'exam_centers': ExamCenterExam.objects.filter(workspace=ws).count(),
        })

    context = {
        'workspaces_with_counts': workspaces_with_counts,
        'active_workspace': active,
        'total_points_spent': PointsSpent.objects.filter(workspace__teacher=teacher).count(),
    }
    return render(request, 'marks/workspace_list.html', context)


@login_required
def workspace_create(request):
    teacher, err = _require_teacher(request)
    if err:
        return err

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        description = (request.POST.get('description') or '').strip()
        if not name:
            messages.error(request, 'Workspace name is required.')
        elif len(name) > 120:
            messages.error(request, 'Workspace name must be 120 characters or fewer.')
        else:
            with transaction.atomic():
                ws = Workspace.objects.create(
                    teacher=teacher,
                    name=name,
                    description=description,
                    slug_number=_next_slug_number(teacher),
                )
                # Make the brand-new workspace the active one so the teacher lands in it.
                set_active_workspace(request, ws)
            messages.success(request, f'Workspace "{ws.name}" created.')
            return redirect('workspace_list')

    return render(request, 'marks/workspace_form.html', {
        'form_mode': 'create',
        'form_action': reverse('workspace_create'),
        'workspace': None,
        'name_value': '',
        'description_value': '',
    })


@login_required
def workspace_edit(request, pk):
    teacher, err = _require_teacher(request)
    if err:
        return err
    ws = _get_owned_workspace(request, pk)
    if ws is None:
        return redirect('workspace_list')

    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        description = (request.POST.get('description') or '').strip()
        if not name:
            messages.error(request, 'Workspace name is required.')
        elif len(name) > 120:
            messages.error(request, 'Workspace name must be 120 characters or fewer.')
        else:
            ws.name = name
            ws.description = description
            ws.save(update_fields=['name', 'description', 'updated_at'])
            messages.success(request, f'Workspace "{ws.name}" updated.')
            return redirect('workspace_list')

    return render(request, 'marks/workspace_form.html', {
        'form_mode': 'edit',
        'form_action': reverse('workspace_edit', args=[ws.pk]),
        'workspace': ws,
        'name_value': ws.name,
        'description_value': ws.description,
    })


@login_required
@require_POST
def workspace_archive(request, pk):
    teacher, err = _require_teacher(request)
    if err:
        return err
    ws = _get_owned_workspace(request, pk)
    if ws is None:
        return redirect('workspace_list')

    if ws.is_archived:
        messages.info(request, f'"{ws.name}" is already archived.')
        return redirect('workspace_list')

    active_non_archived = (
        Workspace.objects
        .filter(teacher=teacher, is_archived=False)
        .exclude(pk=ws.pk)
        .exists()
    )
    if not active_non_archived:
        messages.error(
            request,
            'You cannot archive your only active workspace. Create another workspace first.',
        )
        return redirect('workspace_list')

    ws.is_archived = True
    ws.save(update_fields=['is_archived', 'updated_at'])

    # If the archived workspace was the active one, switch the teacher to another.
    if getattr(request, 'workspace', None) and request.workspace.pk == ws.pk:
        next_active = (
            Workspace.objects
            .filter(teacher=teacher, is_archived=False)
            .order_by('slug_number')
            .first()
        )
        if next_active:
            set_active_workspace(request, next_active)
            messages.success(request, f'"{ws.name}" archived. Switched to "{next_active.name}".')
        else:
            messages.warning(request, f'"{ws.name}" archived.')

    return redirect('workspace_list')


@login_required
@require_POST
def workspace_restore(request, pk):
    teacher, err = _require_teacher(request)
    if err:
        return err
    ws = _get_owned_workspace(request, pk)
    if ws is None:
        return redirect('workspace_list')

    if not ws.is_archived:
        messages.info(request, f'"{ws.name}" is already active.')
        return redirect('workspace_list')

    ws.is_archived = False
    ws.save(update_fields=['is_archived', 'updated_at'])
    messages.success(request, f'"{ws.name}" restored.')
    return redirect('workspace_list')


@login_required
def workspace_delete(request, pk):
    teacher, err = _require_teacher(request)
    if err:
        return err
    ws = _get_owned_workspace(request, pk)
    if ws is None:
        return redirect('workspace_list')

    remaining_non_archived = (
        Workspace.objects
        .filter(teacher=teacher, is_archived=False)
        .exclude(pk=ws.pk)
        .count()
    )
    remaining_archived = (
        Workspace.objects
        .filter(teacher=teacher, is_archived=True)
        .exclude(pk=ws.pk)
        .count()
    )

    # Safety guard: refuse if this is the last remaining workspace (§9 plan).
    if remaining_non_archived == 0 and remaining_archived == 0:
        messages.error(
            request,
            'You cannot delete your only workspace. Create another workspace first.',
        )
        return redirect('workspace_list')

    if request.method == 'POST':
        confirm = (request.POST.get('confirm_name') or '').strip()
        if confirm != ws.name:
            messages.error(request, 'Confirmation name did not match. Deletion cancelled.')
            return redirect('workspace_delete', pk=ws.pk)

        deleted_name = ws.name
        # Switch active workspace away before we delete.
        if getattr(request, 'workspace', None) and request.workspace.pk == ws.pk:
            replacement = (
                Workspace.objects
                .filter(teacher=teacher)
                .exclude(pk=ws.pk)
                .order_by('slug_number')
                .first()
            )
            if replacement:
                set_active_workspace(request, replacement)

        # CASCADE on every workspace FK removes this workspace's rows; delete explicit Student users.
        with transaction.atomic():
            User = get_user_model()
            student_user_ids = list(
                StudentProfile.objects
                .filter(student__workspace=ws, user__isnull=False)
                .values_list('user_id', flat=True)
            )
            ws.delete()
            if student_user_ids:
                User.objects.filter(id__in=student_user_ids).delete()

        messages.success(request, f'Workspace "{deleted_name}" deleted.')
        return redirect('workspace_list')

    summary = {
        'students': Student.objects.filter(workspace=ws).count(),
        'subjects': Subject.objects.filter(workspace=ws).count(),
        'exam_types': ExamType.objects.filter(workspace=ws).count(),
        'exams': Exam.objects.filter(workspace=ws).count(),
        'exam_centers': ExamCenterExam.objects.filter(workspace=ws).count(),
    }
    return render(request, 'marks/workspace_confirm_delete.html', {
        'workspace': ws,
        'summary': summary,
        'remaining_non_archived': remaining_non_archived,
    })


@login_required
@require_POST
def workspace_switch(request, pk):
    """POST-only — CSRF protects against silent workspace switches via crafted links."""
    teacher, err = _require_teacher(request)
    if err:
        return err

    # Guests cannot switch (they are pinned to one workspace per plan §7).
    if get_guest_account_for_request(request) is not None:
        return HttpResponseForbidden('Guest sessions cannot switch workspaces.')

    ws = _get_owned_workspace(request, pk)
    if ws is None:
        return redirect('workspace_list')
    if ws.is_archived:
        messages.error(request, 'Cannot switch to an archived workspace.')
        return redirect('workspace_list')

    set_active_workspace(request, ws)
    next_url = request.POST.get('next') or reverse('dashboard')
    # Only allow same-site redirects.
    if not next_url.startswith('/'):
        next_url = reverse('dashboard')
    return HttpResponseRedirect(next_url)