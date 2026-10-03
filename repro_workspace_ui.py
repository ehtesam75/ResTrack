"""Verify the workspace UI is discoverable and usable for a real teacher.

Simulates the actual browser flow (login -> dashboard -> switcher -> create ->
manage -> edit -> archive -> restore -> switch -> delete) against a throwaway
test database, and asserts the controls are present in the *rendered markup*
(not just that the backend URLs respond).

    python repro_workspace_ui.py
"""
import os
import re
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ResTrack.settings')
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECRET_KEY', 'repro-only-not-a-real-secret')
django.setup()

from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402

FAILURES = []


def markup_only(html):
    """Drop <script>/<style> bodies and HTML comments.

    Without this, checking for 'data-ws-switcher-toggle' matches the JS
    selector strings (or a comment mentioning them) and reports a control as
    present when no such element was actually rendered.
    """
    html = re.sub(r'<script.*?</script>', ' ', html, flags=re.S)
    html = re.sub(r'<style.*?</style>', ' ', html, flags=re.S)
    html = re.sub(r'<!--.*?-->', ' ', html, flags=re.S)
    return html



def text_of(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', markup_only(html))).strip()


def check(label, ok):
    print(f'  [{"PASS" if ok else "FAIL"}] {label}')
    if not ok:
        FAILURES.append(label)


def section(title):
    print('\n' + '=' * 68)
    print(title)
    print('=' * 68)


def count(pattern, html):
    return len(re.findall(pattern, markup_only(html)))


def main():
    from django.contrib.auth.models import User
    from django.test import Client
    from marks.models import TeacherProfile, Workspace

    client = Client()
    user = User.objects.create_user(username='newteacher', password='pw12345!')
    TeacherProfile.objects.create(user=user)
    client.force_login(user)

    # ---------------------------------------------------------------
    section('1. Brand-new teacher, single workspace, loads /dashboard/')
    # ---------------------------------------------------------------
    html = client.get('/dashboard/', follow=True).content.decode()
    m = markup_only(html)
    print('  workspaces in DB:', list(
        Workspace.objects.filter(teacher=user).values_list('name', 'slug_number')))

    check('desktop switcher button rendered', 'data-ws-switcher-toggle' in m)
    check('desktop switcher menu rendered (was hidden with 1 workspace)',
          'data-ws-switcher-menu' in m)
    check('mobile switcher rendered (was hidden with 1 workspace)',
          'data-ws-mobile-switcher' in m)
    check('"Create workspace" link reachable from nav',
          'href="/workspaces/create/"' in m)
    check('"Manage workspaces" link reachable from nav',
          'href="/workspaces/"' in m)
    check('active workspace name visible', 'Default Workspace' in m)
    check('exactly one [data-ws-switcher] root (no duplicate that breaks JS)',
          count(r'data-ws-switcher(?![-\w])', html) == 1)
    check('dashboard empty-state renders for empty workspace',
          'is empty' in text_of(html))

    # ---------------------------------------------------------------
    section('2. Manage page exposes Workspaces')
    # ---------------------------------------------------------------
    mhtml = markup_only(client.get('/manage/', follow=True).content.decode())
    check('Workspaces card on /manage/', 'href="/workspaces/"' in mhtml)

    # ---------------------------------------------------------------
    section('3. Create a second workspace through the UI form')
    # ---------------------------------------------------------------
    form_html = markup_only(client.get('/workspaces/create/').content.decode())
    check('create form posts to /workspaces/create/',
          'action="/workspaces/create/"' in form_html)
    check('create form has a name input', 'name="name"' in form_html)

    resp = client.post('/workspaces/create/',
                       {'name': 'Class 9', 'description': 'Second batch'},
                       follow=True)
    names = list(Workspace.objects.filter(teacher=user)
                 .order_by('slug_number').values_list('name', flat=True))
    check('second workspace created', names == ['Default Workspace', 'Class 9'])
    check('new workspace became active', 'Class 9' in markup_only(resp.content.decode()))

    ws1 = Workspace.objects.get(teacher=user, slug_number=1)
    ws2 = Workspace.objects.get(teacher=user, slug_number=2)

    # ---------------------------------------------------------------
    section('4. Switcher lists both workspaces and can switch')
    # ---------------------------------------------------------------
    html = client.get('/dashboard/', follow=True).content.decode()
    m = markup_only(html)
    check('switch form for the non-active workspace present in nav',
          f'action="/workspaces/{ws1.pk}/switch/"' in m)
    check('switch form carries CSRF token', 'csrfmiddlewaretoken' in m)
    check('switch form returns to current page', 'name="next"' in m)

    resp = client.post(f'/workspaces/{ws1.pk}/switch/',
                       {'next': '/dashboard/'}, follow=True)
    check('switching redirects back to the page you were on',
          resp.request['PATH_INFO'] == '/dashboard/')
    check('active workspace label now shows the switched-to workspace',
          'Default Workspace' in markup_only(resp.content.decode()))

    # ---------------------------------------------------------------
    section('5. Manage page: edit / archive / restore / delete controls')
    # ---------------------------------------------------------------
    lhtml = markup_only(client.get('/workspaces/').content.decode())
    check('list shows both workspaces',
          'Default Workspace' in lhtml and 'Class 9' in lhtml)
    check('New workspace button', 'href="/workspaces/create/"' in lhtml)
    check('Edit link per workspace', f'href="/workspaces/{ws2.pk}/edit/"' in lhtml)
    check('Archive form per workspace',
          f'action="/workspaces/{ws2.pk}/archive/"' in lhtml)
    check('Delete link per workspace',
          f'href="/workspaces/{ws2.pk}/delete/"' in lhtml)
    check('Active badge on the current workspace', 'Active' in text_of(lhtml))

    client.post(f'/workspaces/{ws2.pk}/edit/',
                {'name': 'Class 9 - 2026', 'description': 'Renamed'}, follow=True)
    ws2.refresh_from_db()
    check('edit renamed the workspace', ws2.name == 'Class 9 - 2026')
    check('rename did not change the immutable slug', ws2.slug_number == 2)

    client.post(f'/workspaces/{ws2.pk}/archive/', follow=True)
    ws2.refresh_from_db()
    check('archive worked', ws2.is_archived is True)
    lhtml = markup_only(client.get('/workspaces/').content.decode())
    check('archived workspace shows Restore control',
          f'action="/workspaces/{ws2.pk}/restore/"' in lhtml)
    nav = markup_only(client.get('/dashboard/', follow=True).content.decode())
    check('archived workspace dropped out of the nav switcher',
          f'action="/workspaces/{ws2.pk}/switch/"' not in nav)

    client.post(f'/workspaces/{ws2.pk}/restore/', follow=True)
    ws2.refresh_from_db()
    check('restore worked', ws2.is_archived is False)

    # ---------------------------------------------------------------
    section('6. Delete flow (type-to-confirm)')
    # ---------------------------------------------------------------
    dhtml = markup_only(client.get(f'/workspaces/{ws2.pk}/delete/').content.decode())
    check('delete page asks for confirmation name', 'name="confirm_name"' in dhtml)

    client.post(f'/workspaces/{ws2.pk}/delete/', {'confirm_name': 'wrong'}, follow=True)
    check('wrong confirmation does NOT delete',
          Workspace.objects.filter(pk=ws2.pk).exists())

    client.post(f'/workspaces/{ws2.pk}/delete/',
                {'confirm_name': ws2.name}, follow=True)
    check('correct confirmation deletes',
          not Workspace.objects.filter(pk=ws2.pk).exists())
    check('other workspace untouched', Workspace.objects.filter(pk=ws1.pk).exists())

    # ---------------------------------------------------------------
    section('7. Last workspace cannot be deleted (no broken state)')
    # ---------------------------------------------------------------
    client.post(f'/workspaces/{ws1.pk}/delete/',
                {'confirm_name': ws1.name}, follow=True)
    check('refuses to delete the only workspace',
          Workspace.objects.filter(pk=ws1.pk).exists())

    # ---------------------------------------------------------------
    section('8. Students never see workspace controls')
    # ---------------------------------------------------------------
    from marks.models import Student, StudentProfile
    student_user = User.objects.create_user(username='pupil', password='pw12345!')
    student = Student.objects.create(first_name='Ada', last_name='L', roll='1',
                                    class_name='9', workspace=ws1)
    StudentProfile.objects.create(user=student_user, student=student, created_by=user)

    sclient = Client()
    sclient.force_login(student_user)
    shtml = markup_only(sclient.get('/dashboard/', follow=True).content.decode())
    check('student sees no switcher', 'data-ws-switcher-toggle' not in shtml)
    check('student sees no workspace links', '/workspaces/' not in shtml)
    check('student blocked from /workspaces/',
          sclient.get('/workspaces/').status_code == 403)

    # ---------------------------------------------------------------
    section('9. Guest session is pinned (view-only, no management)')
    # ---------------------------------------------------------------
    from marks.models import GuestTeacherAccount
    guest_user = User.objects.create_user(username='guesty', password='pw12345!')
    GuestTeacherAccount.objects.create(teacher=user, workspace=ws1,
                                       guest_user=guest_user)

    gclient = Client()
    gclient.post('/login/', {'username': 'guesty', 'password': 'pw12345!'}, follow=True)
    ghtml = markup_only(gclient.get('/dashboard/', follow=True).content.decode())
    check('guest sees the workspace name', 'Default Workspace' in ghtml)
    check('guest gets no create/manage links', 'href="/workspaces/create/"' not in ghtml)


if __name__ == '__main__':
    setup_test_environment()
    runner = DiscoverRunner(verbosity=0, interactive=False)
    old_config = runner.setup_databases()
    try:
        main()
    finally:
        runner.teardown_databases(old_config)
        teardown_test_environment()

    print('\n' + '=' * 68)
    if FAILURES:
        print(f'{len(FAILURES)} CHECK(S) FAILED:')
        for f in FAILURES:
            print('  -', f)
        sys.exit(1)
    print('ALL CHECKS PASSED')
