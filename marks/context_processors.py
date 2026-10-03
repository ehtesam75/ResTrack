from .guest_access import get_guest_account_for_request
from .workspaces import get_active_workspace, get_workspace_for_user


def guest_session_context(request):
    guest_account = get_guest_account_for_request(request)
    return {
        'is_guest_session': guest_account is not None,
        'guest_session_username': guest_account.guest_user.username if guest_account else '',
    }


def workspace_context(request):
    """Expose the active workspace and the teacher's full workspace list to
    every template so the switcher / chips can render without a view-layer
    detour.

    Returns:
        dict with keys:
            - active_workspace: Workspace instance or None
            - available_workspaces: list of all workspaces owned by the current
              teacher, ordered by slug_number (empty for non-teachers / anonymous)
            - active_workspaces: list of non-archived workspaces (the switchable
              set; never contains the active workspace's archived entry)
            - show_workspace_chip: True when the user is a teacher (always show
              the current-workspace chip even if there's only one workspace)
            - show_workspace_switcher: True when the teacher has more than one
              non-archived workspace (drives the dropdown chevron)
    """
    active_workspace = getattr(request, 'workspace', None)
    if active_workspace is None and request.user.is_authenticated:
        # Fallback: lazy resolve (covers cases where middleware didn't run).
        active_workspace = get_active_workspace(request)

    available_workspaces = []
    active_workspaces = []  # non-archived only, used by the switcher dropdown
    show_workspace_chip = False
    show_workspace_switcher = False

    if request.user.is_authenticated and hasattr(request.user, 'teacher_profile'):
        from .models import Workspace
        available_workspaces = list(
            Workspace.objects.filter(teacher=request.user).order_by('slug_number')
        )
        active_workspaces = [ws for ws in available_workspaces if not ws.is_archived]
        show_workspace_chip = True
        show_workspace_switcher = len(active_workspaces) > 1

    return {
        'active_workspace': active_workspace,
        'available_workspaces': available_workspaces,
        'active_workspaces': active_workspaces,
        'show_workspace_chip': show_workspace_chip,
        'show_workspace_switcher': show_workspace_switcher,
    }
