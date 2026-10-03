"""
Active workspace resolution.

A teacher can own many workspaces. Every request needs to know *which* one is
"active" so all queries can filter on it.

Resolution order (per plan §3):

1. Cache: ``request.workspace`` already populated → return it.
2. Anonymous or non-teacher user → return ``None``.
3. Guest session → if the guest is pinned to a workspace, return it;
   otherwise return the teacher's oldest non-archived workspace.
4. Read session key ``active_workspace_id`` and look it up with
   ``teacher=request.user`` (security: never trust the session value alone).
5. Fallback: oldest non-archived workspace for this user.
6. Last-resort: auto-create a "Default Workspace" (slug_number=1) so
   a brand-new teacher always has something to render.

The cache is stored on ``request._workspace_cache`` so repeated calls within
the same request are O(1).
"""

from __future__ import annotations

from django.contrib.auth.models import User

from .guest_access import get_guest_account_for_request


ACTIVE_WORKSPACE_SESSION_KEY = 'active_workspace_id'


def get_student_workspace(user):
    """Return the workspace a student-user belongs to, or ``None``.

    A student is linked to a ``Student`` via ``StudentProfile``. The student's
    workspace is the source of truth — never read from the session for a
    student session.
    """
    if not user or not user.is_authenticated:
        return None
    profile = getattr(user, 'student_profile', None)
    if profile is None:
        return None
    student = profile.student
    return student.workspace if student else None


def get_workspace_for_user(user, *, include_archived: bool = False):
    """Return the teacher's oldest workspace (creating one if necessary).

    Args:
        user: A Django auth user.
        include_archived: If ``True``, archived workspaces may be returned.

    Used for teachers and for guests (who are scoped to a teacher).
    """
    if not user or not user.is_authenticated:
        return None

    # Lazy import to avoid circular dependency at module load time.
    from .models import Workspace

    qs = Workspace.objects.filter(teacher=user)
    if not include_archived:
        qs = qs.filter(is_archived=False)
    ws = qs.order_by('slug_number').first()
    if ws is not None:
        return ws

    # No workspace yet — auto-create the default.
    return _ensure_default_workspace(user)


def _ensure_default_workspace(user):
    """Create slug_number=1 workspace if this teacher has none."""
    from .models import Workspace
    ws, _created = Workspace.objects.get_or_create(
        teacher=user,
        slug_number=1,
        defaults={
            'name': 'Default Workspace',
        },
    )
    return ws


def set_active_workspace(request, workspace):
    """Persist the active workspace on the session and the request cache."""
    request.session[ACTIVE_WORKSPACE_SESSION_KEY] = workspace.id
    request._workspace_cache = workspace


def get_active_workspace(request):
    """Return the active workspace for this request, or ``None``.

    See module docstring for the resolution order.
    """
    cached = getattr(request, '_workspace_cache', None)
    if cached is not None:
        return cached
    workspace = _resolve_active_workspace(request)
    request._workspace_cache = workspace
    return workspace


def _resolve_active_workspace(request):
    if not request.user.is_authenticated:
        return None

    # Students don't use the switcher — their workspace is the student's.
    if not hasattr(request.user, 'teacher_profile'):
        # Not a teacher (e.g. student user) — return None to keep view code simple.
        return get_student_workspace(request.user)

    # Guest sessions: pinned workspace if set, else teacher's oldest active.
    guest_account = get_guest_account_for_request(request)
    if guest_account is not None:
        if guest_account.workspace_id:
            from .models import Workspace
            ws = Workspace.objects.filter(
                id=guest_account.workspace_id,
                teacher=guest_account.teacher,
            ).first()
            if ws is not None:
                return ws
        return get_workspace_for_user(guest_account.teacher)

    # Teacher: try session key first, but always re-validate ownership.
    from .models import Workspace
    session_id = request.session.get(ACTIVE_WORKSPACE_SESSION_KEY)
    if session_id:
        ws = Workspace.objects.filter(
            id=session_id,
            teacher=request.user,
        ).first()
        if ws is not None and not ws.is_archived:
            return ws

    # Fallback: teacher's oldest non-archived workspace.
    return get_workspace_for_user(request.user)
