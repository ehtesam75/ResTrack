"""Workspace resolution middleware.

Resolves ``request.workspace`` once per request using
``marks.workspaces.get_active_workspace``. The resolved workspace is also
exposed via ``request.active_workspace`` (alias) and used by downstream code
to scope queries.
"""

from .workspaces import get_active_workspace


class WorkspaceMiddleware:
    """Attach ``request.workspace`` (and ``request.active_workspace``) for
    every request. Returns ``None`` for anonymous users and students; views
    should handle ``None`` appropriately.

    This middleware must run *after* ``GuestReadOnlyMiddleware`` so the guest
    account is already attached to the request (we use it during resolution).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        workspace = get_active_workspace(request)
        request.workspace = workspace
        request.active_workspace = workspace
        return self.get_response(request)